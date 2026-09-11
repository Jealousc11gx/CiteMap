# llm-paper-radar 算法对齐状态

更新日期：2026-09-10
参考仓库：`zhaolin-amd/llm-paper-radar`
本轮验证参考 HEAD：`1d2d05a4c57dfeedc15527ca3fb6f1ae7c2f3264`

## 结论

CiteMap 的 Explore 已按参考仓库的 pipeline 语义适配。适配范围是“同一算法、不同存储和运行时”:

- 参考仓库：GitHub Actions + JSON/Markdown 产物 + provider-specific LLM client。
- CiteMap：FastAPI + SQLite + OpenAI-compatible LLM + React 页面。
- Radar：继续基于项目 corpus 做个性化推荐。
- Explore：独立主题、多源论文流、日报、趋势。Explore 不读取项目论文作为推荐输入。

## 已对齐

| 阶段 | 参考算法 | CiteMap 实现 |
|---|---|---|
| 来源优先级 | `hf_daily` > `openreview` > `arxiv_authors` > `arxiv` | `explore_algorithms.py` 的 `SOURCE_PRIORITY` |
| 去重 | canonical arXiv ID 合并，保留所有来源 | `merge_candidates()`，OpenReview 使用 `or-...` 兼容 ID |
| prefilter | title + abstract；word boundary；无 whitelist 且 blacklist 命中数达到 2 次则 hard gate | `prefilter_verdict()` |
| Judge | `topic_relevance` 0-5 + `practicality` 0-5；hard gate 得分为 0 | `composite_relevance()` + 原始 relevance prompt |
| LLM 失败 | 第一轮 5 次 structured JSON，第二轮 5 次无 structured JSON；贪婪 JSON 提取 | `explore_llm.call_json()` |
| milestone | curated trending ID，或 HF rank <= 20，或 GitHub stars >= 5000；14 天冷却 | `milestone_override()` + `explore_milestone_surfaces` |
| heat | HF rank bonus + HF upvotes + GitHub stars 对数 bonus | `heat_score()` |
| 排序 | `heat + relevance_score * 30`，heat 作为 tie-break | `ranking_score()` + `sort_candidates()` |
| topic bucket | PTQ、Low-bit、QAT、KV cache、Pruning/Distill、Diffusion、Trending、Survey | `BUCKET_ORDER` + `TOPIC_CAPS` |
| caps | 8、5、5、5、3、3、3、3；默认 2 | `group_with_caps()` |
| watched authors | 绕过 topic cap；hard gate 不进入 compact table | digest 的 watched 分支 |
| 摘要 | Judge 后独立 summary；中文 3-5 句、highlights、related methods、English sibling | `summarize_explore_candidate()` + 原始 summary prompt |
| 人工 triage | `unreviewed/read/later/ignored/project` | `transition_explore_triage()` |

## CiteMap 侧的必要适配

### 数据

- 参考仓库用 Paper JSON 表达来源。CiteMap 使用 `explore_candidates`、`explore_candidate_sources`、`explore_profile_candidates`。
- 参考仓库的 `arxiv_id` 既用于去重，也作为文件名。CiteMap 继续沿用旧 schema 的 `arxiv_id UNIQUE`，OpenReview submission 通过 `or-...` ID 存储。
- `code_url`、`code_meta` 保存 HF/GitHub enrichment。
- `summary_status` 与 `judge_status` 分离。Judge 失败可重试，summary 失败不抹掉已有 Judge 结果。

### LLM

Prompt 保留参考仓库版本。调用协议适配为 CiteMap 现有 `get_client()`。默认模型读取 `LLM_MODEL`，不绑定特定 provider 或 model。

### 运行

参考仓库依赖 GitHub Actions 定时触发。CiteMap 当前提供同步 API:

```text
POST /api/explore/scan
POST /api/explore/candidates/{candidate_id}/analyze
POST /api/explore/analyze-pending
```

本地单用户场景先保证算法可重复。后续再把 `scan -> analyze-pending -> digest` 放入后台任务或 Actions worker。

## 尚未声称“完全等价”的部分

这些部分需要独立实现或外部依赖，当前不能标记为完成：

1. Paper River：历史 skill 已恢复，协议已改为复用 CiteMap OpenAI-compatible LLM。CiteMap 内部批量 job 与结果页仍需实现。
2. venue trend：后端已实现一次性抓取 accepted set、exact `venueid` 判定、至少 20 篇完整性门槛、`inference_relevance` 全量分类、subfield 聚类、全体摘要宏观综合。它不是每日 Explore pipeline；前端报告视图仍待接入。
3. weekly/monthly rollup：后端已提供 SQLite rollup API，按窗口去重、检查缺失日期、按 bucket/composite/heat 排序；尚未生成参考仓库的 Markdown snapshot 文件。
4. GitHub Actions、邮件、Markdown 发布：CiteMap 目前保存结构化结果，尚未复制外部仓库的发布作业。

## 配置

最低配置沿用 CiteMap:

```env
LLM_API_KEY=your-openai-compatible-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.5
```

可选来源配置：

```env
OPENREVIEW_EMAIL=
OPENREVIEW_PASSWORD=
```

Explore 的 arXiv categories 在 `explore_profiles.categories` 配置，watched authors 与参考仓库一致，当前在 `explore_sources.py` 常量中维护。HF Daily、OpenReview、arXiv 使用公开接口时无需额外 key；OpenReview 登录凭据用于被 challenge 的账号访问。来源受到 rate limit 或权限限制时，Explore 返回 partial source status，不把部分结果误报成完整结果。

## License

适配代码依据参考仓库 MIT License。原始许可证见 `docs/licenses/llm-paper-radar-MIT.txt`，第三方声明见 `THIRD_PARTY_NOTICES.md`。
