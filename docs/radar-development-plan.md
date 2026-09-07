# CiteMap 论文雷达开发计划

> 更新日期：2026-09-06  
> 目标：电脑关闭时通过 GitHub Actions 发送每日论文邮件；CiteMap 重新打开后补齐离线期间的推荐历史、邮件点击状态、应用内操作。

## 1. 已确定架构

```text
GitHub Actions
  唯一自动扫描器
  获取 arXiv 新论文
  计算推荐
  写入远端 Radar Store
  发送邮件

远端 Radar Store
  保存离线期间的雷达消息
  保存邮件投递状态
  保存 read / saved / dismissed 状态
  提供邮件点击跳转
  提供 CiteMap 增量同步

CiteMap
  本地保存完整论文库、PDF、笔记、Map
  打开时同步远端历史
  展示雷达结果
  保存、忽略、标记已读
  保存后正式入库
```

原则：

- Action 是唯一每日自动扫描器。
- CiteMap 打开时默认只同步，不自动重复扫描。
- CiteMap 的“立即扫描”是手动补救、测试入口。
- 远端不保存 PDF、笔记、聊天记录、完整 SQLite。
- 本地保存完整雷达历史；远端保存 Action 离线期间所需的雷达项和状态。
- 邮件点击论文链接后标记 `read`。打开邮件不算已读。

## 2. 数据和状态约定

用户状态与邮件投递状态分开：

```text
user_state: unread | read | saved | dismissed
emailed_at: NULL 或已发送时间
```

含义：

- `unread`：用户尚未通过邮件或应用查看。
- `read`：用户点击邮件论文链接，或在 CiteMap 打开论文详情。
- `saved`：用户确认入库并加入项目。
- `dismissed`：用户明确忽略。
- `emailed_at`：该项目、该 arXiv 论文已发送过邮件。

发送规则：

```text
只发送 emailed_at IS NULL 的候选
```

发送成功后写入 `emailed_at`。不删除 `read`、`saved`、`dismissed` 记录，只在发送前排除已投递项。

同步采用增量游标：

```text
remote_cursor = 单调递增 event_id
```

应用每次同步：

```text
读取 after=remote_cursor 的事件
→ 幂等合并本地状态
→ 成功后保存 next_cursor
```

本地离线操作进入 pending queue。网络恢复后重试。状态不允许从 `saved` 降级为 `read`。

## 3. 开发节点

### Node 0：架构和契约冻结

状态：已完成

交付：

- 本文档。
- Action、Radar Store、CiteMap 的职责边界。
- 用户状态、投递状态、同步游标定义。
- 默认不重复发送规则。

验收：三端可以独立描述同一篇论文的唯一键和状态变化。

### Node 1：本地雷达数据模型

状态：已完成

范围：

- 新增 `radar_configs`。
- 新增 `radar_runs`。
- 新增 `radar_candidates`。
- 新增 `radar_matches`。
- 新增本地同步游标。
- 新增本地 pending operations。
- 项目删除时清理雷达配置和匹配记录。

暂不做：远端、邮件、embedding、前端页面。

验收：pytest 覆盖建表、重复约束、状态迁移、旧库初始化、幂等写入。已通过 16 个相关测试。

### Node 2：本地 arXiv 候选抓取

状态：已完成

范围：

- 复用 daily arxiv 的 arXiv RSS/API 思路。
- 首版只抓 arXiv。
- 按项目 categories、include keywords、exclude keywords 过滤。
- 候选只写 `radar_candidates`，不写 `papers`。
- 按日期和 arXiv ID 去重。
- 记录 `radar_runs` 状态和错误。

验收：重复扫描不重复生成候选；单项目失败不影响其他项目。已通过 21 个累计相关测试。

### Node 3：推荐算法 A

状态：已完成基础排序核心

范围：

- 复用 daily arxiv 的 SentenceTransformer reranker/embedding 配置。
- 首版使用 `title + abstract`。
- 项目论文按 `project_papers.added_at` 排序。
- 使用时间衰减权重和 cosine similarity。
- 默认支持本地 SentenceTransformer provider；API provider、lexical fallback 留接口。
- embedding 缓存不进入远端；GitHub Actions 使用 Hugging Face cache 复用模型。
- anchor papers 作为轻量额外权重，不做复杂 profile rerank。

验收：固定测试语料下分数稳定；空项目、单论文项目、无 abstract 候选有明确结果。已通过 27 个累计相关测试。Embedding provider 接入仍由后续运行配置完成。

### Node 4：本地雷达 API

状态：已完成

范围：

```text
GET  /api/radar/config
PUT  /api/radar/config
POST /api/radar/scan
GET  /api/radar/matches
PATCH /api/radar/matches/{id}
POST /api/radar/matches/{id}/save
POST /api/radar/sync
GET  /api/radar/status
```

验收：当前项目隔离正确；保存操作调用现有 `ingest_arxiv_id`；候选未保存前不进入正式论文表。已通过 API 测试。

### Node 5：雷达前端页面

状态：已完成

范围：

- 新增 `/radar` 路由和侧边栏入口。
- 今日推荐、全部、已保存、已忽略。
- 分数、推荐原因、发布时间、arXiv 链接。
- 标记已读、保存、忽略。
- 立即扫描。
- 本地最近运行状态。

验收：项目切换隔离；保存后论文列表、Dashboard、Map 可见；刷新页面状态不丢失。Vitest 68/68、生产构建通过。

### Node 6：远端 Radar Store

状态：已完成

范围：

- Worker + D1 或等价极简服务。
- 保存项目雷达 profile snapshot。
- 保存 radar item、`emailed_at`、`user_state`。
- 追加事件并返回单调 `event_id`。
- 提供增量同步接口。
- 提供签名邮件跳转接口。

最小接口：

```text
POST /profiles/{project_id}
POST /items
GET  /sync?after={event_id}
POST /items/{id}/state
GET  /r/{token}
```

验收：应用离线期间远端能保留推荐；应用重新打开可补齐历史；重复同步幂等。Worker + D1 schema、HTTP 协议客户端已完成。

### Node 7：GitHub Actions + 邮件

状态：已完成

范围：

- 新增 `.github/workflows/radar.yml`。
- `schedule` + `workflow_dispatch`。
- Action 调用共享 Radar Core，不调用 FastAPI 本地服务。
- 读取远端 profile snapshot。
- 获取每日 arXiv 新论文并排序。
- 只发送 `emailed_at IS NULL` 的候选。
- 发送成功后写入 `emailed_at`。
- 邮件链接经过 `/r/{token}`，点击后标记 `read` 再跳转 arXiv。

验收：电脑关闭时 Action 可完成扫描、写入、发信；重复运行不重复发送；邮件点击状态可被应用同步。Action、SMTP、点击跳转已完成。

### Node 8：离线同步和冲突处理

状态：已完成

范围：

- 应用启动同步远端事件。
- 本地 pending operation 重试。
- 合并邮件点击、应用查看、保存、忽略。
- 处理网络失败、Action 重试、应用重复启动。
- 保证 `saved` 不被旧 `read` 覆盖。

验收场景：

1. 应用关闭 30 天，Action 生成 30 天推荐，打开后全部可见。
2. 应用关闭期间点击邮件，打开后显示 `read`。
3. 应用离线保存，联网后远端显示 `saved`。
4. Action 重跑不重复发送。
5. 同一论文命中两个项目，状态互不覆盖。相关后端测试通过。

### Node 9：配置页和运维体验

状态：已完成云端部署文档与雷达页连接入口；不再开发本地云端配置向导

范围：

- 项目雷达配置页。
- LLM、embedding、SMTP 只通过 GitHub Actions Secrets/Variables 配置。
- 雷达页只保存远端 Radar Store URL、token。
- 连接请求验证 Worker、token、profile 发布。
- 测试邮件、Action 状态在 GitHub Actions 页面查看。

Worker token 与 URL 保存在当前浏览器 localStorage，不进入 SQLite。LLM、SMTP、Cloudflare Secrets 不进入本地前端。

### Node 10：推荐质量和稳定性验收

状态：基础稳定性验收完成，推荐质量评测待真实数据

范围：

- 固定历史数据集。
- Precision@5、保存率、忽略率。
- arXiv 429、RSS 失败、embedding 失败、SMTP 失败重试。
- 远端不可用时本地雷达仍可读历史。
- 运行日志和错误提示。

当前验证结果：

- 后端全量 pytest：192 passed。
- 前端 Vitest：68 passed。
- 前端 production build：通过。
- Worker JavaScript syntax check：通过。
- `git diff --check`：通过。

## 4. 暂不实现

- bioRxiv、medRxiv、ChemRxiv。
- Project Profile Rerank。
- 邮件打开 tracking pixel。
- 已发送未查看论文的自动重发。
- 完整云端论文库。
- 云端 PDF、笔记、聊天同步。
- 本地和 Action 同时自动定时扫描。

## 5. 推荐执行顺序

```text
Node 1 → Node 2 → Node 3 → Node 4 → Node 5
→ Node 6 → Node 7 → Node 8 → Node 9 → Node 10
```

每个节点必须：

1. 先写测试。
2. 完成实现。
3. 运行相关测试。
4. 更新文档中的节点状态。
5. 再进入下一个节点。
