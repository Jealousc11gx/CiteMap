# CiteMap

本地优先的论文管理、关系图谱、研究笔记工具。支持 arXiv 发现、本地 PDF 入库、AI 标注、引用图谱、智能聊天、Markdown 笔记、论文雷达。

## 功能

- 论文：arXiv 搜索、arXiv ID 入库、本地 PDF 上传、PDF 下载、批量处理
- 标注：中文 TLDR、核心贡献、领域与标签、团队和机构识别
- 图谱：团队视图、论文关系视图、引用视图、相似度视图；支持搜索、缩放、拖拽、入口论文高亮
- 聊天：arXiv 搜索、本地论文查询、摘要相似度检索、流式回答
- 笔记：Markdown 模板、frontmatter、论文与 PDF 路径绑定、Obsidian 兼容
- 雷达：GitHub Actions 定时抓取 arXiv，使用 embedding 相似度排序，生成中文摘要，邮件通知；Cloudflare Worker + D1 保存云端状态

## 本地启动

### 环境

- Python 3.12+
- Node.js 24+
- OpenAI 兼容 API Key（标注、聊天、雷达 LLM 摘要）

### 配置后端

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`：

```env
LLM_API_KEY=your-openai-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.5
```

### 启动后端

macOS/Linux：

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Windows：

```powershell
cd backend
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

后端地址：`http://localhost:8000`。健康检查：`GET /api/health`。

### 启动前端

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

浏览器打开：`http://localhost:3000`。Vite 将 `/api` 代理到 `http://localhost:8000`。

## GitHub Actions 部署

Fork 用户可以不安装 Python、Node、uv、Wrangler，也不需要使用命令行：

1. Fork 本仓库。
2. 在 `Settings → Secrets and variables → Actions` 配置 Cloudflare、雷达 Token、LLM、SMTP 参数。
3. 打开 `Actions → Deploy Radar Worker → Run workflow`，创建/迁移 D1 并部署 Worker。
4. 将部署日志中的 Worker URL 写入 `RADAR_REMOTE_URL` Secret。
5. 打开 `Actions → CiteMap Radar Test → Run workflow`，验证抓取、排序、LLM、邮件链路。
6. `CiteMap Radar` 默认每天 UTC 22:00（北京时间次日 06:00）自动执行。需要立即运行时点击 `Run workflow`。

完整 Secret、Variable、Cloudflare D1 配置见 [GitHub Actions 论文雷达部署](docs/radar-github-action-setup.md)。

## 雷达排序算法

当前排序与 `zotero-arxiv-daily` 历史版一致：

1. 项目论文按加入时间从新到旧排列。
2. 仅使用论文 abstract 生成 embedding。
3. 计算候选论文与项目论文的 cosine similarity。
4. 使用 `1 / (1 + log10(rank + 1))` 时间衰减权重。
5. 加权结果乘以 10，按分数降序取 Top K。

标题参与、anchor paper 加权、最低分二次过滤已关闭。默认本地 embedding 模型为 `jinaai/jina-embeddings-v5-text-nano-retrieval`。

## 测试

后端：

```bash
source backend/.venv/bin/activate
pytest -q
```

前端：

```bash
cd frontend
npm run test:run
npm run build
```

## 目录

```text
CiteMap/
├── backend/                 # FastAPI API、论文处理、雷达 CLI
├── frontend/                # React + Vite 前端
├── radar-worker/             # Cloudflare Worker + D1 schema/migrations
├── data/                    # 本地 SQLite、PDF、Markdown 笔记
├── docs/                    # 部署、技术决策、开发规划
├── images/                  # README 界面截图
└── .github/workflows/       # CI、Worker 部署、雷达定时任务
```

## 主要 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/papers` | 论文列表，最新入库优先 |
| POST | `/api/papers/ingest-arxiv` | arXiv 入库 |
| POST | `/api/papers/ingest-pdf` | 本地 PDF 入库 |
| POST | `/api/papers/{id}/annotate` | AI 标注 |
| GET | `/api/graph/team` | 团队图谱 |
| GET | `/api/graph/paper` | 论文图谱 |
| GET | `/api/graph/citation` | 引用图谱 |
| GET | `/api/graph/similarity` | 相似度图谱 |
| GET | `/api/radar/matches` | 雷达推荐 |
| POST | `/api/radar/sync` | 同步云端雷达状态 |
| GET | `/api/health` | 健康检查 |

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE)。
