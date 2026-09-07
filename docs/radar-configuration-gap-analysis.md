# 论文雷达配置能力核验

## lexical embedding 是什么

当前代码中的 `lexical` 是 hashing vector fallback：把文本切成词，使用稳定 hash 映射到固定维度向量，再计算 cosine similarity。

```text
文本
→ token
→ hash bucket
→ 512 维词频向量
→ cosine similarity
```

它不理解语义，不等同于 daily arxiv 的 SentenceTransformer embedding。适合：

- 本地无模型时跑通流程。
- 单元测试。
- 关键词相似的简单领域。

不适合作为正式推荐质量方案。正式 Action 应配置以下二选一：

```text
local：SentenceTransformer / daily arxiv 使用的 embedding model
api：OpenAI-compatible embeddings API
```

## Action 是否需要 rerank / embedding 配置

需要。Action 是电脑关闭时唯一执行推荐的环境。若 Action 使用 lexical fallback，线上邮件推荐和本地语义推荐不是同一套质量标准。

daily arxiv 的基础 rerank 读取：

- 用户论文 `title`、`abstractNote`、`dateAdded`。
- 候选论文 `title`、`abstract`。
- 本地或 API embedding model。
- 时间衰减权重。

CiteMap Action 需要：

- `RADAR_EMBEDDING_PROVIDER`：`local` 或 `api`。
- `RADAR_EMBEDDING_MODEL`。
- local 模型名，或 API Key、Base URL。
- `top_k`、`min_score`。
- 项目 categories、include/exclude keywords。

`lexical` 只能作为开发 fallback，正式配置页不应把它作为推荐默认值。当前保留它是为了无 Key 运行 smoke test。

## 当前配置能力核验

| 能力 | 当前状态 | 是否需要补全 |
|---|---|---|
| LLM API 读取 | Action 读取 GitHub Secrets/Variables | 云端配置完成 |
| LLM model list | GitHub Variable `LLM_MODEL` | 用户填写 API 支持的模型 |
| embedding provider | Action 读取 GitHub Secrets/Variables | 云端配置完成 |
| lexical fallback | 已有 | 仅保留为开发 fallback |
| local SentenceTransformer | 已接入 | 默认复用 daily arxiv 模型；Action 需要缓存 |
| SMTP 发送 | Action 代码、测试 workflow 已有 | 通过 `CiteMap Radar Test` 验证 |
| Worker URL/token | 雷达页单一连接表单 | 连接时通过同步请求验证 |
| profile 发布 | 雷达页连接、保存项目配置时发布 | 已实现 |
| GitHub Secrets | workflow 已有 | 用户在 Fork 的 GitHub Settings 配置 |
| GitHub workflow 状态 | GitHub Actions 页面 | 本地前端不代理 GitHub 管理操作 |
| Cloudflare D1 创建 | Cloudflare Dashboard | 首次部署前创建一次 |

## 当前配置边界

云端配置沿用 daily arxiv 的职责分组：

```text
Zotero corpus → CiteMap project profile
source → arXiv categories
reranker → embedding provider/model
llm → LLM API/model
email → SMTP sender/receiver
executor → top_k、schedule、enabled
```

GitHub 管理：

- Cloudflare、LLM、embedding、SMTP Secrets/Variables。
- Worker deployment、D1 migration、雷达定时任务。
- 测试 workflow、运行日志。

本地 CiteMap 管理：

- 项目 categories、关键词、阈值、启用状态。
- Worker URL、`RADAR_TOKEN` 连接。
- profile 发布、推荐与阅读状态同步。

不再实现本地 Cloudflare/SMTP/模型向导。Fork 用户在 GitHub Secrets/Variables 配置云端参数；本地雷达页只连接 Worker、发布 profile、同步结果与状态。
