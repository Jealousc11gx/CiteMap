# CiteMap 论文雷达部署

CiteMap 的论文雷达由 GitHub Actions 执行抓取、相似度排序、中文摘要、邮件发送。Cloudflare Worker + D1 保存项目画像、推荐结果、阅读状态。

## 部署流程

1. Fork 本仓库，确保 Actions 已启用。
2. 在 Cloudflare 创建 D1 database，名称建议为 `citemap-radar`，记录 `Database ID`、`Account ID`。
3. 在 GitHub 打开 `Settings → Secrets and variables → Actions`，添加下方 Secrets、Variables。
4. 打开 `Actions → Deploy Radar Worker → Run workflow`。
5. 从部署日志获取 Worker URL，写入 `RADAR_REMOTE_URL` Secret。
6. 打开 `Actions → CiteMap Radar Test → Run workflow` 验证。
7. `CiteMap Radar` 默认每天 UTC `22:00` 自动运行，需要立即执行时点击 `Run workflow`。

## GitHub Secrets

### Worker 部署

| Name | 内容 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token，需 Workers Scripts Edit、D1 Edit 权限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `CLOUDFLARE_D1_DATABASE_ID` | `citemap-radar` 的 D1 Database ID |
| `RADAR_REMOTE_TOKEN` | 自行生成的长随机 Token，同时作为 Worker 的 `RADAR_TOKEN` |

### 雷达运行

| Name | 内容 |
|---|---|
| `RADAR_REMOTE_URL` | 部署后的 Worker URL |
| `RADAR_REMOTE_TOKEN` | 与 Worker 部署使用的 Token 相同 |
| `RADAR_EMAIL_SENDER` | 发件邮箱 |
| `RADAR_EMAIL_RECEIVER` | 收件邮箱 |
| `RADAR_EMAIL_PASSWORD` | SMTP 授权码或 App Password，不是登录密码 |
| `LLM_API_KEY` | OpenAI 兼容 API Key |
| `RADAR_EMBEDDING_API_KEY` | 使用 API embedding provider 时填写 |

## GitHub Variables

| Name | 推荐值 |
|---|---|
| `RADAR_SMTP_HOST` | `smtp.qq.com`、`smtp.gmail.com` 等 |
| `RADAR_SMTP_PORT` | `465` |
| `RADAR_EMBEDDING_PROVIDER` | `local` |
| `RADAR_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v5-text-nano-retrieval` |
| `RADAR_EMBEDDING_TASK` | `retrieval` |
| `RADAR_EMBEDDING_PROMPT_NAME` | `document` |
| `RADAR_EMBEDDING_TRUST_REMOTE_CODE` | `true` |
| `RADAR_EMBEDDING_BATCH_SIZE` | `64` |
| `RADAR_LLM_ENABLED` | `true` |
| `RADAR_LLM_REQUIRED` | `true` |
| `LLM_BASE_URL` | OpenAI-compatible API Base URL |
| `LLM_MODEL` | API 实际支持的模型名 |
| `RADAR_DEBUG` | `false` |

详细说明见 [`docs/radar-github-action-setup.md`](docs/radar-github-action-setup.md)。
