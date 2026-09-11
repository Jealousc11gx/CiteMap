# llm-paper-radar 功能一致性验证

验证日期：2026-09-11
参考仓库 HEAD：`1d2d05a4c57dfeedc15527ca3fb6f1ae7c2f3264`

## 结论

不能声称 CiteMap 已与参考仓库“全部功能、全部表现一致”。确定性发现算法已对齐；存储与 UI 做了产品适配；发布自动化、Paper River job、Explore 机构补全仍未实现。统一到 OpenAI-compatible LLM 后，Prompt、JSON schema、gate、score、bucket、排序可以保持一致，生成文本无法保证逐字一致。

## 自动验证

运行：

```bash
backend/.venv/bin/python scripts/verify_llm_paper_radar_parity.py \
  --reference /path/to/llm-paper-radar
```

本次结果：`18/18 passed`。

覆盖：relevance/summary/Venue relevance Prompt SHA-256、source priority、topic caps、prefilter whitelist/blacklist/threshold、watched authors、OpenReview venues、milestone IDs/rank/stars/cooldown、relevance weight、HF rank cap、star weight/cap。

## 功能矩阵

| 参考能力 | CiteMap 状态 | 一致性 |
|---|---|---|
| arXiv 精确目标日、retry、OAI fallback | 已实现 | 等价 |
| HF Daily、Trending metadata、arXiv 补全 | 已实现 | 算法等价；按需求新增 30 天默认年龄边界 |
| watched authors 联合查询 | 已实现 | 等价 |
| OpenReview rolling source、登录 | 已实现 | 等价 |
| canonical dedupe、来源优先级 | 已实现 | 等价 |
| word-boundary prefilter | 已实现 | 默认等价；profile 关键词可主动追加 |
| LLM Judge、hard gate、bucket | 已实现 | Prompt/schema/后处理等价；provider 不同 |
| HeatRanking、caps、milestone、cooldown | 已实现 | 等价 |
| 双语 summary/highlights/related methods | 已实现 | Prompt/schema 等价；provider 不同 |
| Daily Digest | 已实现为 SQLite/API/UI | 语义适配，不生成相同 Markdown |
| Weekly/Monthly/Half-year/Yearly rollup | 已实现为 API/UI | 窗口、去重、完整性等价；不生成 snapshot 文件 |
| paper triage | 已实现为 Explore 状态流转 | 产品适配；未写 `seeds.yaml/rejected.jsonl` |
| Venue Trend | 后端与 UI 已实现 | accepted gate、分类、分组等价；报告 Prompt 为 OpenAI-compatible 结构化适配 |
| PDF 首页机构提取与 cache | Radar 有；Explore 无 | 缺失 |
| Paper River skill | 已恢复并改为 OpenAI-compatible | 方法可用；无 CiteMap job、批量执行、结果页 |
| paper-interpret 多角度归档 | 无 | 缺失 |
| `daily.sh`、backfill、snapshot、Git push | 无 Explore scheduler | 缺失 |
| Explore Markdown/邮件发布 | 无 | 缺失 |
| seed accept/reject、curation learning | 只有 UI triage | 缺失 |

## 验证边界

1. 同一 LLM provider、model、temperature、Prompt、输入仍不保证逐字相同输出。
2. OpenAI-compatible provider 不支持 `response_format` 时，CiteMap 会执行与参考仓库相同目的的 JSON fallback；性能、速率限制取决于 provider。
3. HF 年龄限制是用户要求的差异，不属于上游原始行为。
4. “全部功能一致”需要先补齐矩阵中的缺失项，再做端到端 golden dataset 对照。
