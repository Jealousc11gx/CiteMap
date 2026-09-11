# CiteMap 论文发现与深度研究最终方案

更新日期：2026-09-11
参考项目：`zhaolin-amd/llm-paper-radar`
算法基线 commit：`dc1e54afcfefb3579aae43ddc4b056fda24e2d0a`
Paper River 来源：`lijigang/ljg-skills@de75385ae4226e6589a56ae1ef4ebe5d508d7c4a`

> 最新实现状态、时间修复、集中设置、配置清单见 [`llm-paper-radar-integration-audit.md`](./llm-paper-radar-integration-audit.md)。本文件保留整体产品方案与阶段性 parity 记录。

## 1. 最终结论

CiteMap 不应继续把所有新功能合并进“雷达”页面。最终产品分成三层：

```text
发现层
├── Explore：项目外、独立主题、持续发现
└── Radar：项目内、基于已有 corpus、定向推荐

研究层
└── Research Jobs：对具体论文或会议进行深度分析

沉淀层
├── Papers
├── Notes
└── Map
```

两个发现方向并列，不互相替代：

| 方向 | 核心问题 | 推荐依据 | 用户心智 |
|---|---|---|---|
| 方向一：Project Radar | 哪些新论文适合当前项目？ | 项目描述、已有论文、anchor、反馈 | “围绕项目补充资料” |
| 方向二：Explore | 当前领域有哪些值得关注的新论文？ | 独立 profile、多源、Judge、HeatRanking | “不依赖项目地发现机会” |

深度研究不是第三种推荐流。它消费前两条流的结果：

```text
Explore / Radar 找到论文
        -> 人工 triage
        -> Paper River / Paper Interpret
        -> 加入项目、笔记、Map
```

## 2. 方向一：Project Radar

### 定位

Radar 保持项目内能力。进入前需要当前项目。它回答“为什么这篇论文和我的项目有关”，不展示通用热门论文大盘。

### 输入

- 项目名称、项目描述。
- 项目已有论文 corpus。
- anchor papers。
- include/exclude keywords。
- 用户历史操作：saved、dismissed、read。

### 算法

```text
项目画像
-> 候选采集
-> keyword filter
-> embedding/project-fit ranking
-> LLM project judge
-> 项目相关性排序
-> 项目内每日消息
```

Radar 的分数不能直接复用 Explore 的 `topic_relevance + practicality`。建议保留：

- `semantic_score`：候选与项目 corpus 的语义接近程度。
- `project_fit_score`：对当前研究问题的直接价值。
- `novelty_score`：相对项目已有论文是否提供新方法、数据或结论。
- `reason`：为什么推荐给当前项目。

### UI

Radar 页面只保留：

- 当前项目。
- 项目推荐列表。
- 推荐原因与项目关联点。
- 保存、忽略、已读。
- 设置入口。Radar Worker、ranking、embedding、LLM、邮件配置集中到全局“设置”。

不放入：全局来源统计、全局趋势、venue trend、Paper River 批量任务、通用 Daily Digest。

## 3. 方向二：Explore

### 定位

Explore 是独立发现空间，不依赖任何项目。用户先探索、判断，再决定是否加入项目。

### 核心 pipeline

```text
arXiv + HF Daily + watched authors + OpenReview
-> canonical ID dedupe
-> keyword prefilter
-> LLM Judge / hard gate
-> topic bucket
-> HeatRanking
-> bilingual summary
-> Daily Digest
-> manual triage
```

### 已采用的参考算法

| 算法 | 规则 |
|---|---|
| 来源优先级 | `hf_daily > openreview > arxiv_authors > arxiv` |
| prefilter | 无 whitelist 命中，blacklist 命中数 `>= 2` 才 hard gate |
| Judge | `topic_relevance 0..5 + practicality 0..5` |
| hard gate | 得分固定为 0，不进入 Digest |
| HeatRanking | `100 / HF rank + upvotes + min(log(stars+1)*3, 25)` |
| 最终排序 | `heat + relevance_score * 30` |
| milestone | curated paper 且 HF rank `<= 20`，或 stars `>= 5000` |
| cooldown | milestone 14 天内不重复置顶 |
| bucket caps | PTQ 8；Low-bit/QAT/KV cache 各 5；其他主要桶各 3 |
| 摘要 | Judge 后单独生成中文、English、highlights、related methods |

### 页面结构

Explore 使用四个清晰子视图：

1. `今日简报`：今天通过 Judge、经过 topic cap 的精选结果。
2. `候选池`：所有来源聚合后的论文，支持来源、主题、状态筛选。
3. `周期回顾`：Weekly、Monthly、Half-year、Yearly rollup。
4. `领域趋势`：topic 数量与热度变化，不等同于会议趋势报告。

来源默认聚合。用户可切换只看 arXiv、HF Daily、关注作者、OpenReview。来源是过滤维度，不拆成四个页面。

### Triage

```text
待处理 -> 已读
       -> 稍后处理
       -> 忽略
       -> 加入项目
       -> 发起深度研究
```

Explore 候选默认不进入 `papers`。只有“加入项目”才正式入库，避免发现流污染个人论文库。

## 4. 深度方向：Paper River

### 定位

Paper River 对具体论文按需开启。默认关闭，不跟随每日 pipeline 批量执行。入口可以同时出现在 Explore 论文详情、Radar 推荐详情、正式 Paper 详情。

### retired skill 的真实算法

恢复的原始 skill 不是 citation graph 算法库，而是一套深度检索与写作协议：

```text
读取目标论文摘要、Introduction、Related Work
-> 提取明确批判、改进、baseline 线索
-> 选择最直接的 1 条问题线
-> 向前递归，最多 5 层
-> 每层记录问题、解法、对前序工作的批判、新局限
-> 反向找 1-3 篇后续工作
-> 从最老论文正向叙述问题演化
-> 生成两张 ASCII 图
-> 输出洞见、下一步方向、研究启发
```

关键约束：

- 问题是主角，论文只是证据节点。
- 每一条边必须解释“后者看到了前者的什么问题”。
- 只追一条最相关主线，不扩成完整 citation graph。
- 找不到明确关系时停止。
- 不确定关系必须标记，不补造引用。
- 目标论文之后最多选择 3 篇后续工作。

原文与模板见 `docs/retired-ljg-paper-river.md`。

### CiteMap 的优化方向

历史 skill 依赖特定 CLI、搜索工具、`~/Documents/notes/`。当前版本已改为 OpenAI-compatible LLM 与宿主研究工具；CiteMap 产品内仍应实现可审计任务：

```text
PaperRiverJob
├── target_paper_id
├── max_depth = 5
├── branch_limit = 1
├── forward_limit = 3
├── evidence_source
├── edge_confidence
├── status
└── result
```

建议的节点与边：

```text
node:
  paper_id, title, year, problem, solution, limitation

edge:
  from_paper, to_paper, relation, evidence_quote,
  evidence_location, source_url, confidence
```

改进点：

1. 使用 CiteMap 已有 PDF 与 citation graph，减少重复抓取。
2. 先从 Introduction/Related Work 提取 evidence，再让 LLM 选择主线。
3. 区分 `explicit_citation`、`explicit_critique`、`method_extension`、`inferred_relation`。
4. 所有推断边显示 confidence，用户可以删除或修正。
5. 结果同时提供结构化 graph 与 Markdown narrative，不绑定 Org-mode。
6. 用户确认后才写入 Note 或 Map。

### UI

论文详情页操作：`生成 Paper River`。

任务结果页只显示四部分：

- 问题之河：一句话主问题。
- 演化时间线：前序论文、目标论文、后续论文。
- 证据面板：选中边后查看引用位置与置信度。
- 演化叙事：问题、解法、新局限、洞见。

## 5. 找到的其他方向

### 5.1 Venue Trend

Venue Trend 是会议级一次性研究，不是 Explore 日趋势。

```text
指定 conference/year
-> 获取全部 accepted papers
-> exact venueid acceptance gate
-> 至少 20 篇完整性检查
-> inference relevance 分类
-> subfield grouping
-> 强模型读取全部 in-scope abstracts
-> 按真实研究问题生成宏观报告
```

价值：回答“这个会议正在集中解决什么问题”，帮助选方向、做 related work、判断研究热度。

UI 归属：Explore 的 `会议研究` 页面，或 Research Jobs 的新建任务。不要放在今日简报中。

### 5.2 Digest 与长期回顾

Daily Digest 只描述独立 Explore 当天结果，区别于 Radar 的项目每日消息。

- Daily：经过 bucket cap 的当天精选。
- Weekly：允许少量日期缺失，做 7 天窗口去重。
- Monthly/Half-year/Yearly：要求窗口数据完整，缺失时明确中止。
- 每篇论文保留首次出现日期、多源信息、Judge、summary、triage。

UI 使用同一个 `周期回顾` 子视图，不再单独增加导航入口。

### 5.3 Watched Authors 与 Watched Venues

watched author 论文绕过 topic cap，但不能绕过 hard gate。UI 在 Digest 中独立成组，避免被热门论文挤掉。

watched venues 用于来源采集与筛选。会议整体分析仍由 Venue Trend 手动触发。

### 5.4 Affiliation Enrichment

参考 repo 会读取最终入选论文 PDF 首页，再用 LLM 提取作者机构。CiteMap 可复用已有 PDF parser，只对最终 surfaced set 运行：

```text
入选论文 -> PDF 首页 -> affiliation extraction -> 本地 cache
```

用途：观察团队、机构、产业界研究动向；补充 CiteMap team graph。不能对所有候选运行，成本过高。

### 5.5 Curation Learning

参考 repo 用 `seeds.yaml`、accepted/rejected JSONL 维护人工经验。CiteMap 应改为数据库反馈：

- 接受为长期 seed。
- 拒绝原因。
- 建议 blacklist pattern。
- 用户修正 bucket。
- 用户修正 Paper River edge。

首版只记录反馈，不自动修改 Prompt。积累足够样本后，再提供“建议规则变更”，由用户确认。

### 5.6 自动化与发布

参考 repo 使用 GitHub Actions 运行 Daily/Weekly、写 Markdown、提交 Git。CiteMap 应拆成：

- 本地 scheduler：单机常驻时使用。
- GitHub Actions/Worker：无人值守采集与分析。
- Web UI：读取 SQLite 或远端同步结果。
- 邮件：只发送 Digest，不承担主数据存储。

任务状态建议命名为 `分析任务`，不要使用含义模糊的“任务中心”。

## 6. UI 信息架构

```text
发现
├── 探索
│   ├── 今日简报
│   ├── 候选池
│   ├── 周期回顾
│   └── 领域趋势
└── 雷达
    ├── 项目推荐
    └── Radar 设置

研究
├── 论文
├── 图谱
├── 分析任务
│   ├── Paper River
│   └── Venue Trend
├── 助手
└── 笔记
```

页面层级原则：

- Explore 首页直接展示工作结果，不写功能介绍。
- 今日简报不显示漏斗过程，只显示精选结果与来源摘要。
- 候选池显示 Judge 状态、score、heat、bucket、triage。
- 采集与 LLM 分析分成两个动作，避免用户误以为采集必然消耗 LLM。
- Paper River 入口只在具体论文详情出现。
- Venue Trend 需要会议参数，单独新建分析任务。

## 7. 当前实现与参考 repo 的 parity 结果

### 测试结果

| 测试对象 | 结果 |
|---|---:|
| 参考 repo 原生 pytest | 本轮未完成：环境缺少 `uv`；替代 venv 卡在联网重试 |
| CiteMap 后端 pytest | `252 passed` |
| CiteMap 前端 Vitest | `76 passed` |
| CiteMap TypeScript/Vite build | 通过 |
| Prompt SHA-256 对比 | relevance、summary、venue relevance 完全一致 |
| 确定性 parity 脚本 | `18/18 passed` |

### 已达到算法等价

- arXiv、HF Daily、watched authors、OpenReview 多源采集语义。
- 来源优先级与 dedupe 字段回填。
- prefilter word boundary 与 hard gate 条件。
- Judge composite score。
- LLM JSON fallback。
- milestone override 与 cooldown。
- HeatRanking、最终排序、topic caps。
- bilingual summary schema。
- watched authors 分组规则。
- venue accepted 判定、venue filter、grouping。
- SQLite rollup 的窗口、去重、排序、完整性语义。

### 架构适配，不要求字节等价

- JSON 文件改为 SQLite。
- 外部 LLM client 改为 CiteMap 统一的 OpenAI-compatible client。
- Markdown Digest 改为 React 页面与 API payload。
- shell pipeline 改为 FastAPI service functions。
- `seeds.yaml` 改为后续数据库 curation store。

### 尚未功能等价

| 参考能力 | 当前状态 | 缺口 |
|---|---|---|
| Paper River | 历史 skill 与 Org 模板已恢复 | 无 job、PDF evidence extraction、递归主线、结果页 |
| affiliation enrichment | 未并入 Explore surfaced pipeline | 缺 PDF 首页提取、cache、机构 UI |
| Markdown daily/index/snapshot | 未实现 | 当前只提供 UI/API |
| GitHub Actions daily/weekly | 未实现 | 缺 scheduler/worker orchestration |
| 邮件发布 | Radar 已有，Explore 未接 | 缺 Explore Digest renderer |
| seed accept/reject scripts | triage 已有 | 缺长期 seed、拒绝原因、规则建议 |
| Paper River English sibling | 未实现 | 应在主结果完成后按需翻译 |
| Venue Trend 前端 | 后端已实现 | 缺任务创建与报告视图 |

结论：核心 Explore 判定与排序算法已对齐。整个参考 repo 的所有产品功能尚未完全等价。最大缺口是 Paper River 执行器、affiliation enrichment、自动化发布、curation learning、Venue Trend UI。

## 8. 开发优先级

### P0：完成 Explore 可用闭环

1. Explore profile 设置已集中到全局“设置”：categories、来源、watched authors、venues。
2. 今日简报、候选池、周期回顾 UI 收敛。
3. 后台运行 `scan -> analyze -> digest`，显示 task progress。
4. Explore Digest 邮件。

### P1：实现第二方向的深度研究闭环

1. Paper River job schema、状态与取消。
2. PDF Introduction/Related Work evidence extraction。
3. citation candidate retrieval。
4. 单主线递归、最多 5 层。
5. 后续工作搜索、最多 3 篇。
6. evidence/confidence UI。
7. 写入 Note、Map。

### P2：扩展方向

1. Venue Trend 前端与后台任务。
2. affiliation enrichment 与 team graph 联动。
3. curation feedback 与规则建议。
4. monthly/half-year/yearly snapshot export。
5. GitHub Actions/Worker 无人值守执行。

## 9. 验收标准

### Explore

- 不选择项目也可完整使用。
- 同一论文多源采集只产生一个候选。
- Judge、HeatRanking、bucket cap 与参考测试 fixture 结果一致。
- 候选不会自动进入 Papers。
- 今日简报与 Radar 每日消息有明确数据边界。

### Radar

- 推荐解释引用当前项目上下文。
- Explore 的 ignored 状态不影响 Radar 同论文状态。
- 热度只能辅助排序，不能覆盖项目相关性。

### Paper River

- 每个关系边都有 evidence 与 confidence。
- 主线最多 5 层，只保留一条最相关问题线。
- 后续工作最多 3 篇。
- 找不到关系时停止，不生成推测性 citation。
- 输出能独立写入 Note，并可投影到 Map。

### Venue Trend

- accepted papers 使用 exact `venueid` 判定。
- partial fetch 不生成最终报告。
- 报告按研究问题组织，不按 bucket 顺序简单拼接。
- 说明覆盖范围、模型、数据时间与证据限制。

## 10. 最终产品表达

一句话：

> CiteMap 用 Explore 发现领域机会，用 Radar 服务当前项目，用 Research Jobs 把关键论文变成可追溯的知识脉络。

对应用户路径：

```text
探索新论文
-> 判断值不值得读
-> 找到与项目的关系
-> 对关键论文追溯问题演化
-> 加入项目
-> 写入笔记与知识图谱
```
