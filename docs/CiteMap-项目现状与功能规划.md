# CiteMap 项目现状与功能规划

> 更新日期：2026-09-04  
> 文档性质：项目现状说明与后续功能讨论稿  
> 说明：本文不记录本地服务启动过程，只描述产品、代码结构、现有能力、已讨论功能与建议路线。

---

## 1. 项目定位

CiteMap 是一个本地优先、面向个人研究者的论文管理与知识组织工具。

核心目标：

```text
发现论文
→ 判断是否值得关注
→ 保存到研究项目
→ 提取论文信息并生成 AI 标注
→ 通过 Map 理解论文、作者、团队之间的关系
→ 通过 AI 助手检索和操作论文库
→ 使用 Markdown 笔记沉淀研究内容
```

当前产品形态：

- 本地单用户应用
- React Web 前端
- FastAPI 后端
- SQLite 保存结构化数据
- 本地目录保存 PDF 和 Markdown 笔记
- OpenAI-compatible API 提供 AI 标注与聊天能力
- 不依赖云端账号体系

CiteMap 当前不是 Zotero 的完整替代品。它更接近一个围绕“研究项目、论文关系、AI 分析、Markdown 笔记”构建的个人研究工作区。

---

## 2. 当前系统构成

### 2.1 技术架构

| 层级 | 当前技术 | 作用 |
|---|---|---|
| 前端 | React 19、TypeScript、Vite | 页面、状态、交互 |
| UI | shadcn/ui、Radix UI、Tailwind CSS | 组件和视觉体系 |
| 后端 | FastAPI、Python | REST API、SSE、业务逻辑 |
| 数据库 | SQLite | 论文、项目、关系、聊天记录 |
| PDF | PyMuPDF | 文本、版面、metadata 提取 |
| 图计算 | NetworkX | 团队 Map、论文 Map 构建 |
| 图渲染 | PixiJS、d3-force | 节点和边的交互式展示 |
| AI | OpenAI-compatible API、Kimi Agent SDK | 标注、聊天、工具调用 |
| 笔记 | Markdown、YAML-like frontmatter | 本地研究笔记 |
| 测试 | pytest、Vitest | 后端、前端自动测试 |

### 2.2 核心目录

```text
CiteMap/
├── backend/
│   ├── main.py                  FastAPI 路由和 API 模型
│   ├── agent.yaml               AI 助手工具配置
│   └── paper_graph/
│       ├── database.py          SQLite schema、CRUD、项目关系
│       ├── ingest.py            arXiv、本地 PDF 入库和解析
│       ├── annotate.py          AI 标注
│       ├── graph.py             Map 构建和 HTML 导出
│       ├── notes.py             Markdown 笔记
│       ├── chat_agent.py        Agent 会话和 SSE
│       ├── chat_tools.py        Agent 工具执行
│       ├── kimi_tools.py        Kimi SDK 工具包装
│       └── export.py            Markdown 汇总导出
├── frontend/src/
│   ├── pages/                   总览、论文、Map、助手、笔记、详情
│   ├── components/              Layout、PixiGraph、NoteEditor 等
│   ├── contexts/                当前研究项目状态
│   ├── services/api.ts          REST 和 SSE API client
│   └── types/                   TypeScript 类型
├── data/
│   ├── papers.db                SQLite 数据库
│   ├── pdfs/                    PDF 文件
│   └── notes/                   Markdown 笔记
└── docs/                        产品和技术文档
```

### 2.3 核心数据关系

```text
Project ──< ProjectPaper >── Paper
                              │
                              ├── Author
                              ├── Institution
                              ├── Team
                              ├── Tag
                              ├── PDF
                              └── Markdown Note

Project ──< ChatSession ──< ChatMessage
```

项目与论文是多对多关系。同一篇论文可以同时服务多个研究项目。`未分类`是系统项目，用于承接尚未归入普通项目的论文。

---

## 3. 当前已经实现的功能

### 3.1 研究项目工作区

当前支持：

- 创建研究项目
- 重命名普通项目
- 删除普通项目
- 内置不可重命名、不可删除的`未分类`项目
- 记住当前选中的项目
- 同一篇论文加入多个项目
- 将单篇论文添加到其他项目
- 从其他项目批量导入已有论文
- 对筛选结果全选、取消全选、显示半选状态
- 从当前普通项目移除论文
- 项目切换后刷新 Dashboard、论文、Map、聊天、笔记
- 聊天会话绑定项目
- 防止切换项目后旧 SSE 回复污染新项目界面

当前限制：

- 项目描述的编辑入口较弱
- 没有项目级研究目标、关注主题、排除主题配置
- 没有项目归档、排序、颜色、图标
- 没有项目级导入导出
- 没有项目级阅读进度与研究产出统计

项目结构已经为“论文雷达”提供了基础：每个项目可以拥有独立兴趣画像、anchor papers、雷达配置和推荐结果。

### 3.2 arXiv 发现与论文入库

当前支持：

- 使用关键词搜索 arXiv
- 搜索结果只展示，不自动污染本地论文库
- 从搜索结果选择单篇入库
- 输入 arXiv ID 或 URL 入库
- 批量入库多个 arXiv ID
- 入库时选择目标项目
- 可选下载 arXiv PDF
- 已入库 arXiv 论文补下载 PDF
- 本地 PDF 单文件上传
- PDF 复制到统一管理目录
- 使用文件内容 hash 生成本地论文 ID
- 识别 PDF 中的 arXiv ID 后转为规范 arXiv 论文记录
- 遇到扫描版、没有文本层的 PDF 时明确返回错误

当前限制：

- 没有多文件拖拽
- 没有整个文件夹递归导入
- 没有导入任务队列
- 没有暂停、继续、取消、失败重试
- 没有重复论文检测和版本合并界面
- 没有 DOI、BibTeX、RIS、Zotero 导入
- 没有论文删除、归档和 metadata 手动编辑
- 上传主要校验扩展名，PDF 文件真实性校验仍可加强

### 3.3 PDF 信息提取

当前主引擎为 PyMuPDF。

已经实现：

- 提取 PDF metadata
- 提取首页和多页文本
- 基于字号、位置、文本结构识别标题
- 识别作者区域和摘要区域
- 处理常见双栏摘要布局
- 从 PDF 前几页识别 arXiv ID
- 使用 arXiv API 回填权威标题、摘要、作者、分类、日期
- arXiv API 返回 `HTTP 429` 等错误时，降级读取 arXiv 摘要页 `citation_*` metadata
- metadata 刷新时保留已有 `pdf_path`
- 为 AI 标注抽取 Abstract、Introduction、Method、Results、Conclusion 等章节片段
- 控制送入 LLM 的文本长度

已经解决的典型错误：

- 将 `Published as a conference paper...` 误识别为标题
- 将日期误识别为标题
- 将 `Untitled Diagram` 等 PDF metadata 误识别为标题
- 一键摘要只读取 abstract、不读取 PDF

当前限制：

- 不支持扫描版 PDF OCR
- 不完整提取表格、公式、图片、参考文献结构
- 非 arXiv 论文缺少 Crossref、OpenAlex 等 metadata 补全
- 复杂作者上标、机构映射仍可能失败
- 尚未保存完整结构化章节结果

### 3.4 AI 智能标注

当前支持：

- 生成中文 TLDR
- TLDR 覆盖研究问题、方法、结果、价值
- 提炼简短核心贡献
- 识别主要研究领域
- 识别子领域
- 生成结构化标签
- 标签类型包括任务、方法、模型、数据集、模态、应用等
- 识别研究团队
- 识别作者与机构关系
- 标注结果写入 SQLite
- 单篇标注
- 批量标注未标注论文
- 强制重新标注
- 重新标注前重新读取 PDF 并刷新 arXiv metadata
- 获取可用 LLM 模型列表
- 选择模型
- LLM 返回 markdown code fence、缺失字段、非法 JSON 时进行容错或明确报错

当前限制：

- AI 依赖外部 OpenAI-compatible API
- 不是完全离线的本地模型
- 没有标注质量评分和置信度
- 没有用户确认、拒绝、撤销标签的工作流
- 没有标注结果版本历史
- 没有固定评测集验证“自动分类准确率 ≥85%”

### 3.5 论文库与详情页

当前支持：

- 按当前项目显示论文
- 搜索标题、摘要、TLDR、核心贡献、领域、子领域、标签
- 展示 arXiv、本地来源
- 展示 PDF、笔记、AI 标注状态
- 查看论文详情
- 查看作者、机构、领域、子领域和标签
- 查看摘要、TLDR、核心贡献
- 打开 arXiv 页面
- 下载 PDF
- 进入对应 Markdown 笔记
- 添加到其他项目、从当前项目移除

当前限制：

- 搜索是数据库字段和内存文本匹配，不是 PDF 全文搜索
- 没有高级组合筛选
- 没有排序方式切换
- 没有阅读状态、优先级、星标
- 没有批量移动、删除、归档、导出
- 没有手动编辑 metadata
- 没有稳定 citekey

### 3.6 Map 知识图谱

CiteMap 当前提供两种 Map。

#### 团队 Map

- 研究团队作为节点
- 团队通过关联论文形成关系
- AI 标注生成团队和机构信息
- 点击节点查看团队信息和代表论文

#### 论文 Map

- 论文作为节点
- 两篇论文共享作者时形成边
- 共享作者数量可作为边权重
- 点击论文节点进入详情页

#### 交互能力

- Map 按当前项目生成
- PixiJS 高性能绘制
- d3-force 力导向布局
- 拖拽节点
- 缩放和平移画布
- 搜索节点
- 重置视图
- 点击节点查看 Inspector
- 明暗主题适配

当前限制：

- 论文 Map 表示共享作者，不表示真实引用关系
- 没有作者、机构、标签、笔记节点视图
- 没有时间、领域、标签、作者筛选
- 没有社区发现、聚类、路径分析
- 节点位置和用户布局不会持久化
- Markdown `[[wikilink]]` 尚未转为 Map 关系
- 已有 PyVis HTML 导出函数，但没有 API 和前端入口
- 没有 PNG、SVG、JSON、GraphML 等导出

### 3.7 AI 助手

当前支持：

- 创建、重命名、删除聊天会话
- 保存聊天历史
- 多轮上下文
- SSE 流式回答
- 显示 thinking、tool call、tool result、answer
- 按研究项目隔离会话和工具范围
- 将工具结果渲染为论文卡片
- 自动批准当前本地工具调用

可调用工具：

1. 搜索 arXiv
2. 入库 arXiv 论文
3. 列出本地论文
4. 搜索本地论文
5. 查看论文详情
6. 执行 AI 标注
7. 下载 PDF
8. 查看论文笔记
9. 查看 Map 统计

当前限制：

- 本地搜索仍是关键词匹配，不是向量 RAG
- 不能对 PDF 全文进行带页码引用的问答
- 不能可靠比较多篇论文的原文证据
- 没有引用片段、来源页码和证据定位
- 没有用户可配置的工具权限
- 没有对话导出

### 3.8 Markdown 笔记

当前支持：

- 为论文创建 Markdown 笔记模板
- 保存到 `data/notes/{paper_id}.md`
- YAML-like frontmatter
- frontmatter 保存标题、作者、日期、分类、arXiv、PDF 等信息
- 笔记文件树
- 按当前项目显示笔记
- 编辑和预览模式切换
- 手动保存
- 删除笔记
- GFM 表格
- 任务列表
- 删除线
- 代码块
- 引用、链接、图片等 Markdown 样式
- `[[wikilink]]` 文本
- 预览时隐藏 frontmatter
- 禁止原始 HTML，降低注入风险

当前限制：

- `[[wikilink]]` 没有自动补全
- `[[wikilink]]` 没有跳转和反向链接
- 笔记关系没有进入 Map
- 笔记正文没有全文搜索
- 笔记没有标签、文件夹、独立笔记类型
- 当前笔记主要绑定论文，不能创建不绑定论文的研究笔记
- PDF 高亮和摘录不能自动生成笔记
- 笔记与 PDF 页码之间没有双向定位
- 没有 Obsidian 笔记库一键导出
- 没有 Obsidian/Logseq 双向同步

### 3.9 Dashboard 与 UI

当前支持：

- 当前项目论文总数
- arXiv、本地论文统计
- 已标注、待标注统计
- PDF、笔记覆盖率
- 最近论文
- 快捷进入论文、Map、笔记
- `Research Workspace` 桌面布局
- 左侧导航
- 项目切换器
- 明暗主题
- Skeleton、错误、重试、Toast 等状态反馈

已经确定的设计方向：

- 产品名称使用 CiteMap
- 桌面研究工作区
- 冷白、石墨、Cobalt Blue
- 高信息密度
- 减少营销页式布局、渐变、装饰 Card
- 不把移动端作为 v1 产品目标

尚未实现的 UI 建议：

- 全局 Command Palette
- 全局论文搜索
- 快捷切换项目
- 统一右侧 Inspector
- 论文库与 arXiv 发现 Tabs
- 固定论文操作栏

### 3.10 测试与当前质量

当前自动验证结果：

- 后端 pytest：165 项通过
- 前端 Vitest：68 项通过
- TypeScript 与 Vite production build：通过

已覆盖的主要测试范围：

- SQLite schema 与迁移
- 项目 CRUD 和论文归属
- arXiv、本地 PDF 入库
- PDF metadata 与布局提取
- AI 标注与降级
- Map 构建
- 聊天会话和 SSE
- 笔记 CRUD 与 frontmatter
- API client
- 页面基础渲染

当前测试边界：

- 前端测试以 API 和 smoke test 为主
- 没有正式 Playwright/Cypress E2E 套件
- 没有 10,000 篇论文规模性能测试
- 没有 AI 标注准确率评测集
- 没有雷达推荐质量评测

---

## 4. 已讨论的核心新功能：项目论文雷达

### 4.1 功能目标

论文雷达用于自动追踪每个研究项目相关的 arXiv 新论文。

```text
每天获取 arXiv 新论文
→ 根据当前研究项目分别匹配
→ 保存推荐结果
→ 在 CiteMap 内显示未读提醒
→ 用户查看、保存或忽略
→ 保存后进入正式论文库和当前项目
```

参考项目：

- `TideDra/zotero-arxiv-daily`

参考项目使用 Zotero 论文摘要作为用户兴趣语料，计算每日 arXiv 论文的 embedding 相似度，再通过邮件发送结果。

CiteMap 的调整方向：

| 参考项目 | CiteMap 方案 |
|---|---|
| Zotero library | 当前研究项目论文 |
| Zotero abstract | `title`、`abstract`、`core_contribution` |
| 单一兴趣库 | 每个项目独立兴趣模型 |
| embedding 加权 | 算法 A，并增加 anchor papers |
| 邮件发送 | 站内雷达页面和未读提醒 |
| GitHub Actions | FastAPI 本地定时任务 |
| 邮箱配置 | 不需要 |
| 自动邮件 | 今日推荐列表 |

许可证边界：参考仓库使用 AGPL-3.0，CiteMap 使用 Apache-2.0。实现时只借鉴流程和算法思想，独立编写代码，不直接复制其核心实现。

### 4.2 雷达配置

每个普通项目独立拥有一份雷达配置：

| 配置 | 作用 |
|---|---|
| `enabled` | 是否开启当前项目雷达 |
| `categories` | 关注的 arXiv 分类 |
| `include_keywords` | 关注词 |
| `exclude_keywords` | 排除词 |
| `profile_override` | 用户补充的研究目标 |
| `anchor_paper_ids` | 项目核心论文 |
| `top_k` | 每日最多推荐数量 |
| `min_score` | 最低相关度 |

规则：

- 普通项目创建后默认不开启雷达
- `未分类`默认关闭
- 每个项目可以选择不同分类、关键词和 anchor papers
- 每日只抓取一次 arXiv，然后对所有启用项目分别计算

### 4.3 算法 A：Reference Embedding

算法 A 尽量保持参考 repo 的有效逻辑，作为第一版默认算法。

```text
当前项目所有论文
→ 提取 title + abstract
→ 计算并缓存 embedding
→ 每日 arXiv 候选计算 embedding
→ 计算 candidate 与项目论文的 cosine similarity
→ 按论文加入项目的时间加权
→ anchor papers 额外加权
→ min_score 过滤
→ Top K
```

已讨论的时间权重：

```text
项目论文按 added_at 从新到旧排序

weight_i = 1 / (1 + log10(i + 1))
weights = weights / sum(weights)

score(candidate)
    = sum(cosine(candidate, project_paper_i) * weight_i)
```

优点：

- 接近用户已经认可的参考 repo 效果
- 不依赖 LLM 生成项目画像
- 项目中每篇论文都参与匹配
- embedding 可以缓存
- 新加入论文自然获得较高权重
- anchor 可以强化核心研究方向

限制：

- 项目有多个子方向时，平均分可能稀释强相关论文
- 项目论文数量增加后计算量增长
- 空项目无法仅依靠论文完成推荐
- embedding 相似并不等于严格研究相关

### 4.4 算法 B：Project Profile Rerank

算法 B 使用结构化项目画像和专用 rerank 模型。

```text
项目名称、描述、关注主题
+ anchor papers
+ 最近加入论文
+ core_contribution
+ 用户保存/忽略反馈
→ project_profile
→ 作为 query
→ arXiv candidate title + abstract 作为 document
→ rerank score
→ Top K
```

推荐的结构化项目画像：

```text
研究目标：项目描述
关注主题：用户配置
代表论文：anchor papers
近期兴趣：最近加入论文
排除方向：exclude keywords
```

讨论过的混合评分：

```text
70%：项目画像与候选论文相关度
30%：候选论文与 anchor/代表论文的最高分或 Top 3 平均分
```

优点：

- 项目方向明确
- 支持空项目冷启动
- 可编辑、可解释
- 更适合独立 rerank 模型

限制：

- 项目画像可能压缩掉论文细节
- rerank 调用成本高于单纯 embedding
- 需要确定本地 CrossEncoder 或 API provider
- 需要建立推荐质量评测集

### 4.5 雷达候选与正式论文库的边界

雷达候选不能直接写入正式 `papers` 表。

原因：

- 每天候选会污染论文库
- 未确认论文会错误参与项目画像
- Dashboard、Map、聊天统计会失真
- 忽略、删除、移出项目的语义混乱

正确流程：

```text
arXiv candidate
→ radar candidate
→ project match
→ 用户保存
→ ingest_arxiv_id
→ papers
→ project_papers
```

候选状态：

```text
unread
read
saved
dismissed
```

同一篇候选可以匹配多个项目，每个项目拥有独立分数和处理状态。

### 4.6 雷达数据模型

建议新增四张表。

#### `radar_configs`

- `project_id`
- `enabled`
- `categories`
- `include_keywords`
- `exclude_keywords`
- `profile_override`
- `anchor_paper_ids`
- `top_k`
- `min_score`
- `updated_at`

#### `radar_runs`

- `id`
- `project_id`
- `run_date`
- `status`
- `candidate_count`
- `matched_count`
- `error`
- `started_at`
- `finished_at`

建议约束：

```sql
UNIQUE(project_id, run_date)
```

#### `radar_candidates`

- `arxiv_id`
- `title`
- `abstract`
- `authors`
- `categories`
- `published_date`
- `arxiv_url`
- `first_seen_at`

候选全局保存一次，避免不同项目重复存储元数据。

#### `radar_matches`

- `project_id`
- `candidate_id`
- `run_id`
- `score`
- `reason`
- `state`
- `created_at`

### 4.7 雷达运行机制

```text
FastAPI 启动
→ 检查今天是否已运行
→ 未运行则补跑
→ 到达每日计划时间再次检查
→ 全局获取 arXiv 候选
→ 对 enabled 项目逐个匹配
→ 单个项目失败不影响其他项目
→ 保存运行状态与错误
```

第一版边界：

- 只获取 arXiv
- 只读取 title、abstract、categories
- 不下载所有候选 PDF
- 只为 Top K 生成推荐理由或 TLDR
- 用户保存后才下载 PDF
- 应用关闭时不执行
- 下次启动自动补跑
- 支持手动立即扫描

### 4.8 雷达页面

侧边栏新增`雷达`入口，跟随当前项目。

页面内容：

- 上次扫描时间
- 下次计划扫描时间
- 当前雷达状态
- 立即扫描
- 设置
- 当前项目未读数量

页面 Tabs：

- 今日推荐
- 全部
- 已保存
- 已忽略

推荐项展示：

- 标题
- 作者
- arXiv 分类
- 发布时间
- 匹配分数
- 推荐原因
- 中文 TLDR
- 查看 arXiv
- 加入当前项目
- 忽略

---

## 5. Map 后续规划

### 5.1 Map 基础增强

- 支持作者节点
- 支持机构节点
- 支持标签节点
- 支持笔记节点
- 支持不同节点类型开关
- 支持按年份、领域、标签、作者筛选
- 支持节点和边搜索
- 保存节点位置
- 保存用户布局
- 导出 PNG、HTML、JSON、GraphML

### 5.2 笔记关系 Map

解析 Markdown 中的 `[[wikilink]]`：

```text
论文笔记 A
→ [[论文 B]]
→ 建立 note/paper relation
→ 在 Map 中生成边
```

需要补充：

- wikilink 自动补全
- 标题到 paper ID 的稳定解析
- 同名论文消歧
- 反向链接
- 孤立链接检查
- 删除或重命名后的链接修复

### 5.3 真实 Citation Graph

当前论文 Map 是共享作者图。后续可接入真实引用关系：

- OpenAlex
- Semantic Scholar
- Crossref
- arXiv metadata 可用字段

预期能力：

- 论文引用了谁
- 哪些论文引用当前论文
- 引用路径
- 共同引用
- Bibliographic coupling
- 关键基础论文
- 某项目的研究演进时间线

需要先确定：优先做 citation graph，还是优先做笔记 wikilink graph。前者依赖外部数据源；后者完全本地，更符合当前 local-first 架构。

---

## 6. 笔记后续规划

### 6.1 检索与链接

- 笔记标题、正文全文搜索
- 论文 wikilink 自动补全
- 点击 wikilink 跳转论文或笔记
- 反向链接
- 显示引用当前论文的所有笔记
- 孤立笔记、未解析链接检查
- 笔记关系进入 Map

### 6.2 PDF 阅读联动

- 从 PDF 高亮创建笔记
- 从 PDF 摘录创建带页码的引用块
- 笔记保存 PDF 页码和定位信息
- 从笔记跳转 PDF 对应页面
- 从 PDF 查看当前页面相关笔记
- 高亮、摘录、批注进入统一搜索

建议回链格式：

```text
[p.42](citemap://open?id=<paper_id>&page=42)
```

### 6.3 独立研究笔记

当前笔记主要绑定论文。后续需要决定是否支持：

- 不绑定论文的普通 Markdown 笔记
- 项目综述笔记
- 研究问题笔记
- 实验笔记
- 方法、数据集、模型等概念笔记

如果支持独立笔记，需要新增稳定 note ID，不能继续完全依赖 `paper_id`。

### 6.4 导出与外部工具

- 按论文导出笔记
- 按项目导出笔记库
- 导出 YAML frontmatter
- 导出 wikilink
- 导出 PDF 相对路径
- 导出批注和页码回链
- Obsidian 可直接打开
- 后续评估 Obsidian、Logseq 双向同步

当前已有 Markdown 论文汇总导出函数，但尚未接入 API 和前端。这不等于完整 Obsidian 笔记库导出。

---

## 7. 其他已讨论功能

### 7.1 PDF 深度解析

已经比较和讨论：

- MinerU
- GROBID
- Docling
- pdfplumber
- Camelot
- OCRmyPDF/Tesseract
- PaddleOCR

建议保留 PyMuPDF 作为快速主路径，增加可选深度解析：

```text
PDF 上传
→ PyMuPDF 快速入库
→ 页面立即可用
→ 用户手动或自动提交 MinerU
→ pending/running/done/failed
→ 保存完整 Markdown/JSON
→ 生成 metadata 候选
```

建议提供三种模式：

- 关闭：只使用 PyMuPDF
- 手动：详情页点击`深度解析`
- 自动：入库后后台解析

建议目录：

```text
data/parsed/{paper_id}/full.md
data/parsed/{paper_id}/content_list.json
data/parsed/{paper_id}/source.zip
```

建议新增 `paper_parses` 表。深度解析结果不能写入当前 `md_path`，因为该字段属于用户笔记。

尚未决定：

- 是否接受上传 PDF 到 MinerU Cloud
- 是否需要本地 MinerU
- 是否支持 OCR
- 默认关闭还是默认手动

### 7.2 全文检索与语义检索

计划能力：

- PDF 正文全文索引
- 标题、摘要、正文、笔记、批注统一搜索
- 中英文混合搜索
- 精确词组
- AND、OR、NOT
- 命中上下文
- 关键词高亮
- 跳转 PDF 页面
- 年份、作者、标签、来源、阅读状态组合筛选
- 搜索历史
- 保存搜索条件

语义检索仍需拍板：当前技术决策明确不引入向量数据库，但论文雷达算法 A 又需要 embedding。可采用轻量本地向量文件或 SQLite 扩展，不一定引入独立 vector DB。

### 7.3 PDF 阅读器与批注

计划能力：

- 内置 PDF 阅读器
- 连续滚动
- 缩放
- 大纲和页码跳转
- 记忆阅读位置
- 多颜色高亮
- 高亮附注
- 页面笔记
- 整篇论文笔记
- 批注总览
- 阅读状态
- 星标和待读队列
- 两篇论文分屏阅读

该功能成本较高。自研阅读器体验若明显弱于系统阅读器或 Zotero，可能降低产品体验，需要单独评估。

### 7.4 导入、引用与迁移

计划能力：

- 文件夹递归导入 PDF
- BibTeX 导入
- RIS 导入
- Zotero 库只读导入
- DOI metadata 补全
- 重复论文检测
- arXiv 与正式出版版本关联
- BibTeX 导出
- RIS 导出
- CSL-JSON 导出
- 稳定 citekey
- citekey 自定义规则
- 导出前完整性检查
- LaTeX/Overleaf `.bib` 自动更新
- PDF、metadata、标签、笔记一键完整导出

### 7.5 Tauri 桌面应用

已经确认技术上可行，建议架构：

```text
Tauri 2
├── React/Vite 静态前端
└── PyInstaller 打包 FastAPI sidecar
```

需要改造：

- 新增 `frontend/src-tauri/`
- Python 后端构建各平台 sidecar
- Rust 管理 sidecar 生命周期
- 动态端口和健康检查
- 数据目录迁移到系统 App Data
- 本地随机 token 保护 API
- 打包 Agent 配置资源
- 用户 API Key 不进入安装包

CI 计划：

- 保留现有 Web 流程
- 增加前后端测试 workflow
- 增加 Tauri 三平台构建 workflow
- tag 触发 GitHub Release
- macOS 后续增加签名和 notarization

建议先做 macOS PoC，再决定 Windows、Linux。

### 7.6 本地备份与同步

计划能力：

- 手动备份
- 定时自动备份
- 恢复
- SQLite 完整性检查
- 丢失 PDF 检测和重新定位
- iCloud、Dropbox、OneDrive 本地同步目录检查
- WebDAV
- NAS、S3-compatible 存储
- 同步冲突可视化
- 双版本保留
- 端到端加密

同步不是当前近期重点。需要在桌面数据目录、写入策略、冲突模型稳定后实施。

---

## 8. 参考项目与借鉴方向

| 项目 | 借鉴方向 | 当前状态 |
|---|---|---|
| `TideDra/zotero-arxiv-daily` | 每日 arXiv、embedding 加权推荐 | 已形成雷达方案，未实现 |
| Zotero | PDF、批注、引用管理、迁移 | 参考，未集成 |
| Paperlib | 论文管理、metadata、全文搜索 | 参考 |
| PapersGPT | PDF 问答、多论文问答、本地模型 | 参考，未实现 |
| Zotero-GPT | PDF 摘要和对话交互 | 参考 |
| Reor | Local-first Markdown、语义关联 | 参考 |
| Local Citation Network | 引用网络构建与交互 | 参考，未实现 |
| Citation Gecko | 引用发现和图谱探索 | 参考，未实现 |
| Obsidian Citation Plugin | Markdown 文献笔记 | 已部分采用思路 |
| MinerU | PDF 深度结构化解析 | 已验证方案，未接入 |

参考项目用于理解成熟交互和技术方案。CiteMap 不计划简单复制或组合这些项目，而是围绕“研究项目 + 雷达 + Map + Markdown 笔记”形成自己的工作流。

---

## 9. 功能状态总表

| 功能域 | 当前状态 | 主要下一步 |
|---|---|---|
| 项目管理 | 已实现基础闭环 | 项目画像、雷达配置、项目导出 |
| arXiv 搜索与入库 | 已实现 | 每日自动获取、雷达候选 |
| 本地 PDF 入库 | 已实现单文件 | 文件夹批量、任务队列、去重 |
| PDF metadata | 已实现 arXiv 优化 | DOI、非 arXiv 补全、深度解析 |
| AI 标注 | 已实现 | 本地模型、质量评测、确认与撤销 |
| 论文库 | 已实现基础列表和详情 | 编辑、删除、归档、高级筛选 |
| 团队 Map | 已实现 | 筛选、布局、更多节点类型 |
| 论文 Map | 已实现共享作者关系 | Citation graph、聚类、路径 |
| AI 助手 | 已实现工具型聊天 | 全文证据、页码引用、多论文比较 |
| Markdown 笔记 | 已实现编辑和预览 | 搜索、反链、Map、PDF 回链、导出 |
| 论文雷达 | 已完成方案 | 实现算法 A、调度、页面、状态 |
| 全文检索 | 未实现 | 本地索引、统一搜索、定位 |
| PDF 阅读与批注 | 未实现 | 阅读器、高亮、摘录、页码 |
| 引用导入导出 | 未实现 | BibTeX、RIS、Zotero、citekey |
| MinerU 深度解析 | 已验证，未接入 | provider、任务状态、存储 |
| Tauri 桌面版 | 已评估，未实现 | macOS PoC |
| 备份与同步 | 未实现 | 本地备份优先 |

---

## 10. 建议优先级

### P0：论文雷达 MVP

理由：

- 已经完成详细讨论
- 项目结构已经具备
- 能形成 CiteMap 的主动发现能力
- 与现有 arXiv 入库、AI 标注、项目工作区直接复用
- 相比 PDF 阅读器、全文检索，实施边界更清晰

范围：

1. 四张雷达数据表
2. 项目雷达设置
3. arXiv 每日抓取
4. 启动补跑和立即扫描
5. 算法 A
6. anchor papers
7. 雷达页面
8. 未读、已读、保存、忽略
9. 一键加入项目
10. 基础推荐质量测试

### P1：Map 与笔记闭环

范围：

1. 笔记全文搜索
2. wikilink 自动补全
3. wikilink 跳转和反向链接
4. 笔记关系进入 Map
5. Map 节点类型和筛选
6. 布局保存
7. Obsidian 笔记库导出

### P1：论文管理基础补全

范围：

1. 文件夹批量导入
2. 导入任务和错误报告
3. 去重
4. metadata 编辑
5. 删除、归档
6. 手动标签
7. BibTeX/RIS/Zotero 导入导出

### P2：阅读与全文理解

范围：

1. 全文搜索
2. PDF 阅读器
3. 高亮和批注
4. PDF 页码回链
5. PDF 全文问答
6. 多论文比较
7. MinerU 深度解析

### P2：桌面化与可靠性

范围：

1. Tauri macOS PoC
2. 系统 App Data
3. 本地备份和恢复
4. CI 构建
5. Windows、Linux 评估
6. WebDAV 和加密同步

---

## 11. 建议迭代顺序

### 迭代 1：雷达基础

- `radar_configs`
- `radar_runs`
- `radar_candidates`
- `radar_matches`
- arXiv 每日候选抓取
- 启动补跑
- 手动扫描
- 算法 A
- anchor papers
- Top K 和最低分数

### 迭代 2：雷达产品闭环

- 雷达页面
- 今日推荐、全部、已保存、已忽略
- 未读数量
- 推荐理由和中文 TLDR
- 一键加入项目
- 保存、忽略反馈
- 防重复推荐
- 推荐效果评测

### 迭代 3：Map 与笔记

- 笔记全文搜索
- wikilink 自动补全
- wikilink 跳转
- 反向链接
- 笔记关系 Map
- Map 筛选和布局保存
- Obsidian 项目笔记导出

### 迭代 4：论文管理基础

- 文件夹批量导入
- 导入任务队列
- 重复检测
- metadata 编辑
- 手动标签
- BibTeX、RIS、Zotero 导入导出

### 迭代 5：阅读与全文检索

- 本地全文索引
- PDF 阅读器
- 高亮、摘录、批注
- 页码定位
- 笔记和批注统一搜索
- PDF 问答

### 迭代 6：桌面应用

- Tauri macOS PoC
- FastAPI sidecar
- App Data 迁移
- 本地备份
- CI 构建
- 多平台评估

---

## 12. 当前需要讨论并确定的问题

### 雷达

1. 第一版只实现算法 A，还是同时实现 A/B？
2. embedding 使用本地模型还是 API？
3. anchor papers 只允许手动选择，还是自动加入最近论文？
4. anchor 的额外权重如何设置？
5. 默认每天几点运行？
6. 是否需要浏览器系统通知，还是只显示站内未读？
7. Top K 默认值是 10、20 还是其他数量？
8. 是否在第一版生成 LLM 推荐理由和中文 TLDR？
9. 算法 B 使用本地 CrossEncoder 还是 API rerank？

### Map

10. 优先做真实 citation graph，还是优先做笔记 wikilink graph？
11. 是否将论文、作者、团队、机构、标签、笔记放在一个 Map？
12. 还是保持多个独立 Map，通过 Tabs 切换？
13. Map 是否需要布局保存和导出作为近期功能？

### 笔记

14. 是否支持不绑定论文的独立研究笔记？
15. 是否把 Obsidian 导出放入近期迭代？
16. 笔记与 PDF 的页码回链是否必须依赖内置阅读器？
17. 是否先实现 wikilink 和反向链接，再做 PDF 批注？

### PDF 与 AI

18. 是否接受将 PDF 上传到 MinerU Cloud？
19. MinerU 默认关闭还是默认手动？
20. 是否需要本地 AI，还是继续使用 OpenAI-compatible API？
21. 全文语义检索是否允许使用 embedding？

### 产品顺序

22. 下一阶段是否集中完成论文雷达？
23. Map 与笔记闭环是否排在论文批量导入之前？
24. Tauri 应在核心功能完成后做，还是尽快用桌面版验证真实使用？

---

## 13. 当前建议

建议下一阶段集中完成论文雷达，不同时展开全文搜索、PDF 阅读器、MinerU、Tauri。

第一阶段只实现算法 A：

```text
项目论文 embedding
+ 时间权重
+ anchor 权重
→ 每日 arXiv Top K
→ 站内推荐
→ 保存或忽略
```

原因：

- 方案已经讨论充分
- 最接近参考 repo 的已验证效果
- 无需先解决 project profile 和 rerank 模型选型
- 可以先积累保存、忽略反馈
- 后续可用真实反馈比较算法 A、算法 B 和混合评分

雷达完成后，建议优先连接 Map 与笔记：让 Markdown 中的论文关系进入 Map，让 Map 从“系统计算出的关系”扩展为“研究者主动表达的知识关系”。这会强化 CiteMap 区别于普通论文管理器的核心特征。
