# pubmed_fetcher.py - PubMed 文献爬取 + 翻译 + AI设计启发 + 邮件推送

import argparse
import datetime
import html
import importlib
import json
import logging
import os
import smtplib
import ssl
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from Bio import Entrez
from deep_translator import GoogleTranslator

parser = argparse.ArgumentParser(description="PubMed Daily Fetcher")
parser.add_argument("--config", default="config_car_m", help="配置模块名（不含 .py），如 config_car_m")
args = parser.parse_args()

cfg = importlib.import_module(args.config)
TOPICS = cfg.TOPICS
RECENT_DAYS = cfg.RECENT_DAYS
MAX_BACKFILL_DAYS = cfg.MAX_BACKFILL_DAYS
SMTP_SERVER = cfg.SMTP_SERVER
SMTP_PORT = cfg.SMTP_PORT
SENDER_EMAIL = cfg.SENDER_EMAIL
SMTP_AUTH_CODE = cfg.SMTP_AUTH_CODE
RECEIVER_EMAILS = cfg.RECEIVER_EMAILS
CONFIG_NAME = args.config

ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "pubmed.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

Entrez.email = SENDER_EMAIL

# ---------- 翻译 ----------

_translator = GoogleTranslator(source="en", target="zh-CN")


def translate(text: str) -> str:
    if not text or not text.strip():
        return ""
    try:
        if len(text) > 4500:
            parts = []
            sentences = text.split(". ")
            chunk = ""
            for s in sentences:
                if len(chunk) + len(s) < 4000:
                    chunk = chunk + s + ". " if chunk else s + ". "
                else:
                    if chunk:
                        parts.append(_translator.translate(chunk.strip()))
                    chunk = s + ". "
            if chunk:
                parts.append(_translator.translate(chunk.strip()))
            return " ".join(parts)
        else:
            return _translator.translate(text)
    except Exception as e:
        log.warning(f"翻译失败: {e}")
        return text


# ---------- EasyScholar 期刊排名查询 ----------

EASYSCHOLAR_KEY = "5b3999c870c042d6a4aacbd6ba13f100"
EASYSCHOLAR_CACHE = {}  # 运行内缓存，避免重复查询同期刊


def get_journal_rank(journal_name: str) -> dict:
    """查询期刊排名信息，返回关键指标字典"""
    if not journal_name or journal_name in EASYSCHOLAR_CACHE:
        return EASYSCHOLAR_CACHE.get(journal_name, {})

    try:
        url = f"https://www.easyscholar.cc/open/getPublicationRank?secretKey={EASYSCHOLAR_KEY}&publicationName={urllib.request.quote(journal_name)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if result.get("code") != 200:
            EASYSCHOLAR_CACHE[journal_name] = {}
            return {}

        data = result.get("data", {})
        official = data.get("officialRank", {}).get("all", {})

        # 提取关键信息
        rank_info = {{
            "sciif": official.get("sciif", "—"),
            "sciif5": official.get("sciif5", "—"),
            "jci": official.get("jci", "—"),
            "sciUp": official.get("sciUp", "—"),
            "esi": official.get("esi", "—"),
        }}

        # 解析 customRank 中的 SCI分区 和 预警
        rank_list = data.get("customRank", {}).get("rank", [])
        for item in rank_list:
            parts = item.split("&&&")
            if len(parts) == 2:
                uuid, level = parts
                rank_infos = data.get("customRank", {}).get("rankInfo", [])
                for ri in rank_infos:
                    if ri.get("uuid") == uuid:
                        abb = ri.get("abbName", "")
                        if "SCI" in abb or "中科院" in abb:
                            rank_info["sciZone"] = level
                        elif "预警" in abb:
                            rank_info["warning"] = level

        EASYSCHOLAR_CACHE[journal_name] = rank_info
        return rank_info
    except Exception as e:
        log.warning(f"  期刊排名查询失败 [{journal_name}]: {e}")
        EASYSCHOLAR_CACHE[journal_name] = {}
        return {}


# ---------- 智谱 GLM 设计启发总结 ----------

INSIGHT_PROMPT = """你是一名CAR-M（嵌合抗原受体巨噬细胞）领域的资深研究员。请基于以下文献信息，总结设计启发。

文献信息：
- 第一作者：{first_author}
- 期刊：{journal}
- 标题：{title}
- 中文摘要：{abstract}

要求：
1. 从"递送方式"和"CAR-M结构设计"两个维度总结，每个维度1-2句话
2. 只提取摘要中明确提到或可合理推断的信息，不要编造
3. 如果某个维度在摘要中无法提取，写"摘要中未明确提及"
4. 用中文回答，格式严格如下（每行一个维度，不要换行）：

💡 递送方式：xxx
🧬 CAR-M 结构设计：xxx"""


def call_zhipu(prompt: str, max_retries: int = 3) -> str:
    """调用智谱 GLM-4-Flash API"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    payload = json.dumps({
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
    }

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"  GLM 调用失败 (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return "AI 总结生成失败"


def generate_insight(first_author: str, journal: str, title: str, abstract_zh: str) -> str:
    """生成 CAR-M 设计启发总结"""
    if not ZHIPU_API_KEY:
        return ""
    prompt = INSIGHT_PROMPT.format(
        first_author=first_author,
        journal=journal,
        title=title,
        abstract=abstract_zh
    )
    raw = call_zhipu(prompt)
    return md_to_html(raw)


def md_to_html(text: str) -> str:
    """简易 Markdown → HTML（处理加粗、斜体、换行）"""
    import re
    if not text:
        return ""
    # 加粗 **text** → <strong>text</strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 斜体 *text* → <em>text</em>（注意排除已匹配的加粗）
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    # 换行
    text = text.replace("\n", "<br>")
    return text


# ---------- PubMed 查询 ----------

def search_pubmed(query: str, days_back: int, max_results: int) -> list[str]:
    mindate = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%Y/%m/%d")
    maxdate = datetime.date.today().strftime("%Y/%m/%d")
    full_query = f'{query} AND ("{mindate}"[Date - Publication] : "{maxdate}"[Date - Publication])'
    log.info(f"  检索范围: {mindate} ~ {maxdate}")
    handle = Entrez.esearch(db="pubmed", term=full_query, retmax=max_results, sort="pub_date")
    record = Entrez.read(handle)
    handle.close()
    pmids = record.get("IdList", [])
    log.info(f"  找到 {len(pmids)} 篇")
    return pmids


def fetch_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    handle = Entrez.efetch(db="pubmed", id=",".join(pmids), rettype="medline", retmode="text")
    raw = handle.read()
    handle.close()

    articles = []
    for block in raw.split("\n\n"):
        lines = block.strip().split("\n")
        if not lines:
            continue
        record = {}
        current_key = None
        current_val = []
        for line in lines:
            if line[:4].strip() and line[4:6] == "- ":
                if current_key:
                    record[current_key] = "\n".join(current_val).strip()
                current_key = line[:4].strip()
                current_val = [line[6:].strip()]
            elif current_key:
                current_val.append(line.strip())
        if current_key:
            record[current_key] = "\n".join(current_val).strip()

        if "PMID" not in record:
            continue

        pmid = record["PMID"].split("\n")[0].strip()
        title = record.get("TI", "")
        abstract = record.get("AB", "")
        journal = record.get("TA", "") or record.get("JT", "")
        pub_date = ""
        dp = record.get("DP", "")
        if dp:
            pub_date = dp.split(" ")[0]

        authors = []
        for key in record:
            if key.startswith("AU"):
                au = record[key].strip()
                if au:
                    authors.append(au)
                if len(authors) >= 5:
                    authors.append("et al.")
                    break

        if not abstract or not abstract.strip():
            log.info(f"  跳过无摘要: {title[:60]}...")
            continue

        articles.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "date": pub_date,
            "authors": ", ".join(authors),
        })
    return articles


# ---------- 邮件发送 ----------

def build_email_html(all_results: list[dict], search_days: int) -> str:
    """all_results: [{"topic_zh": "CAR-M", "articles": [...]}, ...]"""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    total = sum(len(r["articles"]) for r in all_results)

    # 生成今日速览
    overview_lines = []
    for result in all_results:
        for art in result["articles"]:
            insight = art.get("insight", "")
            if insight and "失败" not in insight:
                # 提取关键信息，压缩成一行
                first_line = insight.split("<br>")[0].strip()
                # 去掉 HTML 标签，提取递送方式要点
                import re as _re
                clean_text = _re.sub(r'<[^>]+>', '', insight)
                # 取递送方式那行
                delivery_line = ""
                for line in clean_text.split("<br>"):
                    line = line.strip()
                    if "递送方式" in line:
                        delivery_line = _re.sub(r'^.*?递送方式[：:]\s*', '', line).strip()
                        break
                if not delivery_line:
                    delivery_line = clean_text.split("<br>")[0].strip()

                # 提取第一作者（去掉 et al.）
                first_author = art.get("authors", "").split(",")[0].strip().replace(" et al.", "")
                journal_name = art.get("journal", "")

                overview_lines.append(
                    f"<li><strong>{html.escape(first_author)}</strong> 在 <strong>{html.escape(journal_name)}</strong> 提出：{html.escape(delivery_line)}</li>"
                )

    overview_html = ""
    if overview_lines:
        overview_html = f"""\
<div class="overview">
  <div class="overview-title">📌 今日速览</div>
  <ul>{''.join(overview_lines)}</ul>
</div>
"""

    html_parts = [f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #333; max-width: 720px; margin: 0 auto; padding: 20px; background: #f4f6f9; }}

.header {{ background: linear-gradient(135deg, #1a5276, #2e86c1); color: #fff; padding: 20px 24px; border-radius: 10px; margin-bottom: 6px; }}
.header h1 {{ margin: 0 0 4px 0; font-size: 20px; letter-spacing: 0.5px; }}
.header .summary {{ font-size: 13px; opacity: 0.9; }}

.overview {{ background: #fff; border-radius: 10px; padding: 14px 18px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 4px solid #27ae60; }}
.overview-title {{ font-size: 14px; font-weight: 700; color: #1e8449; margin: 0 0 6px 0; }}
.overview ul {{ margin: 0; padding-left: 18px; }}
.overview li {{ font-size: 12px; color: #555; line-height: 1.6; margin-bottom: 3px; }}

.paper {{ background: #fff; border-radius: 10px; padding: 14px 18px; margin: 8px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 4px solid #2e86c1; }}

.paper-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
.paper-num {{ background: #2e86c1; color: #fff; width: 24px; height: 24px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }}
.paper-link a {{ color: #2e86c1; text-decoration: none; font-size: 11px; border: 1px solid #d4e6f1; padding: 2px 8px; border-radius: 10px; }}

.meta {{ font-size: 11px; color: #888; margin-bottom: 4px; }}

.rank-tags {{ font-size: 11px; color: #2e86c1; margin-bottom: 4px; font-weight: 600; }}

.title-zh {{ font-size: 15px; font-weight: 700; color: #1a1a2e; line-height: 1.5; margin: 4px 0; }}
.title-en {{ font-size: 12px; color: #999; line-height: 1.4; margin: 2px 0 6px 0; }}

.insight-box {{ padding: 10px 14px; background: linear-gradient(135deg, #fef9e7, #fdebd0); border-radius: 8px; border-left: 3px solid #f39c12; font-size: 12px; color: #7d6608; line-height: 1.7; margin-top: 6px; }}
.insight-box strong {{ color: #b7950b; }}

details {{ margin-top: 6px; }}
details summary {{ cursor: pointer; font-size: 12px; color: #2e86c1; user-select: none; padding: 4px 0; }}
details summary:hover {{ color: #1a5276; }}
.abstract-zh {{ font-size: 12px; color: #666; line-height: 1.7; text-align: justify; padding: 10px 14px; background: #f8f9fa; border-radius: 6px; margin-top: 4px; }}

.footer {{ text-align: center; color: #bbb; font-size: 10px; margin-top: 24px; padding: 12px 0; border-top: 1px solid #e5e8e8; }}
</style></head><body>

<div class="header">
  <h1>🔬 CAR-M 顶刊日报</h1>
  <div class="summary">📅 {today_str} &nbsp;&nbsp;|&nbsp;&nbsp; 🔍 近 {search_days} 天 &nbsp;&nbsp;|&nbsp;&nbsp; 📊 共 {total} 篇</div>
</div>

{overview_html}
"""]

    for result in all_results:
        topic_zh = result["topic_zh"]
        articles = result["articles"]

        for i, art in enumerate(articles, 1):
            title_zh = art.get("title_zh", "")
            abstract_zh = art.get("abstract_zh", "")
            insight = art.get("insight", "")
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{art['pmid']}/"
            rank = art.get("rank", {})

            # 期刊排名标签
            rank_tags = []
            if rank.get("sciif") and rank["sciif"] != "—":
                rank_tags.append(f"IF: {rank['sciif']}")
            if rank.get("sciif5") and rank["sciif5"] != "—":
                rank_tags.append(f"IF5: {rank['sciif5']}")
            if rank.get("sciUp") and rank["sciUp"] != "—":
                rank_tags.append(rank["sciUp"])
            if rank.get("jci") and rank["jci"] != "—":
                rank_tags.append(f"JCI: {rank['jci']}")
            if rank.get("warning"):
                rank_tags.append(f"⚠️ 预警: {rank['warning']}")

            rank_html = ""
            if rank_tags:
                rank_html = f'<div class="rank-tags">{" &nbsp;|&nbsp; ".join(rank_tags)}</div>'

            insight_html = ""
            if insight and "失败" not in insight:
                insight_html = f'<div class="insight-box">{insight}</div>'

            html_parts.append(f"""\
<div class="paper">
  <div class="paper-head">
    <span class="paper-num">{i}</span>
    <span class="paper-link"><a href="{pubmed_url}" target="_blank">PubMed 🔗</a></span>
  </div>
  <div class="meta">📖 {html.escape(art['journal'] or 'Unknown')} &nbsp;|&nbsp; 📆 {html.escape(art['date'] or '—')} &nbsp;|&nbsp; ✍️ {html.escape(art['authors'] or '—')}</div>
  {rank_html}
  <div class="title-zh">{html.escape(title_zh)}</div>
  <div class="title-en">{html.escape(art['title'])}</div>
  {insight_html}
  <details>
    <summary>📖 展开中文摘要</summary>
    <div class="abstract-zh">{html.escape(abstract_zh)}</div>
  </details>
</div>

""")

    html_parts.append(f"""\
<div class="footer">
  CAR-M 顶刊日报 · Powered by OpenClaw + 智谱GLM<br>
  检索主题: CAR-M（嵌合抗原受体巨噬细胞, Chimeric Antigen Receptor Macrophage）<br>
  检索范围: 77 本中科院1区顶刊（含材料/递送方向）
</div>
</body></html>
""")
    return "\n".join(html_parts)


def send_email(subject: str, html_content: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECEIVER_EMAILS)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SMTP_AUTH_CODE)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())
    log.info("邮件发送成功!")


# ---------- 主流程 ----------

STATE_FILE = Path(__file__).parent / f"state_{CONFIG_NAME}.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"sent_pmids": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    state = load_state()
    all_results = []
    any_new = False
    search_days = RECENT_DAYS

    for topic in TOPICS:
        log.info(f"🔍 主题: {topic['name_zh']}")

        # 先查最近 7 天
        pmids = search_pubmed(topic["query"], RECENT_DAYS, topic["max_results"])
        new_pmids = [p for p in pmids if p not in state.get("sent_pmids", [])]

        # 不够则回溯
        if len(new_pmids) < topic["max_results"]:
            log.info(f"  最近 {RECENT_DAYS} 天仅 {len(new_pmids)} 篇新文献，回溯到 {MAX_BACKFILL_DAYS} 天...")
            all_pmids = search_pubmed(topic["query"], MAX_BACKFILL_DAYS, topic["max_results"])
            new_pmids = [p for p in all_pmids if p not in state.get("sent_pmids", [])]
            search_days = MAX_BACKFILL_DAYS

        if not new_pmids:
            log.info(f"  {topic['name_zh']} 没有新论文")
            continue
        pmids_to_fetch = new_pmids[:topic["max_results"]]
        log.info(f"  准备推送 {len(pmids_to_fetch)} 篇")

        # 获取详情 + 翻译
        articles = fetch_details(pmids_to_fetch)

        # 如果全部无摘要被跳过
        # All fetched articles had no abstract - try fallback (broad search)
        if not articles:
            fallback_query = topic.get("fallback_query")
            if fallback_query:
                log.info(f"  顶刊新论文无摘要，尝试宽泛检索...")
                fb_pmids = search_pubmed(fallback_query, MAX_BACKFILL_DAYS, topic["max_results"])
                fb_new = [p for p in fb_pmids if p not in state.get("sent_pmids", [])]
                if fb_new:
                    articles = fetch_details(fb_new[:topic["max_results"]])
                    search_days = MAX_BACKFILL_DAYS
            if not articles:
                log.info(f"  {topic['name_zh']} 没有新论文")
                continue

        # 用实际有摘要的 PMID 记录去重
        actual_pmids = [art["pmid"] for art in articles]
        state["sent_pmids"].extend(actual_pmids)
        any_new = True

        # 查询期刊排名
        log.info(f"  查询期刊排名...")
        for art in articles:
            art["rank"] = get_journal_rank(art["journal"])
            time.sleep(0.3)

        log.info(f"  开始翻译...")
        for i, art in enumerate(articles):
            log.info(f"    {i+1}/{len(articles)}: {art['title'][:60]}...")
            art["title_zh"] = translate(art["title"])
            art["abstract_zh"] = translate(art["abstract"])
            time.sleep(0.5)

        # AI 设计启发总结
        if ZHIPU_API_KEY:
            log.info(f"  开始生成 AI 设计启发...")
            for i, art in enumerate(articles):
                log.info(f"    {i+1}/{len(articles)}: {art['title'][:60]}...")
                art["insight"] = generate_insight(art["authors"].split(",")[0].strip(), art["journal"], art["title"], art["abstract_zh"])
                time.sleep(0.5)
        else:
            log.info("  未配置 ZHIPU_API_KEY，跳过 AI 总结")

        all_results.append({"topic_zh": topic["name_zh"], "articles": articles})

    if not any_new:
        log.info("没有新文献，跳过推送")
        print("NO_NEW_PAPERS")
        return

    # 去重限流
    state["sent_pmids"] = state["sent_pmids"][-1000:]
    save_state(state)

    # 构建邮件
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    total = sum(len(r["articles"]) for r in all_results)
    topic_names = " / ".join(r["topic_zh"] for r in all_results); subject = f"[{topic_names}] 顶刊日报 {today_str} ({total}篇)"
    html_content = build_email_html(all_results, search_days)

    send_email(subject, html_content)
    log.info(f"✅ 完成！共推送 {total} 篇到 {', '.join(RECEIVER_EMAILS)}")


if __name__ == "__main__":
    main()

