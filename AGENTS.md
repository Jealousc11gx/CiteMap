# CiteMap - AI Coding Agent Guide

> 面向 AI 编码代理的项目速查手册。如果你需要更多上下文，请阅读 `README.md` 和 `docs/technical-decisions.md`。

---

## 1. 项目概述

CiteMap 是一套面向个人研究的论文管理工具，覆盖从论文发现到知识沉淀的完整工作流：arXiv 搜索与入库、PDF 上传、智能标注、知识图谱（团队视图 / 论文视图）、智能聊天、Markdown 笔记管理。

- 当前版本：v0.4.0（MVP 开发中）
- 定位：本地优先、单用户、轻量运维
- 许可证：Apache License 2.0

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Python 3.12 + Uvicorn |
| 前端 | React 19 + Vite 7 + TypeScript |
| UI | shadcn/ui + Tailwind CSS 3 + Radix UI |
| 数据库 | SQLite（单文件 `data/papers.db`） |
| 图谱 | NetworkX（计算）+ PixiJS + d3-force（渲染） |
| AI | OpenAI 兼容接口（通过 Kimi Agent SDK 调用） |
| PDF | PyMuPDF（fitz） |
| 测试 | pytest（后端）+ Vitest（前端） |

---

## 3. 目录结构与核心模块

```
CiteMap/
├── backend/
│   ├── main.py                    # FastAPI 入口，所有 API 路由
│   ├── paper_graph/
│   │   ├── database.py            # SQLite schema、CRUD、聊天会话/消息
│   │   ├── ingest.py              # arXiv 搜索/入库、本地 PDF 入库、PDF 元数据提取
│   │   ├── annotate.py            # LLM 智能标注（核心贡献 + 团队识别）
│   │   ├── graph.py               # NetworkX 图谱构建 + PyVis HTML 导出
│   │   ├── notes.py               # Markdown 笔记 CRUD、frontmatter 解析
│   │   ├── export.py              # Markdown 格式图谱导出
│   │   ├── chat_agent.py          # Kimi Agent SDK Session 运行器（同步/流式）
│   │   ├── chat_tools.py          # 聊天工具实现（schema + 执行函数）
│   │   └── kimi_tools.py          # CallableTool2 包装器，供 agent.yaml 使用
│   ├── tests/
│   │   ├── conftest.py            # pytest fixtures：tmp_db、client、sample_paper
│   │   ├── test_main.py           # FastAPI TestClient 集成测试
│   │   ├── test_ingest.py         # 入库/解析/搜索单元测试
│   │   ├── test_annotate.py       # 标注逻辑 + LLM 降级测试
│   │   ├── test_graph.py          # 图谱构建 + 可视化导出测试
│   │   ├── test_notes.py          # 笔记系统 + frontmatter 测试
│   │   └── test_export.py         # Markdown 导出测试
│   ├── agent.yaml                 # Kimi Agent SDK 工具声明
│   ├── requirements.txt           # Python 依赖
│   ├── .env.example               # 环境变量模板
│   └── .env                       # 本地 LLM 配置（不提交）
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # React Router 路由配置
│   │   ├── main.tsx               # 入口
│   │   ├── pages/                 # Dashboard、Papers、Graph、Chat、Notes、PaperDetail
│   │   ├── components/            # Layout、PixiGraph、NoteEditor、FileTree、UI 组件
│   │   ├── services/api.ts        # 所有 API 调用（含 SSE 流式聊天）
│   │   ├── types/index.ts         # TypeScript 类型定义
│   │   └── lib/utils.ts           # 工具函数（cn 等）
│   ├── package.json
│   ├── vite.config.ts             # Vite 配置 + Vitest 配置 + API 代理
│   ├── tsconfig.json
│   └── tailwind.config.js
├── data/
│   ├── papers.db                  # SQLite 数据库（运行时生成）
│   ├── pdfs/                      # PDF 原文存储
│   └── notes/                     # Markdown 笔记存储
├── docs/
│   └── technical-decisions.md     # 技术选型决策记录
├── pyproject.toml                 # Python 项目配置 + pytest 配置
├── test_e2e.py                    # 端到端流程验证脚本
└── README.md
```

---

## 4. 构建与运行命令

### 环境要求

- Python 3.12+
- Node.js 24+（已验证 v24.16.0）
- OpenAI 兼容 API Key（用于智能标注和聊天 Agent）

### 后端

```bash
cd backend
.venv\Scripts\activate          # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

- 默认地址：`http://localhost:8000`
- 健康检查：`GET /api/health` 或 `GET /health`
- 后端日志：`backend/server.log`（超过 5MB 启动时自动清空）

### 前端

```bash
cd frontend
npm install
npm run dev -- --port 3000      # 或默认 5173
```

- 默认地址：`http://localhost:3000`（或 `http://localhost:5173`）
- Vite 开发服务器自动代理 `/api` 到 `http://localhost:8000`
- CORS 白名单：`http://localhost:3000`、`http://localhost:5173`

### E2E 验证

```bash
python test_e2e.py
```

该脚本会创建临时数据库，验证数据库初始化、arXiv 搜索/入库、图谱构建、笔记系统全流程。

---

## 5. 测试策略

### 后端测试

```bash
cd backend
pytest                           # 运行全部测试
pytest -k test_graph             # 运行指定模块
```

- **测试发现**：`pyproject.toml` 配置 `testpaths = ["backend/tests"]`、`pythonpath = ["backend"]`
- **异步模式**：`asyncio_mode = "auto"`
- **核心模式**：
  - `conftest.py` 提供 `tmp_db`（临时 SQLite）、`sample_paper`、`client`（TestClient）
  - `test_main.py` 通过 monkeypatch 替换 `DB_PATH` 实现隔离
  - 大量使用 `unittest.mock` 模拟 LLM 响应和 arXiv 客户端
- **覆盖率配置**：`pyproject.toml` 中 `[tool.coverage.run]` 指向 `backend/paper_graph`

### 前端测试

```bash
cd frontend
npm run test:run                 # 非交互运行
npm run test                     # 交互模式（watch）
```

- **测试环境**：Vitest + Node 环境（非 jsdom）
- **配置位置**：`vite.config.ts` 中的 `test` 字段
- **测试范围**：
  - `services/api.test.ts`：API 函数成功/失败路径
  - `pages.test.tsx`：页面组件可渲染性验证
  - **不引入组件交互测试**（项目规模小，手动测试成本低）

### E2E

- `test_e2e.py`：Python 集成脚本，覆盖数据库初始化、入库、标注、图谱、笔记全流程
- **不引入 Playwright/Cypress**：个人项目迭代快，E2E 维护成本高

---

## 6. 数据存储约定

### SQLite 数据库

- 路径：`data/papers.db`（运行时自动创建）
- 核心表：`papers`、`authors`、`institutions`、`paper_authors`、`paper_institutions`、`teams`、`team_members`、`paper_teams`、`chat_sessions`、`chat_messages`
- `init_db()` 会自动创建表并兼容旧库（如动态添加 `md_path` 列）

### 论文 ID 格式

- arXiv 入库：`arxiv_<arxiv_id>`（如 `arxiv_2402.09199`）
- 本地 PDF：`local_<file_hash[:12]>`
- 统一通过 `paper_id` 参数引用

### 文件存储

- PDF：`data/pdfs/{paper_id}.pdf`
- 笔记：`data/notes/{paper_id}.md`
- 笔记 frontmatter 格式：YAML-like，字段包括 `title`、`authors`、`published`、`categories`、`arxiv`、`pdf`

---

## 7. AI / LLM 集成

### 环境变量（`backend/.env`）

```env
LLM_API_KEY=your-openai-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.5
```

可选：`LLM_PROVIDER_TYPE`、`LLM_CAPABILITIES`、`LLM_MAX_CONTEXT_SIZE`

### Kimi Agent SDK 配置

- `chat_agent.ensure_kimi_config()` 会根据 `backend/.env` 生成/更新 `~/.kimi/config.toml`
- 若 `~/.kimi/config.toml` 已有可用配置且环境变量未配，直接复用
- 默认 `provider_type` 为 `openai_legacy`

### 聊天架构

- 前端 SSE 流式：`POST /api/chat/sessions/{session_id}/messages/stream`
- 后端运行 `run_agent_stream()` → Kimi Session turn → yield SSE 事件
- 工具调用自动审批（`_auto_approve`），工具结果回传给前端展示
- 非流式兼容接口：`POST /api/chat`（写入默认会话）

### 标注 Prompt 规范

- 强制 JSON 输出：`response_format={"type": "json_object"}`
- 低温采样：`temperature=0.3`
- abstract 截断 3000 字符
- 后处理清洗 markdown 代码块标记（` ```json ... ``` `）

---

## 8. 前端架构

### 路由

| 路径 | 组件 | 功能 |
|---|---|---|
| `/` | `Dashboard` | 统计卡片 + 最近入库 |
| `/papers` | `Papers` | 论文列表、上传、搜索、标注 |
| `/papers/:id` | `PaperDetail` | 论文详情 |
| `/graph` | `Graph` | 知识图谱（团队/论文视图） |
| `/chat` | `Chat` | 智能聊天（会话管理 + 流式） |
| `/notes` | `Notes` | 笔记列表 + 编辑器 |

### 图谱渲染

- `PixiGraph.tsx`：PixiJS 场景图 + d3-force 力导向布局
- 支持拖拽节点、缩放、平移、点击查看详情
- 自适应暗色模式（监听 `dark` class）

### API 层

- `services/api.ts`：所有 REST/SSE 调用
- 统一 `API_BASE = "/api"`，开发环境由 Vite proxy 转发

---

## 9. 后端 API 路由速查

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/papers` | 列出论文（支持 `source`、`q` 查询） |
| GET | `/api/papers/{id}` | 论文详情 |
| POST | `/api/papers/ingest-pdf` | 本地 PDF 上传入库 |
| POST | `/api/papers/ingest-arxiv` | arXiv ID 入库 |
| POST | `/api/papers/batch-ingest` | 批量 arXiv 入库 |
| POST | `/api/papers/{id}/annotate` | 单篇智能标注 |
| POST | `/api/papers/annotate-all` | 批量标注所有未标注 |
| POST | `/api/papers/batch-annotate` | 批量标注（同 annotate-all） |
| POST | `/api/papers/{id}/download-pdf` | 下载 arXiv PDF |
| GET | `/api/papers/search` | 搜索 arXiv 并自动入库 |
| GET | `/api/papers/search-arxiv` | 仅搜索 arXiv，不自动入库 |
| GET | `/api/graph/team` | 团队图谱节点/边 |
| GET | `/api/graph/paper` | 论文图谱节点/边 |
| GET/POST | `/api/chat/sessions` | 列出/创建会话 |
| DELETE | `/api/chat/sessions/{id}` | 删除会话 |
| GET | `/api/chat/sessions/{id}/messages` | 获取会话消息 |
| POST | `/api/chat/sessions/{id}/messages` | 会话内发送消息（非流式） |
| POST | `/api/chat/sessions/{id}/messages/stream` | 会话内发送消息（SSE 流式） |
| POST | `/api/chat` | 兼容旧接口，写入默认会话 |
| GET | `/api/notes` | 列出所有笔记 |
| GET | `/api/notes/{id}` | 获取笔记 |
| POST | `/api/notes/{id}` | 保存笔记 |
| POST | `/api/notes/{id}/template` | 创建笔记模板 |
| DELETE | `/api/notes/{id}` | 删除笔记 |
| GET | `/api/health` | 健康检查 |

---

## 10. 代码风格与约定

### Python

- 中文注释为主，模块 docstring 使用 `"""..."""`
- 函数签名优先使用 `Path | None` 类型提示
- SQLite 连接统一通过 `get_connection(db_path)` 获取，返回 `sqlite3.Row` factory
- DataFrame 返回前统一做 `df.where(pd.notnull(df), None)` 确保 JSON 安全
- 异常处理：前端返回结构化 JSON；LLM 错误返回 503 + 中文提示
- 路径处理统一使用 `pathlib.Path`

### TypeScript / React

- 路径别名：`@/` 映射到 `src/`
- 组件风格：函数组件 + Hooks
- UI 组件基于 shadcn/ui（Radix UI + Tailwind）
- 状态管理：组件本地 `useState` + `useEffect`，无全局状态管理库
- 错误处理：`ErrorAlert` 统一展示，带 `suggestion` 和 `onRetry`
- 加载状态：`Skeleton` 组件 + `loading` boolean

---

## 11. 安全注意事项

- **路径遍历防护**：PDF 上传使用 `os.path.basename()` 截断文件名
- **文件类型校验**：仅允许 `.pdf` 扩展名
- **NaN 清洗**：所有返回前端的 JSON 统一替换 `NaN`/`NaT` 为 `null`
- **LLM 输出容错**：标注模块支持 markdown 代码块包裹的 JSON、缺失字段等降级场景
- **无认证/鉴权**：当前为本地单用户工具，CORS 仅白名单开发端口
- **密钥管理**：`backend/.env` 不提交；LLM Key 仅存储在本地 `.env` 和 `~/.kimi/config.toml`

---

## 12. 明确不采用的技术

| 技术 | 原因 |
|---|---|
| Embedding / 向量数据库 | 个人库规模不需要，运维成本高 |
| Neo4j / 图数据库 | NetworkX 足够，个人图谱 < 1000 节点 |
| PostgreSQL / MySQL | SQLite 足够，单用户本地场景 |
| Playwright / Cypress | 个人项目，手动测试 + 单元测试足够 |
| LangChain / LlamaIndex | 场景简单，直接调用 OpenAI API 更可控 |
| 微服务架构 | 单体 FastAPI 足够 |
| Docker 化 | 本地直接运行，增加复杂度 |

---

## 13. 快速排障

| 问题 | 排查方向 |
|---|---|
| 前端无法连接后端 | 确认后端运行在 `localhost:8000`，前端 CORS 白名单包含当前端口 |
| LLM 服务不可用 | 检查 `backend/.env` 中的 `LLM_API_KEY`、`LLM_BASE_URL`；查看 `backend/server.log` |
| PDF 解析失败 | PyMuPDF 对扫描版 PDF 支持有限，后续可考虑 `pdfplumber` |
| 前端代理失败 | 检查 `frontend/vite.config.ts` 中 `server.proxy` 配置 |
| 聊天无响应 | 确认 `backend/agent.yaml` 存在且路径正确；检查 Kimi SDK 配置 |

---

## 14. 相关文档

- `README.md`：项目简介、界面预览、快速启动
- `docs/technical-decisions.md`：详细技术选型与 reconsider 条件
- `docs/prd.md`：产品需求文档
- `backend/AGENTS.md`：Kimi 聊天 Agent 的系统提示词（非开发文档）
