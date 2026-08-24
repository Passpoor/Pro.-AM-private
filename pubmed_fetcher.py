"""PubMed 增量监测、结构化分析与可靠投递。"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib
import json
import logging
import os
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from Bio import Entrez, Medline
from deep_translator import GoogleTranslator

log = logging.getLogger("pro_am")
EASYSCHOLAR_CACHE: dict[str, dict[str, Any]] = {}
ZHIPU_AUTH_FAILED = False
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def today_in_beijing() -> dt.date:
    return dt.datetime.now(BEIJING_TZ).date()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CAR-M PubMed literature monitor")
    parser.add_argument(
        "--config", default="config_car_m", help="配置模块名（不含 .py）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="生成预览，不发送邮件或写入状态"
    )
    parser.add_argument("--limit", type=int, help="限制本次处理的新论文数量")
    parser.add_argument(
        "--preview", default="digest_preview.html", help="dry-run HTML 预览路径"
    )
    return parser.parse_args(argv)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )


def state_path_for(config_name: str) -> Path:
    configured = os.environ.get("STATE_FILE")
    return (
        Path(configured)
        if configured
        else Path(__file__).parent / f"state_{config_name}.json"
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 2, "papers": {}, "last_successful_delivery": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"状态文件无法读取: {path}: {exc}") from exc
    if "papers" in raw:
        raw.setdefault("version", 2)
        raw.setdefault("last_successful_delivery", None)
        return raw
    return {
        "version": 2,
        "papers": {
            str(pmid): {"status": "delivered", "migrated": True}
            for pmid in raw.get("sent_pmids", [])
        },
        "last_successful_delivery": None,
    }


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def prune_state(state: dict[str, Any], max_papers: int = 2000) -> None:
    papers = state["papers"]
    if len(papers) <= max_papers:
        return
    removable = [
        pmid for pmid, item in papers.items() if item.get("status") != "pending"
    ]
    for pmid in removable[: max(0, len(papers) - max_papers)]:
        papers.pop(pmid, None)


def search_pubmed(query: str, days_back: int, max_results: int) -> list[str]:
    """按 PubMed 入库日期 EDAT 做增量检索，避免漏掉延迟收录记录。"""
    today = today_in_beijing()
    mindate = (today - dt.timedelta(days=days_back)).strftime("%Y/%m/%d")
    maxdate = today.strftime("%Y/%m/%d")
    log.info("  检索入库范围: %s ~ %s", mindate, maxdate)
    with Entrez.esearch(
        db="pubmed",
        term=query,
        datetype="edat",
        mindate=mindate,
        maxdate=maxdate,
        retmax=max_results,
        sort="pub_date",
    ) as handle:
        record = Entrez.read(handle)
    pmids = [str(pmid) for pmid in record.get("IdList", [])]
    log.info("  找到 %d 篇", len(pmids))
    return pmids


def fetch_details(pmids: list[str]) -> tuple[list[dict[str, Any]], set[str]]:
    if not pmids:
        return [], set()
    with Entrez.efetch(
        db="pubmed", id=",".join(pmids), rettype="medline", retmode="text"
    ) as handle:
        records = list(Medline.parse(handle))
    articles: list[dict[str, Any]] = []
    for record in records:
        pmid = str(record.get("PMID", "")).strip()
        if not pmid:
            continue
        abstract = str(record.get("AB", "")).strip()
        if not abstract:
            log.info("  跳过无摘要: %s", str(record.get("TI", ""))[:60])
            continue
        all_authors = [str(author) for author in record.get("AU", [])]
        authors = all_authors[:5] + (["et al."] if len(all_authors) > 5 else [])
        articles.append(
            {
                "pmid": pmid,
                "doi": next(
                    (aid for aid in record.get("AID", []) if "[doi]" in aid), ""
                ).replace(" [doi]", ""),
                "title": str(record.get("TI", "")).strip(),
                "abstract": abstract,
                "journal": str(record.get("TA") or record.get("JT") or "").strip(),
                "date": str(record.get("DP", "")).strip(),
                "authors": ", ".join(authors),
                "publication_types": [str(value) for value in record.get("PT", [])],
                "mesh_terms": [str(value) for value in record.get("MH", [])],
            }
        )
    return articles, set(pmids) - {article["pmid"] for article in articles}


def get_journal_rank(journal_name: str, api_key: str) -> dict[str, Any]:
    if not journal_name or not api_key:
        return {}
    if journal_name in EASYSCHOLAR_CACHE:
        return EASYSCHOLAR_CACHE[journal_name]
    try:
        query = urllib.parse.urlencode(
            {"secretKey": api_key, "publicationName": journal_name}
        )
        request = urllib.request.Request(
            f"https://www.easyscholar.cc/open/getPublicationRank?{query}"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("code") != 200:
            return {}
        data = result.get("data", {})
        official = data.get("officialRank", {}).get("all", {})
        rank_info: dict[str, Any] = {
            "sciif": official.get("sciif", "—"),
            "sciif5": official.get("sciif5", "—"),
            "jci": official.get("jci", "—"),
            "sciUp": official.get("sciUp", "—"),
            "esi": official.get("esi", "—"),
        }
        rank_metadata = data.get("customRank", {})
        rank_names = {
            item.get("uuid"): item.get("abbName", "")
            for item in rank_metadata.get("rankInfo", [])
        }
        for value in rank_metadata.get("rank", []):
            uuid, separator, level = value.partition("&&&")
            if not separator:
                continue
            name = rank_names.get(uuid, "")
            if "SCI" in name or "中科院" in name:
                rank_info["sciZone"] = level
            elif "预警" in name:
                rank_info["warning"] = level
        EASYSCHOLAR_CACHE[journal_name] = rank_info
        return rank_info
    except Exception as exc:  # noqa: BLE001 - 可选元数据服务不得阻断主流程
        log.warning("  期刊排名查询失败 [%s]: %s", journal_name, exc)
        EASYSCHOLAR_CACHE[journal_name] = {}
        return {}


def translate(text: str, translator: GoogleTranslator) -> str:
    if not text.strip():
        return ""
    try:
        if len(text) <= 4500:
            return translator.translate(text)
        chunks: list[str] = []
        current = ""
        for sentence in text.split(". "):
            candidate = f"{current}{sentence}. "
            if len(candidate) > 4000 and current:
                chunks.append(translator.translate(current.strip()))
                current = f"{sentence}. "
            else:
                current = candidate
        if current:
            chunks.append(translator.translate(current.strip()))
        return " ".join(chunks)
    except Exception as exc:  # noqa: BLE001 - 第三方翻译器的异常类型不稳定
        log.warning("  翻译失败，保留英文原文: %s", exc)
        return text


INSIGHT_PROMPT = """你是CAR-M研究文献分析助手。只能依据下方英文摘要提取信息，不得补充摘要外知识。
无法确定的字段必须填空字符串。只返回合法JSON，不要Markdown。

JSON字段：relevance_score（1-10整数）、study_type、target_antigen、cell_source、delivery_method、
car_design、disease_model、main_finding、limitations、evidence_sentences（最多3条英文原句）。

标题：{title}
期刊：{journal}
摘要：{abstract}
"""


def generate_insight(article: dict[str, Any], api_key: str) -> dict[str, Any]:
    global ZHIPU_AUTH_FAILED
    if not api_key or ZHIPU_AUTH_FAILED:
        return {}
    payload = json.dumps(
        {
            "model": os.environ.get("ZHIPU_MODEL", "glm-4-flash"),
            "messages": [
                {
                    "role": "user",
                    "content": INSIGHT_PROMPT.format(
                        title=article["title"],
                        journal=article["journal"],
                        abstract=article["abstract"],
                    ),
                }
            ],
            "temperature": 0.1,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
            parsed = json.loads(result["choices"][0]["message"]["content"].strip())
            if not isinstance(parsed, dict):
                raise TypeError("模型输出不是 JSON 对象")
            score = parsed.get("relevance_score")
            if not isinstance(score, int) or not 1 <= score <= 10:
                raise ValueError("relevance_score 不在 1-10")
            evidence = parsed.get("evidence_sentences", [])
            parsed["evidence_sentences"] = (
                evidence[:3] if isinstance(evidence, list) else []
            )
            return parsed
        except urllib.error.HTTPError as exc:
            log.warning("  GLM 调用失败 (%d/3): HTTP %s", attempt + 1, exc.code)
            if exc.code in {401, 403}:
                ZHIPU_AUTH_FAILED = True
                break
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            log.warning("  GLM 输出无效 (%d/3): %s", attempt + 1, exc)
        if attempt < 2:
            time.sleep(2**attempt)
    return {}


def enrich_article(
    article: dict[str, Any], cfg: Any, translator: GoogleTranslator
) -> dict[str, Any]:
    enriched = dict(article)
    enriched["rank"] = get_journal_rank(
        article["journal"], getattr(cfg, "EASYSCHOLAR_KEY", "")
    )
    enriched["insight"] = generate_insight(article, os.environ.get("ZHIPU_API_KEY", ""))
    enriched["title_zh"] = translate(article["title"], translator)
    enriched["abstract_zh"] = translate(article["abstract"], translator)
    return enriched


def insight_html(insight: dict[str, Any]) -> str:
    if not insight:
        return ""
    labels = [
        ("相关性", f"{insight.get('relevance_score', '—')}/10"),
        ("递送方式", insight.get("delivery_method", "")),
        ("CAR设计", insight.get("car_design", "")),
        ("靶点", insight.get("target_antigen", "")),
        ("主要发现", insight.get("main_finding", "")),
        ("局限", insight.get("limitations", "")),
    ]
    fields = "".join(
        f"<div><strong>{html.escape(label)}：</strong>{html.escape(str(value))}</div>"
        for label, value in labels
        if value
    )
    evidence = insight.get("evidence_sentences", [])
    if isinstance(evidence, list) and evidence:
        quotes = "".join(
            f"<li>{html.escape(str(sentence))}</li>" for sentence in evidence[:3]
        )
        fields += f"<div><strong>摘要证据：</strong><ul>{quotes}</ul></div>"
    return fields


def build_email_html(articles: list[dict[str, Any]], search_days: int) -> str:
    today = today_in_beijing().isoformat()
    cards: list[str] = []
    overview: list[str] = []
    for index, article in enumerate(articles, 1):
        insight = article.get("insight", {})
        finding = insight.get("main_finding", "") if isinstance(insight, dict) else ""
        if finding:
            overview.append(
                f"<li><strong>{html.escape(article['title_zh'])}</strong>：{html.escape(finding)}</li>"
            )
        rank = article.get("rank", {})
        rank_values = [
            f"IF {rank['sciif']}" if rank.get("sciif") not in {None, "", "—"} else "",
            f"JCI {rank['jci']}" if rank.get("jci") not in {None, "", "—"} else "",
            str(rank.get("sciZone", "")),
        ]
        rank_line = " · ".join(value for value in rank_values if value)
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/"
        cards.append(f"""
<article class="paper"><div class="number">{index}</div>
  <div class="meta">{html.escape(article.get("journal", ""))} · {html.escape(article.get("date", ""))} · {html.escape(article.get("authors", ""))}</div>
  <div class="rank">{html.escape(rank_line)}</div><h2>{html.escape(article.get("title_zh") or article.get("title", ""))}</h2>
  <div class="title-en">{html.escape(article.get("title", ""))}</div><div class="insight">{insight_html(insight)}</div>
  <div class="abstract"><strong>中文摘要：</strong>{html.escape(article.get("abstract_zh", ""))}</div>
  <a href="{pubmed_url}">PubMed {html.escape(article["pmid"])}</a></article>""")
    overview_html = (
        f"<section class='overview'><h2>今日速览</h2><ul>{''.join(overview)}</ul></section>"
        if overview
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font-family:Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;color:#263238;max-width:760px;margin:auto;padding:20px;background:#f4f7f9}}
.header{{background:#175d7d;color:white;padding:20px 24px;border-radius:10px}}.header h1{{margin:0;font-size:22px}}
.overview,.paper{{background:white;margin:12px 0;padding:16px 20px;border-radius:10px;box-shadow:0 1px 4px #0001}}
.paper{{border-left:4px solid #2e86c1}}.number{{float:right;background:#2e86c1;color:white;border-radius:50%;padding:4px 9px}}
.meta,.rank,.title-en{{font-size:12px;color:#78909c}}h2{{font-size:16px;line-height:1.5}}.insight{{background:#fff8e1;padding:10px;margin:10px 0;line-height:1.7}}
.abstract{{font-size:13px;line-height:1.7;background:#f7f9fa;padding:10px;margin:10px 0}}a{{color:#1565c0}}
</style></head><body><section class="header"><h1>CAR-M 文献雷达</h1><div>{today} · 入库窗口 {search_days} 天 · {len(articles)} 篇</div></section>
{overview_html}{"".join(cards)}</body></html>"""


def send_email(cfg: Any, subject: str, content: str) -> None:
    missing = []
    if not cfg.SENDER_EMAIL:
        missing.append("SENDER_EMAIL")
    if not cfg.SMTP_AUTH_CODE:
        missing.append("SMTP_AUTH_CODE")
    if not cfg.RECEIVER_EMAILS:
        missing.append("RECEIVER_EMAILS")
    if missing:
        raise RuntimeError(f"邮件配置缺失: {', '.join(missing)}")
    message = MIMEMultipart("alternative")
    message["Subject"], message["From"], message["To"] = (
        subject,
        cfg.SENDER_EMAIL,
        ", ".join(cfg.RECEIVER_EMAILS),
    )
    message.attach(MIMEText(content, "html", "utf-8"))
    with smtplib.SMTP_SSL(
        cfg.SMTP_SERVER, cfg.SMTP_PORT, context=ssl.create_default_context()
    ) as server:
        server.login(cfg.SENDER_EMAIL, cfg.SMTP_AUTH_CODE)
        server.sendmail(cfg.SENDER_EMAIL, cfg.RECEIVER_EMAILS, message.as_string())


def discover_topic(topic: dict[str, Any], days: int, known: set[str]) -> list[str]:
    primary = [
        pmid
        for pmid in search_pubmed(topic["query"], days, topic["max_results"])
        if pmid not in known
    ]
    if primary or not topic.get("fallback_query"):
        return primary
    log.info("  主检索没有新论文，启用宽泛 fallback 检索")
    return [
        pmid
        for pmid in search_pubmed(topic["fallback_query"], days, topic["max_results"])
        if pmid not in known
    ]


def run(config_name: str, dry_run: bool, limit: int | None, preview: Path) -> int:
    cfg = importlib.import_module(config_name)
    Entrez.email = (
        os.environ.get("NCBI_EMAIL")
        or cfg.SENDER_EMAIL
        or "pro-am-literature-monitor@example.com"
    )
    Entrez.api_key = os.environ.get("NCBI_API_KEY") or None
    Entrez.max_tries, Entrez.sleep_between_tries = 3, 5
    path = state_path_for(config_name)
    state = load_state(path)
    papers: dict[str, dict[str, Any]] = state["papers"]
    known = set(papers)
    days = cfg.MAX_BACKFILL_DAYS if not known else cfg.RECENT_DAYS
    remaining = limit
    translator = GoogleTranslator(source="en", target="zh-CN")

    for topic in cfg.TOPICS:
        log.info("主题: %s", topic["name_zh"])
        pmids = discover_topic(topic, days, known)
        if remaining is not None:
            pmids = pmids[: max(0, remaining)]
            remaining -= len(pmids)
        articles, unavailable = fetch_details(pmids)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        for pmid in unavailable:
            papers[pmid] = {"status": "skipped_no_abstract", "checked_at": now}
            known.add(pmid)
        for index, article in enumerate(articles, 1):
            log.info("  处理 %d/%d: %s", index, len(articles), article["title"][:70])
            enriched = enrich_article(article, cfg, translator)
            enriched["topic_zh"] = topic["name_zh"]
            score = enriched.get("insight", {}).get("relevance_score")
            threshold = topic.get("min_relevance_score", 1)
            if isinstance(score, int) and score < threshold:
                papers[article["pmid"]] = {
                    "status": "excluded_low_relevance",
                    "processed_at": now,
                    "relevance_score": score,
                    "title": article["title"],
                }
                log.info(
                    "  相关性 %d/%d，排除: %s", score, threshold, article["title"][:60]
                )
            else:
                papers[article["pmid"]] = {
                    "status": "pending",
                    "processed_at": now,
                    "article": enriched,
                }
            known.add(article["pmid"])
        if remaining == 0:
            break

    pending = [
        item["article"]
        for item in papers.values()
        if item.get("status") == "pending" and item.get("article")
    ]
    if not pending:
        if not dry_run:
            prune_state(state)
            save_state(path, state)
        log.info("没有待推送的新文献")
        print("NO_NEW_PAPERS")
        return 0
    digest = build_email_html(pending, days)
    if dry_run:
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(digest, encoding="utf-8")
        log.info(
            "dry-run 完成：%d 篇，预览 %s；未发送、未写状态", len(pending), preview
        )
        return 0

    prune_state(state)
    save_state(path, state)
    today = today_in_beijing().isoformat()
    send_email(cfg, f"[CAR-M 文献雷达] {today} ({len(pending)}篇)", digest)
    delivered_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for article in pending:
        item = papers[article["pmid"]]
        item["status"], item["delivered_at"] = "delivered", delivered_at
        item.pop("article", None)
    state["last_successful_delivery"] = delivered_at
    prune_state(state)
    save_state(path, state)
    log.info("完成：推送 %d 篇到 %s", len(pending), ", ".join(cfg.RECEIVER_EMAILS))
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv)
    return run(args.config, args.dry_run, args.limit, Path(args.preview))


if __name__ == "__main__":
    raise SystemExit(main())
