# CiteMap 论文雷达部署

CiteMap 的论文雷达由 GitHub Actions 执行抓取、相似度排序、中文摘要、邮件发送。Cloudflare Worker + D1 保存项目画像、推荐结果、阅读状态。

## 部署流程

1. Fork 本仓库，开启 `Actions`。
2. 在 Cloudflare 创建 D1，名称建议为 `citemap-radar`，记录 `Database ID`、`Account ID`。
3. 在 GitHub `Settings → Secrets and variables → Actions` 添加必填 Secrets、按需覆盖 Variables。
4. 运行 `Actions → Deploy Radar Worker → Run workflow`。
5. 将日志中的 Worker URL 写入 `RADAR_REMOTE_URL` Secret。
6. 运行 `Actions → CiteMap Radar Test → Run workflow` 验证。
7. 正式 workflow `CiteMap Radar` 默认每天 UTC `22:00` 运行。可在 Actions 页面手动 `Run workflow`。

配置完成后，在 CiteMap 雷达页填写 Worker URL、RADAR_TOKEN，点击“连接并发布画像”。再在“设置”中配置当前项目的 arXiv categories、关键词、Top K、抓取上限、计算模式。

雷达按项目独立运行。每个启用雷达的项目都需要自己的 categories、reference papers、Top K 配置。Action 会读取 Worker 中全部已启用项目，逐个计算。项目有新的推荐时发送一封邮件，邮件主题包含项目名；没有 reference papers、没有候选、或推荐已发送过的项目不会发邮件。

## GitHub Secrets

以下 Secrets 没有默认值，需要按场景填写。

### Worker 部署

| Name | 内容 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token，需 Workers Scripts Edit、D1 Edit 权限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `CLOUDFLARE_D1_DATABASE_ID` | `citemap-radar` 的 D1 Database ID |
| `RADAR_REMOTE_TOKEN` | 自行生成的长随机 Token，同时作为 Worker 的 `RADAR_TOKEN` |

### 雷达运行必填

| Name | 内容 |
|---|---|
| `RADAR_REMOTE_URL` | 部署后的 Worker URL |
| `RADAR_REMOTE_TOKEN` | 与 Worker 部署使用的 Token 相同 |
| `RADAR_EMAIL_SENDER` | 发件邮箱 |
| `RADAR_EMAIL_RECEIVER` | 收件邮箱 |
| `RADAR_EMAIL_PASSWORD` | SMTP 授权码或 App Password，不是登录密码 |
| `LLM_API_KEY` | OpenAI 兼容 API Key |
| `RADAR_EMBEDDING_API_KEY` | 仅当 `RADAR_EMBEDDING_PROVIDER=api` 时填写 |

## GitHub Variables

### 必须填写

| Name | 何时填写 | 示例 |
|---|---|---|
| `RADAR_SMTP_HOST` | 发送邮件时必填 | `smtp.qq.com` |
| `LLM_BASE_URL` | 使用非默认 OpenAI 兼容服务时填写 | `https://api.openai.com/v1` |
| `LLM_MODEL` | 使用自定义模型名时填写 | `gpt-4o-mini` |

### 可保持默认

以下值已在 workflow 中提供默认值，无需重复创建。需要切换 provider、模型或调试时再覆盖。

| Name | 推荐值 |
|---|---|
| `RADAR_SMTP_PORT` | `465` |
| `RADAR_EMBEDDING_PROVIDER` | `local` |
| `RADAR_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v5-text-nano-retrieval` |
| `RADAR_EMBEDDING_TASK` | `retrieval` |
| `RADAR_EMBEDDING_PROMPT_NAME` | `document` |
| `RADAR_EMBEDDING_TRUST_REMOTE_CODE` | `true` |
| `RADAR_EMBEDDING_BATCH_SIZE` | `64` |
| `RADAR_LLM_ENABLED` | `true` |
| `RADAR_LLM_REQUIRED` | `true` |
| `RADAR_DEBUG` | `false` |

### 项目雷达参数

这些参数在 CiteMap 雷达页设置，不是 GitHub Variables：

| 参数 | 说明 | 建议 |
|---|---|---|
| `arXiv categories` | 抓取范围，如 `cs.AI, cs.CV` | 默认 `cs.AI`；可填写多个 |
| `关注关键词` | 标题/摘要命中后保留 | 可留空 |
| `排除关键词` | 标题/摘要命中后排除 | 可留空 |
| `Top K` | 每次保留的推荐数量 | `10` |
| `抓取上限` | 每次最多读取候选数量 | `100` |
| `计算模式` | 云端、混合、本地 | `云端计算` |
| `包含 cross-list` | 是否包含交叉分类论文 | 按需开启 |
| `没有推荐时也发送邮件` | 空结果是否发信 | 按需开启 |

当前雷达排序固定使用历史 `zotero-arxiv-daily` 算法。项目设置中的 `最低分数`、anchor 论文不参与排序。

categories 必须使用 arXiv 分类格式，例如 `cs.AI`、`cs.CV`、`stat.ML`。写成 `cd.AI`、缺少点号、使用不存在的分类时，保存或扫描会提示具体错误；留空自动使用 `cs.AI`。

详细说明见 [`docs/radar-github-action-setup.md`](docs/radar-github-action-setup.md)。
