# Pro.-AM

面向 CAR-M（嵌合抗原受体巨噬细胞）研究的个人文献雷达。项目按 PubMed 入库日期增量检索文献，提取结构化研究信息，生成中文 HTML 摘要并定时投递。

## 当前管线

1. GitHub Actions 每日触发，读取独立 `state` 分支中的运行状态。
2. 使用 CAR-M 关键词和期刊白名单检索 PubMed；主检索无新结果时启用宽泛检索。
3. 以 PMID 去重，并通过 Biopython MEDLINE 解析题录、作者、DOI、摘要、MeSH 和文献类型。
4. 可选查询 EasyScholar 期刊指标。
5. 可选调用智谱模型，直接依据英文摘要提取相关性、靶点、细胞来源、递送方式、CAR 设计、模型、发现、局限和证据原句。
6. 翻译标题和摘要；翻译失败时保留英文，不阻断主流程。
7. 生成 HTML 邮件并通过 SMTP 投递。
8. 只有投递成功后才标记为 `delivered`；失败内容保留为 `pending`，下次直接重试，不重复调用分析服务。

## 可靠性设计

- 使用 PubMed `EDAT` 做真正的增量监测；仅在空状态首次启动时回溯 90 天。
- 状态支持 `pending`、`delivered`、`skipped_no_abstract`、`excluded_low_relevance`，并自动迁移旧版 `sent_pmids`。
- 状态保存在独立 `state` 分支，不再向 `main` 写入每日机器人提交。
- 邮件、智谱、翻译和期刊排名相互解耦；可选增强失败不会破坏 PubMed 主流程。
- `--dry-run` 不发送、不写状态，可安全检查真实检索结果。
- Actions 运行前执行离线测试，并将结果写入 Job Summary。

## 本地运行

需要 Python 3.11+。

```bash
python -m venv .venv
pip install -r requirements-dev.txt
```

复制 `.env.example` 中的变量到自己的环境。最少需要为真实邮件投递配置：

- `NCBI_EMAIL`
- `SENDER_EMAIL`
- `RECEIVER_EMAILS`，多个地址以逗号分隔
- `SMTP_AUTH_CODE`

智谱、EasyScholar 和 NCBI API Key 均为可选项。

先执行测试和小规模预览：

```bash
python -m unittest discover -s tests -v
python pubmed_fetcher.py --config config_car_m --dry-run --limit 3
```

预览默认写入 `digest_preview.html`。确认后真实运行：

```bash
python pubmed_fetcher.py --config config_car_m
```

## GitHub 配置

在仓库 Actions Secrets 中配置：

- `SMTP_AUTH_CODE`：必需，163 邮箱 SMTP 授权码
- `ZHIPU_API_KEY`：可选
- `EASYSCHOLAR_KEY`：可选
- `NCBI_API_KEY`：可选

在 Actions Variables 中配置：

- `NCBI_EMAIL`
- `SMTP_SERVER`
- `SMTP_PORT`
- `SENDER_EMAIL`
- `RECEIVER_EMAILS`

定时任务为 UTC 23:30，即北京时间约 07:30。GitHub Actions 的计划任务可能存在排队延迟。

## 检索策略

主检索仍使用 CAR-M 关键词和领域期刊白名单。主检索没有尚未处理的论文时，自动执行不限期刊的宽泛查询。检索配置位于 `config_car_m.py`，期刊名单位于 `config_base.py`。

本项目用于科研信息发现和初筛，不用于临床决策。模型输出必须结合 PubMed 原始摘要或全文核验。
