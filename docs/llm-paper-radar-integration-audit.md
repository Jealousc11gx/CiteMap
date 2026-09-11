# llm-paper-radar 集成审计

更新日期：2026-09-11
参考仓库：`zhaolin-amd/llm-paper-radar`
审计上游 HEAD：`1d2d05a4c57dfeedc15527ca3fb6f1ae7c2f3264`
CiteMap 初始算法移植基线：`dc1e54afcfefb3579aae43ddc4b056fda24e2d0a`

## 1. 上游核心功能

上游不是单一“热门论文列表”，而是完整的每日研究情报 pipeline：

```text
arXiv + HF Daily/Trending + OpenReview + watched authors
-> canonical ID 去重、来源合并
-> 本地 keyword prefilter
-> LLM 两轴 Judge
-> hard gate、topic bucket
-> HeatRanking
-> 双语摘要、机构提取
-> Daily/Weekly/Monthly/Half-year/Yearly Digest
-> Paper River 深度溯源
-> cron / GitHub Actions / 邮件 / Git 提交
```

核心算法：

| 能力 | 上游规则 | CiteMap 状态 |
|---|---|---|
| 多源采集 | arXiv、HF Daily/Trending、OpenReview、watched authors | 已合入 |
| Dedupe | arXiv ID 为 canonical ID；保留全部来源；字段按来源优先级回填 | 已合入 |
| 来源优先级 | `hf_daily > openreview > arxiv_authors > arxiv` | 已复用 |
| Prefilter | 无 whitelist 命中，blacklist 命中数 `>= 2` 才本地 hard gate | 已复用，支持设置追加关键词 |
| LLM Judge | `topic_relevance 0..5 + practicality 0..5` | Prompt、JSON schema、重试语义已复用 |
| Topic bucket | PTQ、Low-bit、QAT、KV cache、Pruning/Distillation、Diffusion、Trending、Survey | 已复用 |
| HeatRanking | `100 / HF rank + upvotes + min(log(stars+1)*3, 25)` | 已复用 |
| 最终排序 | `relevance_score * 30 + heat_score` | 已复用 |
| Milestone | curated ID 且 HF rank `<= 20`，或 stars `>= 5000` | 已复用；默认禁止突破论文年龄限制 |
| Cooldown | milestone 14 天内不重复置顶 | 已复用 |
| Bucket cap | PTQ 8；Low-bit/QAT/KV 5；主要其他桶 3 | 已复用 |
| 双语摘要 | Judge 后独立 summary/highlights/related methods | 已合入 |
| OpenReview venue | `{year}` 展开当前年、下一年；只取 `Submission` | 已合入、默认开启 |
| Venue Trend | accepted gate、相关性分类、分组、宏观报告 | 后端与 Explore UI 已合入 |
| Rollup | Daily、Weekly、Monthly、Half-year、Yearly | API 与 Explore UI 已合入 |
| Affiliation enrichment | 最终入选集读取 PDF 首页 | Radar 已有字段；Explore 自动 enrichment 未合入 |
| 自动发布 | cron、GitHub Actions、Markdown、邮件、Git push | Radar Worker 部分已有；Explore 未完整合入 |

## 2. 时间逻辑

### 上游真实语义

上游每天北京 14:00，即 UTC 06:00 运行。`daily.sh` 设置 `RADAR_DAY_OFFSET=1`，目标日是上一完整 UTC 日。arXiv 使用该目标日的 `submittedDate`；OpenReview、watched authors 使用 7 天滚动窗口。

HF 有两组不同数据：

- `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD`：指定日期的 Daily Papers。
- `https://huggingface.co/papers/trending`：请求时刻的 Trending 排名，不带日期参数。

上游会把当前 Trending 中缺少的论文通过 arXiv 补全。旧论文可能重新进入 Trending。curated milestone 可绕过普通 hard gate；14 天 cooldown 只防止重复置顶，不限制论文发表年份。

### CiteMap 原问题

原实现同时满足以下条件：

1. 无条件合并 HF 当前 Trending 全榜。
2. 旧论文首次入库时，`discovered_at` 写成当前日期。
3. Daily Digest 接受“发表日是今天”或“发现日是今天”。

结果：2023 论文在 2026 首次被 HF Trending 发现，会进入 2026 今日简报。

### 当前修正

- 默认 `EXPLORE_DAY_OFFSET=1`，扫描上一完整 UTC 日。
- 新增 `explore_discoveries`，明确记录候选属于哪个目标批次日期，不再拿数据库写入时间冒充论文批次。
- 默认 `EXPLORE_HF_TRENDING_MAX_AGE_DAYS=30`。
- 未来日期论文始终拒绝。
- 历史 milestone 默认关闭；需要上游原行为时，在设置中显式开启。
- HF rank、upvotes、GitHub stars、milestone、cooldown、最终排序算法保持不变。

默认效果：2026 今日热点不会再混入 2023 论文。用户可在“设置 > 探索”调整年龄上限、目标日偏移、历史 milestone。

## 3. OpenReview

OpenReview 源已存在，不是缺失：

- 默认开启。
- 默认窗口 7 天。
- 默认 venues：ICLR、ICML、NeurIPS、MLSys、AAAI、ACL、EMNLP。
- `{year}` 自动展开目标年、下一年。
- 只读取 `/-/Submission`，不读取 review、comment、rebuttal、meta-review。
- 公开 venue 通常不需要账号；API challenge、私有内容可配置 `OPENREVIEW_EMAIL`、`OPENREVIEW_PASSWORD`。

某天页面没有 OpenReview 标签，通常表示当前窗口内配置的 invitation 没有 submission，或 invitation 名称已经迁移。ACL/EMNLP 部分主轨可能迁移到 ARR，需要在“设置 > 探索”更新 venue。

## 4. 需要的配置

全部本地配置集中在“设置”。读取接口不返回 Secret 明文；Secret 只显示“已配置”，新值写入 `backend/.env`。Worker Token 保存在本机 SQLite。

### 最小配置

| 场景 | 必填 |
|---|---|
| Explore 采集 | 无 Token；至少开启一个来源；配置 arXiv categories |
| Explore Judge/摘要 | `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` |
| Paper 标注、Chat | `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` |
| Radar Local | 项目雷达配置；本地 embedding 模型依赖 |
| Radar Cloud | Worker URL、`RADAR_TOKEN`；云端 GitHub Secrets 仍需在部署端配置 |

### 可选配置

| 配置 | 用途 |
|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | 引用同步限额更稳定 |
| `OPENREVIEW_EMAIL`、`OPENREVIEW_PASSWORD` | OpenReview 登录 |
| `RADAR_EMBEDDING_API_KEY`、`RADAR_EMBEDDING_BASE_URL` | API embedding；留空可复用全局 LLM 凭据 |
| `RADAR_EMAIL_*`、`RADAR_SMTP_*` | 雷达邮件 |
| `LLM_PROVIDER_TYPE`、`LLM_CAPABILITIES`、`LLM_MAX_CONTEXT_SIZE` | Kimi Agent SDK provider |

## 5. 统一设置

“外观”入口已改为“设置”。设置页包含：

- 主题：保留在侧栏“设置”右侧，快速切换浅色、深色。
- AI：LLM endpoint、model、API Key、provider、capabilities、context；Paper River 复用同一 OpenAI-compatible 配置。
- 探索：目标日、HF 年龄边界、四类来源、OpenReview venue/window、watched author window、profile categories、include/exclude keywords。
- 雷达：当前项目配置、Worker、Embedding、LLM 摘要、SMTP。
- 集成：Semantic Scholar、OpenReview 账号。

Radar 页面不再维护第二套设置表单，不再把 Worker Token 存在浏览器 `localStorage`。

## 6. Paper River 恢复

从 `lijigang/ljg-skills@de75385ae4226e6589a56ae1ef4ebe5d508d7c4a` 恢复：

- `skills/ljg-paper-river/SKILL.md`
- `skills/ljg-paper-river/references/template.org`

删除 commit：`fb6279ed25f87442330f3b503d15e5b2457d2e26`。

旧 frontmatter 的 `user_invocable`、`version` 已迁入当前 Codex 支持的 `metadata`；倒读法正文与 Org 模板保持，模型和工具说明改为 OpenAI-compatible。当前状态只恢复 skill。CiteMap 内部 Paper River job、证据抽取、任务状态、结果页仍未实现。

## 7. 尚需补齐

按价值排序：

1. Paper River job：PDF Introduction/Related Work evidence、单主线递归、后续论文、confidence、结果页。
2. Explore affiliation enrichment：只对 surfaced set 读取 PDF 首页。
3. Explore 自动任务：定时 `scan -> analyze -> digest -> mail`。
4. Curation learning：长期 seed、拒绝原因、规则建议。
5. Explore Markdown Digest 与 Git 发布。

当前核心发现、判定、排序效果已最大化复用上游算法。未完成部分主要是自动化、深度研究执行器、发布链路，不是排序公式。
