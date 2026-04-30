# Pro.-AM

自动从 PubMed 检索 **CAR-M（嵌合抗原受体巨噬细胞）** 顶刊文献，提取标题与摘要，每日定时翻译并推送至邮箱。

## 功能

- 🔍 每日自动检索 PubMed 最新文献
- 🌐 标题 + 摘要自动翻译为中文
- 🤖 AI 智能摘要（GLM-4-Flash，基于作者/期刊/标题/摘要生成中文解读）
- 📊 自动查询期刊 SCI/JCI/JCI5/中科院分区（EasyScholar）
- 📧 邮件推送至 persist2021@163.com
- 🔁 自动去重，不会重复推送
- 🤖 GitHub Actions 定时运行（北京 07:30）
- 📄 无摘要文章自动跳过
- 🔀 Fallback 机制：顶刊查询无新文献时自动降级到广泛检索

## 检索模块

| 模块 | 主题 | 推送时间（北京） |
|------|------|-----------------|
| 1 | CAR-M（嵌合抗原受体巨噬细胞） | 07:30 |

### 检索式

**主检索（限定 77 本中科院 1 区顶刊）：**

```
("chimeric antigen receptor macrophage*"[Title/Abstract] OR 
 "CAR macrophage*"[Title/Abstract] OR 
 "CAR-M"[Title/Abstract] OR 
 "CAR-Mac"[Title/Abstract] OR 
 "chimeric antigen receptor"[Title] AND "macrophage*"[Title])
```

**Fallback 检索（不限期刊，顶刊无新文献时自动触发）：**

```
"chimeric antigen receptor macrophage*"[Title/Abstract] OR 
"CAR macrophage*"[Title/Abstract] OR 
"CAR-M"[Title/Abstract] OR 
"CAR-Mac"[Title/Abstract] OR 
("chimeric antigen receptor"[Title] AND "macrophage*"[Title])
```

所有模块均限定 **77 本中科院 1 区期刊**（详见 config_base.py）。

## 使用

1. Fork 或 Clone 本仓库
2. 在仓库 Settings → Secrets and variables → Actions → New repository secret 中添加：
   - `SMTP_AUTH_CODE` — 163 邮箱 SMTP 授权码
   - `ZHIPU_API_KEY` — 智谱 AI API Key（用于 AI 智能摘要，可选）

## 项目结构

```
Pro.-AM/
├── config_base.py          # 共享配置（期刊白名单、邮箱）
├── config_car_m.py         # CAR-M 检索词 + fallback 检索词
├── pubmed_fetcher.py       # 共享爬取代码
├── README.md
└── .github/workflows/
    └── car_m.yml           # CAR-M 定时任务
```

## 依赖

```bash
pip install biopython deep-translator requests
```

## 手动运行

```bash
python pubmed_fetcher.py --config config_car_m
```
