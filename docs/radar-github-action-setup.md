# GitHub Actions 论文雷达配置

## 1. 前置条件

Action 不读取本机 `data/papers.db`。电脑关闭时，Action 依赖两个远端配置：

1. Cloudflare Worker + D1 保存 profile、推荐、邮件状态。
2. GitHub Actions Secrets/Variables 保存 Worker、SMTP、模型配置。

首次打开 CiteMap 的 `/radar` 页面时，会自动跳转到 `/settings/radar` 配置向导。向导按“模型 → 邮件 → Worker/D1 → GitHub Action → 完成”分步保存草稿，配置完成标记保存在当前浏览器。它不会自动写入 GitHub Secrets。

当前仓库为 `Jealousc11gx/CiteMap`。

## GitHub Actions CI/CD

仓库包含三类自动化：

- `ci.yml`：push、PR 时运行后端 pytest、前端 Vitest/build、Worker 语法检查。
- `deploy-radar-worker.yml`：`radar-worker/**` 变化时应用 D1 migrations、部署 Worker。
- `radar.yml`、`radar-test.yml`：执行论文雷达计算、AI 摘要与邮件发送。

Worker 自动部署需要在 GitHub Actions Secrets 配置：

| Name | 内容 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token，需要 Workers Scripts Edit、D1 Edit 权限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `CLOUDFLARE_D1_DATABASE_ID` | 已创建的 CiteMap D1 database ID |

`deploy-radar-worker.yml` 会临时生成 `wrangler.ci.toml`。D1 ID 不写入仓库。已有 Worker Secret `RADAR_TOKEN` 会在部署时保留。

旧 D1 缺少 AI 字段时，部署 workflow 会检测 `items` 表并自动执行 `0003_add_ai_fields.sql`。以后只需提交新的受管 migration，不需要在本地运行 Wrangler。

## 2. 部署 Worker

Cloudflare 配置属于远端实例，与 Windows、macOS、Linux 无关。推荐直接使用 Cloudflare Dashboard 完成首次部署，不需要在本地安装 Wrangler 或执行终端命令：

1. 创建 Worker，粘贴 `radar-worker/src/index.js`。
2. 创建 D1 数据库，执行 `radar-worker/schema.sql`。
3. 在 Worker Settings → Variables 添加 Secret：`RADAR_TOKEN`。
4. 发布 Worker，记录 Worker URL。

不需要为 Worker + D1 单独配置域名。Cloudflare 会提供 `https://<worker-name>.<subdomain>.workers.dev`，CiteMap 可直接使用。自定义域名仅在需要品牌入口或已有 Cloudflare Zone 时配置，D1 本身没有域名。

Cloudflare Dashboard 的 D1「克隆存储库」模板不是必需项。CiteMap 使用仓库内的 `radar-worker/schema.sql`，向导提供复制按钮，可直接粘贴到 Worker 编辑器与 D1 Console。

也可以由维护者使用 Wrangler 部署。`database_id`、Worker URL、`RADAR_TOKEN` 属于具体 Cloudflare 实例，不要写入公共示例配置或提交到仓库。

如果 D1 已经按旧 schema 部署，使用 Cloudflare D1 控制台执行一次迁移：

```bash
npx wrangler d1 execute citemap-radar --remote --file=migrations/0002_add_tldr.sql
```

已经创建过 D1 的用户还需要在 D1 Console 执行 `radar-worker/migrations/0003_add_ai_fields.sql`，用于保存云端生成的中文标题、TLDR、AI 摘要、核心贡献、方法、结果、局限性。完成迁移后，重新复制并部署最新的 `radar-worker/src/index.js`。

云端优先模式的数据流：

```text
GitHub Action → arXiv / embedding / LLM → Worker + D1
CiteMap 本地 ← 同步推荐、AI 字段、已读/收藏/忽略状态
```

本地默认不重复计算。雷达设置中的 `local` 仅用于开发或云端故障时手动备用；`hybrid` 会先同步云端，同步失败后再进行本地计算。

部署完成后得到：

```text
https://citemap-radar.<你的 Cloudflare 子域>.workers.dev
```

## 3. GitHub Secrets

仓库页面：`Settings → Secrets and variables → Actions → New repository secret`

创建以下 Secrets：

| Name | 内容 |
|---|---|
| `RADAR_REMOTE_URL` | Worker URL，例如 `https://citemap-radar.xxx.workers.dev` |
| `RADAR_REMOTE_TOKEN` | 与 Worker 的 `RADAR_TOKEN` 完全相同 |
| `RADAR_EMAIL_SENDER` | 发件邮箱 |
| `RADAR_EMAIL_RECEIVER` | 收件邮箱 |
| `RADAR_EMAIL_PASSWORD` | SMTP 授权码或 App Password，不是登录密码 |
| `RADAR_EMBEDDING_API_KEY` | 仅 API embedding provider 需要，本地模型留空 |
| `LLM_API_KEY` | Action 用于生成论文 TLDR |

## 4. GitHub Variables

同一页面切换到 `Variables`，创建：

| Name | 推荐值 |
|---|---|
| `RADAR_SMTP_HOST` | 例如 `smtp.qq.com`、`smtp.gmail.com` |
| `RADAR_SMTP_PORT` | `465` |
| `RADAR_EMBEDDING_PROVIDER` | `local` |
| `RADAR_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v5-text-nano-retrieval` |
| `RADAR_EMBEDDING_TASK` | `retrieval` |
| `RADAR_EMBEDDING_PROMPT_NAME` | `document` |
| `RADAR_EMBEDDING_TRUST_REMOTE_CODE` | `true` |
| `RADAR_EMBEDDING_BATCH_SIZE` | `64` |
| `RADAR_DEBUG` | `false` |
| `RADAR_LLM_ENABLED` | `true` |
| `RADAR_LLM_REQUIRED` | `false` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` |
| `LLM_MODEL` | `gpt-4o-mini` |
| `RADAR_SCHEDULE_UTC` | 记录当前计划时间；实际 cron 由 workflow 文件控制 |

以上模型变量均有 workflow 默认值，不创建也可以运行。建议显式创建，便于以后改模型。

Action 现在会为每篇邮件论文调用 LLM 生成 `tldr`。`RADAR_LLM_REQUIRED=false` 时，LLM 不可用会降级为原始摘要，仍继续发邮件。测试 workflow 会将它设为 `true`，用于验证 LLM 配置。

完整等价配置快照由云端配置向导生成，内容对应 daily arxiv 的 `email`、`embedding/reranker`、`llm`、`executor`、`remote` 分组。CiteMap 当前不需要 `ZOTERO_ID`、`ZOTERO_KEY`，因为 reference papers 来自本地项目并发布到 Worker。

## 5. 发布项目 profile

Action 的 profile 来源不是本地 SQLite。CiteMap 应用打开、网络可用时，在雷达同步操作中发布 profile：

```text
本地应用 → 雷达 → 配置项目 → 保存 → 同步/发布 profile
```

每个启用雷达的普通项目应至少配置：

- arXiv categories
- `top_k`
- `min_score`
- 至少一篇项目 reference paper
- 可选 anchor paper

Worker 中可用以下接口确认 profile 已存在：

```bash
curl -H "Authorization: Bearer <RADAR_TOKEN>" \
  "https://citemap-radar.<域名>.workers.dev/profiles"
```

## 6. 手动运行 Action

仓库页面：`Actions → CiteMap Radar → Run workflow`

第一次建议手动运行。确认顺序：

1. `profiles` 能返回启用项目。
2. arXiv 能获取候选。
3. Hugging Face 模型下载完成。
4. SMTP 发送成功。
5. Worker 的 item 出现 `emailed_at`。

模型首次下载较慢。workflow 已缓存：

```text
~/.cache/huggingface
~/.cache/torch
~/.cache/sentence_transformers
```

后续运行会复用 cache。Action 重跑不会重复创建 item，也不会重复发送已标记 `emailed_at` 的论文。

另有独立测试 workflow：

```text
Actions → CiteMap Radar Test → Run workflow
```

测试 workflow 固定最多获取 5 篇候选、最多发送 3 篇，开启 debug、LLM TLDR，发送真实测试邮件。

`include_cross_list`、`send_empty`、`fetch_limit`、`debug` 已进入项目 profile，项目配置页可直接调整。

## 7. 当前完整测试结果

### 自动化测试

```text
后端 pytest：193 passed
前端 Vitest：68 passed
前端 production build：通过
Worker node --check：通过
```

### 当前数据库论文测试

`data/papers.db` 当前：

- 22 篇论文
- 默认项目：21 篇论文
- `111` 项目：1 篇论文

已使用默认项目的 20 篇论文作为 reference，剩余 2 篇作为 candidate 做完整排序演练。测试只读 SQLite，不发送邮件，不写 Worker。

在当前机器上，lexical fallback 的耗时为：

```text
20 篇 reference embedding：约 0.0025 秒
完整排序：约 0.0031 秒
```

daily arxiv SentenceTransformer 的首次真实测试未完成。原因是 Hugging Face 模型文件下载时网络握手超时，错误发生在模型下载阶段，不是排序代码：

```text
URLError: <urlopen error EOF occurred in violation of protocol (_ssl.c:1129)>
```

模型已经开始下载并产生部分 cache。Action 环境通常网络更稳定，首次运行耗时主要取决于模型下载；模型 cache 命中后，20 篇论文的编码与排序会远低于首次下载时间。

## 8. 当前限制

- GitHub CLI 未安装，无法从本机自动写入 GitHub Secrets。
- 配置页当前生成清单，不直接管理 GitHub Secrets。
- Worker 必须先部署，Action 才能读取 profile、保存 item、记录邮件状态。
- `radar.yml` 当前 cron 为 UTC `22:00`，即北京时间次日 `06:00`。
