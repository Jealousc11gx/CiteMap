# GitHub Actions 论文雷达部署

论文抓取、相似度排序、AI 摘要、邮件发送由 GitHub Actions 执行。Cloudflare Worker + D1 保存项目画像、推荐结果、邮件状态。本地 CiteMap 只同步云端数据、发布项目画像。

Windows、macOS、Linux 使用相同云端配置。本机不需要安装 Wrangler，不需要复制 Worker JS 或 D1 SQL。

> 说明：当前 workflow 的自动触发分支是 `main`。如果你从其他分支开发，先合并到自己 Fork 的 `main`，再运行部署；只在功能分支上 push 不会触发生产部署。

## 0. 开启 Actions 权限

Fork 仓库后，打开 `Settings → Actions → General`：

- `Actions permissions` 选择允许使用 Actions；
- `Workflow permissions` 选择 `Read repository contents permission`；
- 若仓库使用 Environment，确认 `radar-production` 已创建，或在 workflow 设置中批准首次部署。

首次部署建议按以下顺序执行：创建 D1 → 配置 Worker Secrets → 手动运行 `Deploy Radar Worker` → 写入 `RADAR_REMOTE_URL` → 手动运行 `CiteMap Radar Test` → 手动运行正式 `CiteMap Radar`。

## 1. Fork 仓库

Fork `Jealousc11gx/CiteMap`。后续 Secrets、Variables、Actions 均在自己的 Fork 中配置。

不要把真实 Token、API Key、邮箱授权码提交到仓库。

## 2. 创建 D1

在 Cloudflare Dashboard 创建一个名为 `citemap-radar` 的 D1 database，记录 Database ID。

D1 只需创建一次。无需克隆 Cloudflare 模板。无需手动执行 `schema.sql`。`Deploy Radar Worker` 会自动应用仓库中的 migrations。

## 3. 配置 GitHub Secrets

打开自己的 Fork：`Settings → Secrets and variables → Actions → Secrets`。

### Worker 部署必需

| Name | 内容 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token，需 Workers Scripts Edit、D1 Edit 权限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `CLOUDFLARE_D1_DATABASE_ID` | 第 2 步创建的 D1 Database ID |
| `RADAR_REMOTE_TOKEN` | 自行生成的长随机 Token；同时作为 Worker 的 `RADAR_TOKEN` |

### 每日雷达必需

| Name | 内容 |
|---|---|
| `RADAR_REMOTE_URL` | 部署后得到的 Worker URL |
| `RADAR_REMOTE_TOKEN` | 与上表相同 |
| `RADAR_EMAIL_SENDER` | 发件邮箱 |
| `RADAR_EMAIL_RECEIVER` | 收件邮箱 |
| `RADAR_EMAIL_PASSWORD` | SMTP 授权码或 App Password，不是登录密码 |
| `LLM_API_KEY` | 生成中文标题、TLDR、AI 摘要 |

使用 API embedding provider 时，再添加 `RADAR_EMBEDDING_API_KEY`。默认本地 embedding 模型不需要该 Secret。

## 4. 配置 GitHub Variables

打开：`Settings → Secrets and variables → Actions → Variables`。

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

Embedding 相关 Variables 已有 workflow 默认值。SMTP Host、LLM Base URL、LLM Model 建议显式填写。

## 5. 部署 Worker

打开：`Actions → Deploy Radar Worker → Run workflow`。

该 workflow 自动完成：

1. 生成仅用于 CI 的 Wrangler 配置。
2. 应用 D1 migrations。
3. 部署最新 Worker。
4. 写入 Worker Secret `RADAR_TOKEN`。
5. 请求 `/health` 验证部署。

从部署日志记录 URL，例如：

```text
https://citemap-radar.<Cloudflare 子域>.workers.dev
```

将 URL 添加为 GitHub Secret `RADAR_REMOTE_URL`。不需要为 Worker 或 D1 配置自定义域名。

以后修改 `radar-worker/**` 并 push 到 `main`，workflow 会自动迁移 D1、重新部署 Worker。本地无需运行 Cloudflare 命令。

## 6. 连接本地 CiteMap

启动 CiteMap，打开“雷达”。本地前端不再提供 Cloudflare、模型、SMTP 配置向导。

首次连接只填写：

- `Worker URL`：`RADAR_REMOTE_URL`
- `RADAR_TOKEN`：`RADAR_REMOTE_TOKEN`

点击“连接并发布画像”。连接成功后，URL、Token 保存在当前浏览器 localStorage，不写入 SQLite，不上传到 GitHub。进入雷达页时，同一项目、同一 Worker 在当前浏览器会话内最多每 5 分钟自动同步一次。

每个启用雷达的项目至少配置：

- arXiv categories
- `top_k`
- `min_score`
- 至少一篇项目 reference paper

数据流：

```text
GitHub Actions → arXiv / embedding / LLM → Worker + D1
CiteMap → 发布项目画像 → Worker + D1
CiteMap ← 推荐、AI 字段、已读/收藏/忽略状态 ← Worker + D1
```

## 7. 验证完整流程

首次运行使用：`Actions → CiteMap Radar Test → Run workflow`。

测试 workflow 会使用历史日期，最多获取 5 篇候选、发送 3 篇，适合验证非 arXiv 发布日场景。检查：

1. Action 成功读取 profile。
2. embedding 完成相似度排序。
3. LLM 返回中文 TLDR、AI 摘要。
4. SMTP 发送邮件。
5. Worker D1 保存推荐与 `emailed_at`。
6. CiteMap 雷达页同步到推荐；邮件点击产生的已读状态可回到本地。

验证完成后，可手动运行 `CiteMap Radar`。正式 workflow 每日 UTC `22:00` 自动执行，即北京时间次日 `06:00`。

## 8. CI/CD 边界

| Workflow | 触发方式 | 职责 |
|---|---|---|
| `ci.yml` | push、PR | 后端 pytest、前端 Vitest/build、Worker 语法检查 |
| `deploy-radar-worker.yml` | Worker 相关文件 push、手动 | D1 migration、Worker deployment、health check |
| `radar.yml` | schedule、手动 | 每日抓取、排序、AI 摘要、邮件 |
| `radar-test.yml` | 手动 | 使用少量历史论文验证完整链路 |

Fork 用户需要自行提供 Cloudflare、LLM、SMTP 凭据。GitHub Actions 不读取本机 `backend/.env` 或 `data/papers.db`。
