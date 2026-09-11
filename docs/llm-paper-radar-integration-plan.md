# CiteMap 集成 LLM Paper Radar 功能方案

> 更新日期：2026-09-09
> 参考项目：[llm-paper-radar](https://github.com/zhaolin-amd/llm-paper-radar/)
> 目标：把外部项目的深度筛选、摘要、趋势分析能力集成到 CiteMap 的项目雷达，不复制其独立仓库架构。

## 1. 结论

### 1.1 关键产品边界：Radar 与 Explore 分离

外部项目与 CiteMap 当前 Radar 的根本差别：

```text
llm-paper-radar：独立主题雷达，不依赖本地项目论文
CiteMap Radar：基于已有项目 corpus 的个性化推荐
```

两种推荐不能共用同一个入口、同一套解释、同一个排序语义。建议拆成两个并列产品面：

| 入口 | 推荐依据 | 目标 | 是否依赖项目 |
|---|---|---|---|
| `雷达 Radar` | 项目论文、项目描述、anchor papers、项目反馈 | 找到“适合这个研究项目”的论文 | 是 |
| `探索 Explore` | 独立主题、关键词、来源热度、watched authors、venues | 找到“值得关注的新论文” | 否 |

命名建议：

- 首选：`雷达` + `探索`
- 偏研究工作流：`项目雷达` + `论文探索`
- 不建议：把独立流命名为 `Trending`。Trending 只是 Explore 中的一种排序或分组，不是完整产品能力。
- 不建议：使用 `Safari` 作为正式入口。它有浏览器产品联想，研究工具语义不明确。

推荐的导航结构：

```text
发现
├── 探索       独立主题、多源、热度、日报
└── 雷达       选择项目后，基于项目 corpus 推荐

研究
├── 论文
├── 图谱
├── 助手
└── 笔记
```

### 1.2 两条数据流

```text
Explore
多源采集 → dedupe → prefilter → LLM judge → bucket → heat ranking
         → digest → 用户 triage → 加入项目 / 稍后处理

Radar
项目 corpus + project profile → 候选采集 → semantic ranking
                              → LLM judge → project fit ranking
                              → 推荐 → 入库 / 笔记 / Map
```

共享：候选 canonical record、AI summary、来源元数据、用户 triage、远端同步、邮件。

隔离：推荐输入、评分含义、配置、默认页面、统计指标。

`llm-paper-radar` 的核心竞争力不是 arXiv 抓取。核心是：

```text
多源采集
→ 去重
→ 本地关键词预筛
→ LLM 结构化判断
→ 主题分桶与热度排序
→ 中文 / English 摘要
→ 每日、每周、会议趋势产物
→ 人工接受 / 拒绝反馈
```

CiteMap 已有：

- 项目级兴趣画像
- arXiv 候选抓取
- embedding 排序
- anchor papers
- 中文 TLDR、AI 摘要、核心贡献、方法、结果、局限性
- 雷达状态：`unread`、`read`、`saved`、`dismissed`
- Cloudflare Worker + D1 离线存储
- GitHub Actions 定时执行
- SMTP 邮件
- Paper、Note、Map、Chat 之间的本地关系

因此适合采用以下定位：

```text
llm-paper-radar = 深度论文筛选与日报方法
CiteMap = 项目画像驱动的个人研究工作区
```

集成后，CiteMap 的发现层应成为：

```text
探索 → 判断 → 批量审阅 → 选择项目 → 入库 → 关联已有论文 → 写入笔记 → 进入 Map

`Radar` 则保持更窄的任务：

```text
项目 corpus → 个性化匹配 → 解释为什么适合项目 → 入库
```
```

## 2. 外部项目的功能拆解

### 2.1 多源采集

当前外部项目支持四类来源：

| 来源 | 价值 | CiteMap 集成建议 |
|---|---|---|
| arXiv | 论文主来源，支持按日期、category 抓取 | 已有，抽象成统一 `RadarSource` |
| HF Daily | 发现社区热度高、已被关注的论文 | P1 集成，保留 `trending_rank`、`upvotes`、`github_stars` |
| OpenReview | 会议投稿 / accepted paper / venue 数据 | P1 集成，先做 accepted paper 与会议趋势 |
| watched authors | 关注作者白名单 | P0 集成，适合项目级作者关注 |

多源结果按 arXiv ID 去重。来源信息不丢失。推荐结果可显示“来自 arXiv + HF Daily + 关注作者”。

### 2.2 两阶段筛选

#### Stage 1：本地 keyword prefilter

先用白名单、黑名单过滤明显噪声：

- 无 whitelist 命中
- blacklist 命中数达到阈值
- 直接 hard gate
- 不消耗 LLM 调用

收益：降低成本、降低 LLM 噪声、提高规则可审计性。

#### Stage 2：LLM structured judge

外部项目使用两个评分轴：

| 评分轴 | 范围 | 判断内容 |
|---|---:|---|
| `topic_relevance` | 0-5 | 论文是否直接属于目标研究主题 |
| `practicality` | 0-5 | 方法复杂度、校准成本、显存、推理收益、部署可行性 |

两个分数相加形成 `relevance_score`。LLM 同时输出：

- `hard_gate`
- `topic_bucket`
- `compression_type`
- `model_domain`
- `format_or_method`
- `largest_model_tested`
- `accuracy_benchmarks`
- `accuracy_summary`
- `inference_perf`
- `calibration_cost`
- `peak_memory`
- `reason`

CiteMap 当前只保存一个相似度分数。应新增结构化判断结果。相似度回答“像不像当前项目”。结构化 judge 回答“值不值得读、为什么值得读”。

### 2.3 Topic bucket

外部项目把论文分为固定主题桶，例如：

- PTQ
- Low-bit
- QAT
- KV cache
- Pruning & distillation
- Diffusion
- Trending
- Survey

CiteMap 不应固定使用这些桶。桶应由项目画像定义。默认提供通用桶：

```text
method
model / architecture
dataset / benchmark
system / serving
theory / analysis
survey / benchmark
trending
```

项目可自定义桶。例如：

```text
LLM Inference 项目：Quantization、KV cache、Speculative decoding、Serving
Multimodal 项目：VLM、Video、3D、Dataset、Evaluation
Agent 项目：Planning、Tool use、Memory、Evaluation
```

### 2.4 热度排序

外部项目把 LLM 相关性作为主排序，再用外部热度做 tie-break：

```text
final_score
= relevance_score × relevance_weight
  + hf_daily_bonus
  + github_star_bonus
  + trending_bonus
```

CiteMap 建议保存两类分数：

```text
semantic_score：项目语义相似度
judge_score：LLM 主题相关性 + 实用性
heat_score：HF Daily、GitHub、来源数量、近期引用信号
final_score：用于默认列表排序
```

不要将热度与相关性混成一个不可解释的分数。UI 直接展示分数组成。

### 2.5 深度摘要

外部项目摘要阶段输出：

- 中文摘要
- English 摘要
- highlights
- related methods
- compared baselines
- relevance reason 的 English sibling
- inference performance、calibration cost 的 English sibling

CiteMap 已有中文字段。建议补齐：

- `summary_en`
- `highlights`
- `related_methods`
- `compared_baselines`
- `benchmark_results`
- `deployment_notes`
- `summary_version`
- `summary_model`

### 2.6 每日、每周、长期 digest

外部项目输出：

- 每日 compact table
- 每日 detail page
- 每周 rollup
- monthly / half-year / yearly snapshot

CiteMap 不应把 Markdown 文件作为主数据源。建议：

```text
SQLite / Radar Store = 主数据
前端 Digest 页面 = 主展示
Markdown export = 可选产物
```

这样可以直接和项目、论文、笔记、Map 关联。邮件使用同一份 digest 查询结果生成。

### 2.7 人工 triage

外部项目通过人工审核：

- accept
- reject
- 调整 blacklist
- 写入 seeds

CiteMap 可把它升级为正式反馈闭环：

```text
保存 → 正向反馈
忽略 → 负向反馈
批量接受 → 主题偏好反馈
修改主题桶 → 分类反馈
```

后续用于：

- 调整项目画像
- 调整关键词权重
- 评估 Precision@K
- 训练项目级 rerank profile

## 3. 和 CiteMap 的功能映射

### 3.0 功能归属

| 功能 | Explore | Radar | 共享能力 |
|---|---:|---:|---:|
| arXiv / HF Daily / OpenReview 多源采集 | ✓ | 可复用候选 | source adapters |
| 项目 corpus semantic ranking |  | ✓ | embedding runtime |
| 独立主题 LLM judge | ✓ |  | judge runtime |
| 项目适配 LLM judge |  | ✓ | judge runtime |
| hard gate | ✓ | ✓ | rule engine |
| topic bucket | 全局主题桶 | 项目主题桶 | bucket schema |
| heat ranking | 主排序因子 | 次要 tie-break | heat signals |
| watched authors | 主筛选条件 | 项目辅助条件 | author identity |
| Daily / Weekly digest | ✓ | 可选项目周报 | digest renderer |
| 人工 triage | 主要入口 | 反馈项目匹配 | feedback store |
| Paper River | 单篇探索 | 单篇项目论文 | async job |
| venue trend | ✓ | 可关联项目 | async job |

### 3.1 Explore 的产品定义

Explore 是一个全局研究发现层。它不要求当前项目有论文，不读取项目 corpus 作为推荐基础。

Explore 配置：

- 独立主题描述，例如“LLM 推理优化与模型压缩”
- arXiv categories
- whitelist / blacklist
- watched authors
- watched venues
- 来源开关
- topic buckets
- heat ranking 权重
- 每日 / 每周 digest

Explore 结果默认进入“待处理队列”，不进入任何项目。用户操作：

```text
保存到稍后处理
→ 标记已读
→ 忽略并选择原因
→ 加入一个或多个项目
→ 创建独立 Note
→ 生成 Paper River
```

### 3.2 Radar 的产品定义

Radar 是项目内的个性化推荐层。进入页面前必须选择一个普通项目。项目的论文、描述、anchor papers 组成 recommendation context。

Radar 配置：

- 项目研究目标
- project corpus
- anchor papers
- 项目 categories
- 项目 include / exclude keywords
- 项目主题桶
- semantic / judge / heat 权重
- Top K、最低分数

Radar 不应显示全局探索的“热门论文大盘”。它只显示与当前项目匹配的结果。来源热度只用于相似论文分数接近时排序。

| 外部能力 | CiteMap 当前状态 | 集成动作 | 优先级 |
|---|---|---|---|
| arXiv source | 已有 | 抽象 source interface，保留现有实现 | P0 |
| keyword prefilter | 只有 include / exclude keyword | 作为共享 rule engine，Explore 与 Radar 使用独立规则 | P0 |
| LLM 两轴评分 | 没有 | 新增 `RadarJudge`，区分 Explore judge 与 project-fit judge | P0 |
| topic bucket | 没有 | 全局 Explore bucket、项目 Radar bucket 分开定义 | P0 |
| hard gate | 没有统一结果 | 保存 gate、命中规则、LLM reason | P0 |
| watched authors | 没有 | 项目级作者关注列表 | P0 |
| anchor papers | 已有 | 作为 judge context 与 semantic reference | P0 |
| embedding ranking | 已有 | 作为 semantic_score，不替代 judge | P0 |
| HF Daily | 没有 | 新 source adapter 与热度字段 | P1 |
| OpenReview | 没有 | 新 source adapter、venue 字段 | P1 |
| bilingual summary | 中文摘要已有 | 增加 English、highlights、related methods | P1 |
| heat ranking | 没有 | 保存独立 heat signals | P1 |
| daily digest | Radar 列表已有 | 增加 Explore digest，Radar 只保留项目 digest | P1 |
| weekly rollup | 没有 | 增加周报查询与 Markdown export | P1 |
| triage feedback | 状态只有 saved / dismissed | 增加反馈类型与备注 | P1 |
| watched author section | 没有 | Radar 筛选器与专门分组 | P1 |
| Paper River | 历史外部 skill 已恢复并改为 OpenAI-compatible | 先做“论文溯源”任务入口，不自动批量运行 | P2 |
| venue trend report | 没有 | 独立的会议分析任务 | P2 |
| GitHub Markdown auto-commit | 不需要 | 改为 SQLite + 可选 Markdown 导出 | 不集成 |

## 4. 推荐的数据模型

当前 `radar_configs`、`radar_runs`、`radar_candidates`、`radar_matches` 可以继续使用。优先扩展，不新增平行数据库。关键是给推荐任务增加 `scope`，避免 Explore 与 Radar 混在一起。

### 4.0 推荐任务 scope

```text
scope = explore
scope = project
```

`project` scope 必须有 `project_id`。`explore` scope 使用全局 Explore profile，可没有项目。

建议新建统一任务表，或先在现有表中增加字段：

```text
radar_runs.scope             explore | project
radar_runs.project_id        nullable for explore
radar_runs.profile_id        explore profile or project profile
radar_matches.scope          explore | project
radar_matches.project_id     nullable for explore
```

候选论文可共享。匹配结果不能共享。相同论文可能：

```text
Explore match：Trending，热度 0.92
Project match：项目相关性 4.7，语义分数 0.81
```

两条记录各自保存状态。Explore 中忽略，不应自动忽略项目 Radar 中的同一篇论文。

### 4.1 Explore profile

建议新增 `explore_profiles`：

```text
id
name
description
enabled
source_config JSON
prefilter_config JSON
judge_config JSON
topic_buckets JSON
score_weights JSON
watched_authors JSON
watched_venues JSON
digest_config JSON
updated_at
```

首版只支持一个默认 Explore profile。数据模型预留多个 profile，后续可做“LLM 推理优化”“多模态”“Agent”多个独立探索流。

### 4.2 `radar_configs` 扩展

建议新增字段：

```text
source_config              JSON
prefilter_config           JSON
judge_config               JSON
topic_buckets              JSON
score_weights              JSON
watched_authors            JSON
watched_venues             JSON
digest_config              JSON
feedback_learning_enabled  BOOLEAN
```

其中：

```json
{
  "source_config": {
    "arxiv": {"enabled": true, "categories": ["cs.CL", "cs.LG"]},
    "hf_daily": {"enabled": true},
    "openreview": {"enabled": false, "venues": []},
    "authors": {"enabled": true}
  },
  "prefilter_config": {
    "enabled": true,
    "max_blacklist_hits": 2,
    "whitelist": [],
    "blacklist": []
  },
  "score_weights": {
    "semantic": 0.45,
    "judge": 0.45,
    "heat": 0.10
  }
}
```

### 4.3 `radar_candidates` 扩展

建议新增：

```text
source_records              JSON
external_ids                JSON
code_url                    TEXT
code_meta                   JSON
trending_rank               INTEGER
hf_upvotes                  INTEGER
github_stars                INTEGER
venue                       TEXT
venue_status                TEXT
watch_author_matches        JSON
prefilter_whitelist_hits    JSON
prefilter_blacklist_hits    JSON
```

### 4.4 `radar_matches` 扩展

建议新增：

```text
semantic_score              REAL
topic_relevance             INTEGER
practicality                INTEGER
judge_score                 REAL
heat_score                  REAL
final_score                 REAL
topic_bucket                TEXT
hard_gate                   BOOLEAN
judge_breakdown             JSON
recommendation_reason       TEXT
feedback                    TEXT
feedback_note               TEXT
```

`score` 旧字段暂时保留，迁移期间映射到 `final_score`。

### 4.5 新增 `radar_digests`

日报与周报不应每次由前端临时拼接。建议保存运行快照：

```text
id
project_id
scope                 explore | project
digest_type          daily | weekly | monthly | venue
period_start
period_end
payload_json
created_at
```

日报内容可以重新渲染。历史结果保持稳定。模型升级后可重新生成新版本，不覆盖旧版本。

## 5. 评分架构

### 5.1 P0 推荐链路

```text
source adapters
  ├─ arXiv
  ├─ watched authors
  └─ local project corpus
        ↓
dedupe by canonical_id
        ↓
keyword prefilter
        ↓
embedding semantic score
        ↓
LLM judge
  ├─ topic_relevance 0-5
  ├─ practicality 0-5
  ├─ hard_gate
  ├─ topic_bucket
  └─ structured evidence
        ↓
heat signals
        ↓
final ranking
        ↓
summary enrichment
        ↓
Radar list / Digest / Email / Paper ingest
```

### 5.2 不建议的评分顺序

不要先让 LLM 总结全部候选，再筛选。成本高，噪声大。

不要只用 embedding。embedding 适合相似度，不适合判断：

- 是否真的属于项目主题
- 是否有可复现价值
- 是否需要大规模训练
- 是否存在部署路径
- 是否只是 benchmark 或观点论文

### 5.3 LLM 模型配置建议

CiteMap 统一使用 OpenAI-compatible API。外部实现只复用 Prompt、schema 与算法，不引入第二套 LLM SDK。

建议拆分模型角色：

| 任务 | 默认模型 | 备选 |
|---|---|---|
| keyword prefilter | 本地 Python | 无 |
| embedding | local SentenceTransformer | OpenAI-compatible embeddings API |
| judge | 当前 `LLM_MODEL` 或低成本模型 | 更强模型 |
| summary | 当前 `LLM_MODEL` | 更强模型 |
| venue trend | 强模型 | 手动执行 |

首版可使用同一个模型。调用参数保持结构化 JSON、低温度、重试、错误可诊断。

## 6. 配置清单

### 6.1 本地 `backend/.env`

已有配置可继续使用：

```env
LLM_API_KEY=your-openai-compatible-api-key
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=gpt-5.5
```

新增建议：

```env
RADAR_LLM_ENABLED=true
RADAR_LLM_REQUIRED=false
RADAR_JUDGE_MODEL=gpt-5.5
RADAR_SUMMARY_MODEL=gpt-5.5

RADAR_EMBEDDING_PROVIDER=local
RADAR_EMBEDDING_MODEL=jinaai/jina-embeddings-v5-text-nano-retrieval
RADAR_EMBEDDING_TASK=retrieval
RADAR_EMBEDDING_PROMPT_NAME=document
RADAR_EMBEDDING_TRUST_REMOTE_CODE=true
RADAR_EMBEDDING_BATCH_SIZE=64

RADAR_ARXIV_USER_AGENT=CiteMap/0.4 mailto:your-email@example.com
RADAR_REQUEST_TIMEOUT=45
RADAR_MAX_CONCURRENCY=20
```

说明：

- `RADAR_EMBEDDING_PROVIDER=local` 需要下载模型。首次运行耗时较长。
- 本地模型适合个人库。GitHub Actions 需要 Hugging Face cache。
- `RADAR_EMBEDDING_PROVIDER=api` 需要 `RADAR_EMBEDDING_API_KEY`、`RADAR_EMBEDDING_BASE_URL`。
- `lexical` 只用于测试、无模型环境。正式推荐不应默认使用。
- `RADAR_LLM_REQUIRED=false` 可让抓取、embedding、基础推荐在 LLM 故障时继续运行。推荐 UI 显示“等待 AI 评估”。

### 6.2 GitHub Actions Secrets

现有 CiteMap Radar 已需要：

| Secret | 用途 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Worker 部署 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 |
| `CLOUDFLARE_D1_DATABASE_ID` | D1 数据库 |
| `RADAR_REMOTE_TOKEN` | Worker 访问 |
| `RADAR_REMOTE_URL` | Worker 地址 |
| `RADAR_EMAIL_SENDER` | 发件邮箱 |
| `RADAR_EMAIL_RECEIVER` | 收件邮箱 |
| `RADAR_EMAIL_PASSWORD` | SMTP 授权码 / App Password |
| `LLM_API_KEY` | judge、summary |

新增多源能力后：

| Secret / Variable | 是否必需 | 用途 |
|---|---|---|
| `RADAR_EMBEDDING_API_KEY` | API embedding 时必需 | embedding API |
| `RADAR_EMBEDDING_BASE_URL` | API embedding 时必需 | embedding endpoint |
| `OPENREVIEW_EMAIL` | OpenReview 受限时可选 | OpenReview login |
| `OPENREVIEW_PASSWORD` | OpenReview 受限时可选 | OpenReview login |
| `RADAR_HF_TOKEN` | 视 HF endpoint 需要 | HF API 访问 |

不要把这些 Secret 放进前端配置、SQLite、项目 profile。Worker 只接收项目 profile、推荐结果、用户状态。

### 6.3 GitHub Actions Variables

```text
RADAR_SMTP_HOST=smtp.qq.com
RADAR_SMTP_PORT=465
RADAR_EMBEDDING_PROVIDER=local
RADAR_EMBEDDING_MODEL=jinaai/jina-embeddings-v5-text-nano-retrieval
RADAR_EMBEDDING_TASK=retrieval
RADAR_EMBEDDING_PROMPT_NAME=document
RADAR_EMBEDDING_TRUST_REMOTE_CODE=true
RADAR_EMBEDDING_BATCH_SIZE=64
RADAR_JUDGE_MODEL=gpt-5.5
RADAR_SUMMARY_MODEL=gpt-5.5
RADAR_LLM_REQUIRED=true
RADAR_DEBUG=false
```

### 6.4 数据源配置

建议放入项目配置，不放入全局环境变量：

```json
{
  "arxiv": {
    "categories": ["cs.CL", "cs.LG", "cs.AI"],
    "include_cross_list": true
  },
  "hf_daily": {
    "enabled": true,
    "min_rank": 100
  },
  "openreview": {
    "enabled": false,
    "venues": ["ICLR.cc/2027/Conference", "NeurIPS.cc/2026/Conference"]
  },
  "watched_authors": [
    {"name": "作者名", "affiliation": "机构名"}
  ]
}
```

## 7. UI 设计

### 7.1 Radar 页面定位

现有 Radar 页面已经具备入口、设置、结果列表、状态操作。Radar v2 建议改为研究审阅工作台：

```text
顶部：项目、日期、运行状态、来源、扫描 / 同步
左侧：视图与筛选
中间：推荐队列
右侧：论文详情 / judge evidence / 相关论文
```

不要使用大量同构大卡片。论文审阅需要列表密度、快速比较、连续操作。

### 7.2 顶部工具栏

```text
论文雷达 / 当前项目
今日  ·  未读  ·  已保存  ·  已忽略  ·  周报

[日期] [来源] [主题] [最低相关性] [排序：最终分数 ▼]

[同步云端] [立即扫描] [雷达设置]
```

运行状态放在顶部次级行：

```text
上次运行：今天 06:02 · arXiv 180 · HF Daily 62 · 去重 205 · 评估 42 · 推荐 10
```

### 7.3 左侧筛选栏

建议筛选项：

- 状态：未读、已读、已保存、已忽略
- 来源：arXiv、HF Daily、OpenReview、关注作者
- Topic bucket
- hard gate：默认隐藏，可切换显示
- topic relevance：0-5
- practicality：0-5
- 是否有 code
- 是否有 PDF
- venue
- 机构 / 作者

显示每个筛选项的数量。筛选状态写入 URL query，刷新不丢失。

### 7.4 中间推荐列表

单篇推荐使用紧凑行，不使用大面积摘要卡：

```text
┌─────────────────────────────────────────────────────────┐
│ [PTQ]  论文标题                                         │
│ 中文标题                                               │
│ arXiv ID · 2026-09-08 · arXiv + HF Daily · 有代码      │
│                                                         │
│ 最终 8.7   相关性 4.5   实用性 4.2   热度 0.8           │
│ 为什么推荐：与当前项目的 Quantization / KV cache 方向… │
│                                                         │
│ [标记已读] [保存入库] [忽略] [打开详情]                 │
└─────────────────────────────────────────────────────────┘
```

列表默认展示：

- bucket
- 标题、中文标题
- 来源、日期、作者
- `final_score` 及三个分数组成
- 一句 recommendation reason
- 状态
- code、PDF、关注作者图标

摘要、方法、结果放入详情抽屉。用户可连续浏览，不频繁跳页。

### 7.5 右侧详情抽屉

详情抽屉分为四块：

1. `Why this paper`
   - judge reason
   - semantic match reason
   - 命中的项目论文 / anchor papers
2. `AI summary`
   - TLDR
   - 中文摘要
   - English 摘要
   - highlights
3. `Evidence`
   - 主题相关性
   - 实用性
   - accuracy benchmark
   - inference performance
   - calibration cost
   - peak memory
   - model scale
4. `Related`
   - related methods
   - compared baselines
   - 当前项目内相似论文
   - 打开 Map、创建 Note、保存入库

Evidence 必须标记来源：`LLM extraction`、`arXiv metadata`、`PDF first page`、`HF Daily`。避免把模型推测展示成事实。

### 7.6 Digest 视图

新增 `/radar/digest` 或在 Radar 内切换：

- Daily
- Weekly
- Monthly
- Venue

Daily 结构：

```text
今日摘要
本次扫描统计
主题分组
每组精选论文
关注作者
热度上升
批量审阅操作
```

Weekly 结构：

- 本周新增趋势
- 重复出现的主题
- 最常见方法
- 新增作者 / 机构
- 论文数量变化
- 本周保存率、忽略率
- 进入项目的论文

### 7.7 Settings 页面

现有设置 Dialog 适合小量配置。Radar v2 建议改成全页设置，分四个 Tab：

```text
数据源
筛选规则
评分与 AI
邮件与云端
```

#### 数据源

- arXiv categories
- HF Daily 开关
- OpenReview venues
- watched authors
- 抓取窗口、最大候选数

#### 筛选规则

- whitelist
- blacklist
- 每条规则的 weight
- hard gate 规则
- 项目主题说明
- out-of-scope 说明

#### 评分与 AI

- semantic / judge / heat 权重
- judge model
- summary model
- temperature
- Top K
- 每个 bucket 上限
- 运行前预估 LLM 调用数

#### 邮件与云端

- Worker URL
- token
- 连接状态
- 最后同步时间
- digest 发送时间
- 部署文档链接

Secret 继续由 GitHub Actions 管理。前端只保存 Worker URL、token 的本地连接信息。

### 7.8 人工审阅交互

在列表中增加批量模式：

```text
[选择 12 篇] [批量保存] [批量忽略] [标记已读] [加入项目]
```

每次忽略可选原因：

- 不相关
- 重复
- 不实用
- 规模太小
- 缺少实验
- 只想保留到其他项目

原因用于后续统计。默认不强制填写，减少操作摩擦。

## 8. 实施顺序

### Phase 1：深度 judge，保持单源

目标：先验证推荐质量。

- 新增 keyword prefilter
- 新增 LLM 两轴评分
- 新增 hard gate、topic bucket、judge evidence
- semantic / judge / heat 分数拆分
- Radar 列表显示结构化分数
- 保存 judge JSON 与 prompt version
- 增加固定评测数据集

验收指标：

- Precision@5
- 保存率
- 忽略率
- judge JSON 解析成功率
- 单篇平均 LLM 成本

### Phase 2：多源与 watched authors

- 抽象 `RadarSource`
- 加入 watched authors
- 加入 HF Daily
- source attribution
- canonical ID 去重
- 来源筛选
- heat signal

### Phase 3：Digest 与人工反馈

- Daily / Weekly 页面
- Digest 快照
- 批量审阅
- 忽略原因
- feedback 统计
- Markdown、邮件复用同一 digest payload

### Phase 4：OpenReview 与 venue trend

- accepted paper source
- venue 页面
- 会议分组、主题计数
- LLM 生成趋势报告
- 报告关联项目论文、作者、机构

### Phase 5：Paper River / 深度溯源

Paper River 不默认开启，不加入每日 pipeline，不对所有推荐论文自动生成。只在具体论文详情页按需启动：

```text
论文详情 → 生成 Paper River
         → 创建分析任务
         → GitHub Action / worker 执行
         → 回写任务状态与结果
         → 论文详情 → 论文溯源
```

同一篇论文已有成功结果时显示：

```text
查看论文溯源 · 重新生成
```

不重复创建相同版本任务。重新生成必须明确触发。

实现难度：中等。业务逻辑简单，运行基础设施有要求。

需要处理：

- `queued`、`running`、`succeeded`、`failed`、`cancelled` 状态
- 长任务不阻塞 FastAPI 请求
- Action / worker 超时、重试、失败错误
- 结果写入本地 `data/` 或远端对象存储
- 中文 / English 结果文件关联
- 同一论文重复点击的幂等键
- 用户关闭 CiteMap 后重新打开仍能查看状态

推荐首版实现：

```text
PaperDetail
→ POST /api/papers/{paper_id}/analysis-jobs
→ 创建 paper_analysis_jobs
→ 触发 GitHub Actions workflow_dispatch
→ Action 调用 Paper River runner
→ POST /api/analysis-jobs/{job_id}/callback
→ CiteMap 轮询或 SSE 获取状态
```

外部 `scripts/auto_paper_river.py`、`scripts/gen_paper_river.sh` 可复用候选发现、文件命名、语言 sibling、失败继续策略。执行脚本不能直接放入 Web 请求线程。

自动化执行器统一使用 CiteMap 当前 OpenAI-compatible LLM Agent。保留同一 job contract，前端与数据模型不需要再次改动。

## 9. 暂不集成的部分

### 9.1 GitHub README 作为主 UI

外部项目以 GitHub Markdown 为产品界面。CiteMap 已有 React UI、SQLite、Paper、Note、Map。继续使用本地数据模型更合适。Markdown 只做 export。

### 9.2 历史 skills 适配

`paper-triage`、`paper-interpret`、`venue-trend`、`paper-river` 原本依赖特定 skill 运行环境。CiteMap 当前是 Web 应用，执行层统一适配到 OpenAI-compatible LLM 与 FastAPI job，避免额外 provider、权限、可复现性问题。

Paper River 与 Venue Trend 先统一为 `分析任务`。不是泛化成用户不可理解的“任务中心”。

```text
论文详情 → 分析任务 → Paper River
Explore   → 分析任务 → Venue Trend
```

再将其能力改造成后端 job：

```text
创建任务 → 后台运行 → 保存结果 → 前端查看
```

### 9.3 全量 bilingual

首版不必对所有字段生成中英文双份。建议：

- UI 默认中文
- 原文标题、作者、方法名保留 English
- English summary 作为详情页折叠内容
- 邮件只发送中文摘要，可设置双语开关

### 9.4 全量 OpenReview

OpenReview 的 venue、submission、review、rebuttal 数据边界复杂。先只抓 accepted paper。review 与 rebuttal 另做功能，不放入 Radar 主链路。

## 10. 代码复用方案

这次按“复用代码，适配边界”的方式处理。不是只参考思路，也不是把整个仓库原样嵌入 CiteMap。

### 10.1 可以直接复用或最小改造

| 外部文件 / 模块 | 复用内容 | CiteMap 适配点 |
|---|---|---|
| `sources/base.py` | `Paper`、`SourceRecord`、`Source` 抽象 | 映射为 Radar candidate DTO，不替换 CiteMap `Paper` 主表 |
| `sources/arxiv.py` | arXiv 日期抓取、User-Agent、429 / OAI fallback | 接入现有 Radar collection，输出统一 candidate |
| `sources/arxiv_authors.py` | 单 query watched authors、作者匹配 | 保存项目级或 Explore 级 author match |
| `sources/hf_daily.py` | HF Daily 页面解析、trending rank、upvotes、GitHub metadata | 写入 `source_records`、heat signals |
| `sources/openreview.py` | venue template、Submission 拉取、年份展开 | 先服务 Explore，accepted paper 进入 venue trend |
| `pipeline/dedupe.py` | canonical arXiv ID 去重、source attribution 合并 | 改为写 SQLite / Worker，不写 JSON 文件 |
| `pipeline/filter.py` | word-boundary prefilter、LLM 并发、JSON 容错、hard gate 结构 | 拆成共享 `prefilter` 与 Explore / Project 两个 judge |
| `pipeline/llm_client.py` | 请求重试、JSON 返回 | 接 CiteMap 现有 OpenAI-compatible LLM 配置，增加 model role |
| `pipeline/config.py` | Pydantic 配置结构、keyword rule、source config | 配置落到 Explore profile 与 project radar config |
| `pipeline/summarize.py` | 双语 summary、highlights、related methods 清洗 | 结果写入 `radar_candidates` / `radar_summaries` |

### 10.2 复用算法，不能原样搬运

| 外部能力 | 原因 | CiteMap 处理 |
|---|---|---|
| `pipeline/render.py` | 外部输出 GitHub Markdown，CiteMap 是 Web UI | 复用 bucket 排序、digest payload，不复用页面 renderer |
| `pipeline/weekly.py` | 外部从 JSON 文件扫描历史 | 改成 SQL 聚合、Digest snapshot |
| `pipeline/rollup_digest.py` | 同上 | 改成 API 返回 Daily / Weekly 数据 |
| `pipeline/venue_filter.py` | 会议 judge 与日常 topic judge 不完全相同 | 复用评分框架，保留独立 venue prompt |
| `pipeline/venue_group.py` | 分组结果适合会议报告 | 输出 `venue_report` 数据，不进入普通 Radar 列表 |
| `scripts/resolve_paper.py` | 本地文件结构不同 | 将 resolve 能力改成 CiteMap paper service |
| `scripts/auto_paper_river.py` | 依赖文件扫描、shell 调度 | 改成单篇后台 job、任务状态、结果文件 |
| `workflows/venue_trend_report.js` | 是 Agent workflow 描述，不是 Web runtime | 复用阶段、输出 schema、报告结构 |

### 10.3 不直接复用

- 外部仓库的 `data/`、`digests/`、`README.md` 产物。
- 外部仓库的 Git commit / push 作为业务流程。
- 历史 `paper-triage`、`paper-interpret`、`venue-trend` skill 运行时。
- `scripts/gen_paper_river.sh` 对本地 shell、特定 CLI、技能目录的假设。

这些内容绑定外部仓库运行环境。复制后维护成本高，不能自然接入 CiteMap 的 SQLite、FastAPI、SSE、Worker。

### 10.4 建议的代码落位

```text
backend/paper_graph/
├── discovery_sources.py       # source adapter registry
├── discovery_dedupe.py        # canonical ID + source merge
├── discovery_prefilter.py     # whitelist / blacklist
├── discovery_judge.py         # Explore judge + project-fit judge
├── discovery_summary.py       # bilingual summary
├── discovery_digest.py        # daily / weekly / venue payload
├── paper_river_jobs.py        # Paper River job contract
└── venue_trend.py             # venue fetch / group / report job
```

现有 `radar.py`、`radar_ranking.py`、`radar_embeddings.py`、`radar_sync.py` 继续保留。迁移期通过 adapter 调用新 discovery 模块，避免一次性重写现有本地 Radar。

### 10.5 许可证

外部仓库采用 MIT License。若复制其源代码或实质代码片段：

- 保留原版权声明
- 保留 MIT License 文本
- 在 CiteMap 的 `NOTICE` 或第三方说明中记录来源
- 标注哪些文件来自外部项目、哪些文件是 CiteMap 改造

CiteMap 使用 Apache License 2.0。MIT 代码可以并入 Apache 2.0 项目，必须保留 MIT notice 与 license。

## 10.6 Paper River 原始逻辑核对

`llm-paper-radar` 的 Paper River 不是一个内置 Python pipeline。它的日常脚本只负责扫描哪些论文需要生成，再逐篇调用 shell wrapper：

```text
data/summarized/*.json
→ 找到 hard_gate=false 的论文
→ 按 arXiv ID 去重
→ 检查 paper-river/*<id>.org 是否已存在
→ 调用 scripts/gen_paper_river.sh <arxiv-id>
→ 逐篇执行，不因单篇失败终止全部任务
```

原始 wrapper 的执行逻辑：

```text
提取 arXiv ID
→ 检查 dot / dash 两种文件名
→ 检查 OpenAI-compatible LLM 配置
→ 通过 CiteMap job runner 执行
→ 调用 /ljg-paper-river
→ 允许 WebSearch、WebFetch、Read、Write、Edit、Bash
→ 检查 .org 是否实际生成
→ 用论文真实标题回写 #+title
```

`/ljg-paper-river` 原始 skill 的核心方法：

1. 读取目标论文的摘要、引言、related work。
2. 找出目标论文明确批判、改进、对比的前序论文。
3. 沿最相关的一条引用 / 问题线递归，最多 5 层。
4. 每层记录：研究问题、前序缺陷、核心解法、新增局限。
5. 反向搜索目标论文之后的 1-3 篇后续工作。
6. 形成时间线：`最老论文 → 中间论文 → 目标论文 → 后续论文`。
7. 以问题演化为主线做 Feynman-style 正向叙事。
8. 输出溯源地图、演化叙事、前沿延伸、洞见、启发。

原始 skill 的写作约束：

- 问题是主角，论文不是论文摘要列表。
- 每个转折说明后者看到了前者的什么问题。
- 只追一条最相关的线，不发散到完整 citation graph。
- 找不到明确关系时停止，不能补造引用关系。
- 输出两张 ASCII 图：溯源地图、问题-解法总览。
- 目标是解释研究问题如何演化，不是证明 citation graph 完整。

当前状态：

- `ljg-paper-river` 曾在 `lijigang/ljg-skills` commit `de75385` 加入。
- 在 commit `fb6279e` 被列为 retired skill 并删除。
- `llm-paper-radar` 当前脚本仍调用 `/ljg-paper-river`。
- 最新 `lijigang/ljg-skills` 主分支中已经找不到该 skill。

因此不能把它当作稳定可安装依赖。可以复用：

```text
五层递归溯源逻辑
批判链线索提取
前沿延伸
问题演化叙事
两张 ASCII 图
Org 输出结构
幂等文件检查
失败继续策略
```

需要重做：

```text
OpenAI-compatible skill 调用
WebSearch / WebFetch 权限
本地 shell 写文件
~/Documents/notes/ 路径
Denote identifier
```

CiteMap 的单篇 Paper River 任务建议固定输入与输出：

```text
输入：paper_id、arxiv_id、目标语言、depth=5、prompt_version
输出：paper_river.md 或 paper_river.org、source list、relation confidence、生成时间
```

结果中应区分：

- `confirmed_relation`：论文原文明确引用、批判、改进。
- `inferred_relation`：基于摘要或引用网络推断，需标记不确定。
- `missing_relation`：没有找到可靠前序或后续工作。

这样可以把原始 skill 的“诚实标注”变成 CiteMap 可检索的数据，而不是只保存在一份长文本里。

## 11. 已冻结的产品语义与首版 UI

`/explore` 已作为独立一级入口进入生产页面。现有 Radar 页面继续只承担项目级推荐，不再承载独立发现。

已确认的 UI 决策：

```text
一级导航：探索 / 项目雷达 / 论文 / 图谱 / 助手 / 笔记
默认发现入口：探索
Digest：探索的子视图
Paper River：论文详情页按需启动
Venue Trend：探索内的分析任务
```

在 UI 继续设计前，先确定四个对象：

```text
Explore profile       独立探索主题
Project radar         项目级推荐
Digest                某个 profile / project 的周期汇总
分析任务              Paper River / Venue Trend 等重任务
```

首版 UI 已落地：

1. Explore 与 Project Radar 不共用业务状态，只复用基础 UI。
2. Explore 使用“今日简报 / 候选池 / 趋势”三个子视图。
3. 来源默认聚合，来源筛选只在候选池使用。
4. 候选只有人工选择“加入项目”后才写入正式论文库。
5. Paper River 入口只出现在单篇详情，不进入每日 pipeline。

当前实现状态：

```text
已完成  Explore schema、profile、候选、来源记录、Digest、趋势、triage API
已完成  arXiv + HF Daily 采集、canonical arXiv ID 去重、heat signals
已完成  Explore 页面、默认聚合、来源 / 主题 / 状态筛选、加入项目
待完成  LLM Judge、hard gate 结构化结果、双语总结
待完成  profile 设置 UI、watched authors、OpenReview、Venue Trend
待完成  Paper River 后台 job、Action / worker、结果回写
```

继续开发前需要的配置：

```text
LLM Judge / 双语总结：复用 backend/.env 的 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
HF Daily：无 Key
GitHub heat signal：HF Daily 已返回 stars；直接查 GitHub API 时再增加 GITHUB_TOKEN
Paper River：需要独立 worker 或 GitHub Actions callback，不在 FastAPI 请求线程运行
Explore profile：首版使用 SQLite 默认 profile，后续设置页开放 categories、关键词、来源、权重
```

当前建议只保留以下一级入口：

```text
探索
项目雷达
论文
图谱
助手
笔记
```

二级位置：

```text
Explore
├── 推荐流
├── Digest
└── 分析任务

PaperDetail
└── Paper River / 论文溯源
```

三者暂不提升为一级导航。

## 12. 最终推荐方案

近期开发优先级：

```text
P0  复用 source adapters、dedupe、prefilter、LLM client
P0  Explore profile + Explore 独立候选 / match / run
P0  Explore judge + hard gate + topic bucket + heat ranking
P0  bilingual summary 数据结构
P1  watched authors + HF Daily
P1  Daily / Weekly Digest
P1  人工 triage + feedback 统计
P1  Project Radar judge 与 Explore judge 分离
P2  OpenReview + venue trend job
P2  单篇 Paper River job
UI  先讨论信息架构，再改 Radar / Explore 页面
```

推荐默认配置：

```text
来源：arXiv + watched authors
embedding：local SentenceTransformer
judge：OpenAI-compatible LLM
summary：同一 LLM，低并发
排序：semantic 45% + judge 45% + heat 10%
默认视图：今日未读推荐
硬过滤：默认开启
邮件：每日 Digest，可关闭
```

最重要的产品变化：

```text
当前：Radar 承担项目推荐、独立发现、配置、同步、邮件多个职责
集成后：Explore 负责独立发现，Project Radar 负责项目匹配，Research job 负责深度分析
```
