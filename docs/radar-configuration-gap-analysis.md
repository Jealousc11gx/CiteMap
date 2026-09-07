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
| LLM API 读取 | 只读 `.env` | 是，需页面保存、脱敏、测试 |
| LLM model list | 已有 `/api/llm/models` | 需接入配置页 |
| embedding provider | 环境变量读取 | 是，需 provider/model/API 测试 |
| lexical fallback | 已有 | 仅保留为开发 fallback |
| local SentenceTransformer | 已接入 | 默认复用 daily arxiv 模型；Action 需要缓存 |
| SMTP 发送 | Action 代码已有 | 是，需 SMTP 连接测试、测试邮件 |
| Worker URL/token | 雷达页面手填 | 是，需健康检查、脱敏保存 |
| profile 发布 | API 已有 | 需配置页按钮和结果展示 |
| GitHub Secrets | workflow 已有 | 未实现页面配置 |
| GitHub workflow 状态 | 未实现 | 后续完整向导补全 |
| Cloudflare D1 创建 | 未实现 | 后续部署向导补全 |

## 第一版简化配置页

先模仿 daily arxiv 的配置结构，字段分组：

```text
Zotero corpus → CiteMap project profile
source → arXiv categories
reranker → embedding provider/model
llm → LLM API/model
email → SMTP sender/receiver
executor → top_k、schedule、enabled
```

第一版只做：

- 浏览器 localStorage 保存表单草稿。
- 展示当前配置状态。
- 生成 GitHub Actions Secrets/Variables 清单。
- 一键复制清单。
- 链接到 GitHub Actions 设置页面。

不做：

- 自动写 GitHub Secrets。
- 自动创建 Cloudflare D1。
- 自动部署 Worker。
- 在页面明文回显已保存 Secret。

完整配置向导再补：本地安全存储、SMTP 测试、embedding 测试、Worker health、GitHub CLI/OAuth、Action 状态。当前配置页已生成 daily arxiv 本地模型的 Action 参数。
