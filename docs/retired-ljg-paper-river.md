# `ljg-paper-river` 恢复记录

来源仓库：`lijigang/ljg-skills`
加入 commit：`de75385ae4226e6589a56ae1ef4ebe5d508d7c4a`，2026-04-01
删除 commit：`fb6279ed25f87442330f3b503d15e5b2457d2e26`，2026-07-10
历史文件定位：`git show de75385:skills/ljg-paper-river/SKILL.md`

## 项目文件

- `skills/ljg-paper-river/SKILL.md`
- `skills/ljg-paper-river/references/template.org`

## 适配范围

- 保留倒读法、最多五层递归、问题演化叙事、两张 ASCII 图、Org/Denote 输出规范。
- 迁移旧 frontmatter 字段到 Codex 支持的 `metadata`。
- 统一使用 OpenAI-compatible LLM，复用 CiteMap 的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- 论文检索、PDF 读取、引用验证使用宿主环境提供的工具，不绑定具体 CLI。

恢复文件是研究与写作协议，不是可直接 import 的业务模块。完整正文与模板以项目内 skill 文件为准。
