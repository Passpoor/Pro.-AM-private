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


# ---------- 智谱 GLM 设计启发总结 ----------

INSIGHT_PROMPT = """你是一名CAR-M（嵌合抗原受体巨噬细胞）领域的资深研究员。请基于以下文献标题和中文摘要，从两个维度总结设计启发：

1. **递送方式：** 文中使用了什么方法将CAR基因导入巨噬细胞？是否有新型载体、体内递送策略、或递送优化方案？
2. **CAR-M 结构设计：** 文中CAR的结构特点是什么？靶向什么抗原？采用了什么信号域/共刺激域？是否有结构创新？

要求：
- 只提取摘要中明确提到或可合理推断的信息，不要编造
- 简洁精炼，每个维度2-3句话
- 如果某个维度在摘要中无法提取，写"摘要中未明确提及"
- 用中文回答，格式严格如下：

**💡 递送方式：** xxx
**🧬 CAR-M 结构设计：** xxx

标题：{title}
摘要：{abstract}"""


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


def generate_insight(title: str, abstract_zh: str) -> str:
    """生成 CAR-M 设计启发总结"""
    if not ZHIPU_API_KEY:
        return ""
    prompt = INSIGHT_PROMPT.format(title=title, abstract=abstract_zh)
    return call_zhipu(prompt)


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

    html_parts = [f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #333; max-width: 780px; margin: 0 auto; padding: 24px; background: #f4f6f9; }}

.header {{ background: linear-gradient(135deg, #1a5276, #2e86c1); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 8px; }}
.header h1 {{ margin: 0 0 6px 0; font-size: 22px; letter-spacing: 0.5px; }}
.header .summary {{ font-size: 14px; opacity: 0.9; }}

.section-title {{ font-size: 18px; font-weight: 700; color: #1a5276; margin: 28px 0 4px 0; padding: 10px 0 6px 12px; border-left: 4px solid #2e86c1; }}
.section-meta {{ font-size: 12px; color: #888; margin: 0 0 12px 16px; }}

.paper {{ background: #fff; border-radius: 10px; padding: 20px 24px; margin: 14px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.06); border-left: 5px solid #2e86c1; transition: box-shadow 0.2s; }}
.paper:hover {{ box-shadow: 0 3px 12px rgba(0,0,0,0.1); }}

.paper-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
.paper-num {{ background: #2e86c1; color: #fff; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; }}
.paper-link {{ font-size: 12px; }}
.paper-link a {{ color: #2e86c1; text-decoration: none; border: 1px solid #d4e6f1; padding: 3px 10px; border-radius: 12px; }}
.paper-link a:hover {{ background: #2e86c1; color: #fff; }}

.tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.tag {{ font-size: 11px; padding: 2px 10px; border-radius: 10px; color: #555; }}
.tag-journal {{ background: #eaf2f8; color: #1a5276; font-weight: 600; }}
.tag-date {{ background: #fef9e7; color: #7d6608; }}
.tag-author {{ background: #f4ecf7; color: #6c3483; }}

.title-en {{ font-size: 17px; font-weight: 700; color: #1a1a2e; line-height: 1.5; margin: 10px 0 6px 0; }}

.zh-section {{ margin-top: 6px; padding-top: 6px; border-top: 1px dashed #ddd; }}
.title-zh {{ font-size: 16px; color: #555; line-height: 1.5; margin: 6px 0; text-align: justify; font-weight: 700; }}
.abstract-zh {{ font-size: 13px; color: #666; line-height: 1.7; margin-top: 6px; text-align: justify; padding: 10px 14px; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #2e86c1; }}

.insight-box {{ margin-top: 10px; padding: 12px 16px; background: linear-gradient(135deg, #fef9e7, #fdebd0); border-radius: 8px; border-left: 4px solid #f39c12; font-size: 13px; color: #7d6608; line-height: 1.7; }}
.insight-box strong {{ color: #b7950b; }}

.footer {{ text-align: center; color: #bbb; font-size: 11px; margin-top: 32px; padding: 16px 0; border-top: 1px solid #e5e8e8; }}
</style></head><body>

<div class="header">
  <h1>🔬 CAR-M 顶刊日报</h1>
  <div class="summary">📅 {today_str} &nbsp;&nbsp;|&nbsp;&nbsp; 🔍 近 {search_days} 天 &nbsp;&nbsp;|&nbsp;&nbsp; 📊 共 {total} 篇</div>
</div>

"""]

    for result in all_results:
        topic_zh = result["topic_zh"]
        articles = result["articles"]
        html_parts.append(f'<div class="section-title">{html.escape(topic_zh)}</div>\n')
        html_parts.append(f'<div class="section-meta">{len(articles)} 篇文献</div>\n')

        for i, art in enumerate(articles, 1):
            title_zh = art.get("title_zh", "")
            abstract_zh = art.get("abstract_zh", "")
            insight = art.get("insight", "")
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{art['pmid']}/"

            insight_html = ""
            if insight and "失败" not in insight:
                insight_html = f'<div class="insight-box">{insight}</div>\n'

            html_parts.append(f"""\
<div class="paper">
  <div class="paper-head">
    <span class="paper-num">{i}</span>
    <span class="paper-link"><a href="{pubmed_url}" target="_blank">PubMed 🔗</a></span>
  </div>
  <div class="tags">
    <span class="tag tag-journal">📖 {html.escape(art['journal'] or 'Unknown')}</span>
    <span class="tag tag-date">📆 {html.escape(art['date'] or '—')}</span>
    <span class="tag tag-author">✍️ {html.escape(art['authors'] or '—')}</span>
  </div>
  <div class="title-en">{html.escape(art['title'])}</div>
  <div class="zh-section">
    <div class="title-zh">{html.escape(title_zh)}</div>
    <div class="abstract-zh">{html.escape(abstract_zh)}</div>
  </div>
  {insight_html}
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
            log.info(f"  {topic['name_zh']} 无新文献")
            continue

        pmids_to_fetch = new_pmids[:topic["max_results"]]
        log.info(f"  准备推送 {len(pmids_to_fetch)} 篇")

        # 获取详情 + 翻译
        articles = fetch_details(pmids_to_fetch)
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
                art["insight"] = generate_insight(art["title"], art["abstract_zh"])
                time.sleep(0.5)
        else:
            log.info("  未配置 ZHIPU_API_KEY，跳过 AI 总结")

        all_results.append({"topic_zh": topic["name_zh"], "articles": articles})
        state["sent_pmids"].extend(pmids_to_fetch)
        any_new = True

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
