# GitHub Copilot 仓库指引

共享仓库规则（诚实红线、三层分离、工程约定）的**唯一事实源是根目录 `AGENTS.md`**，请先阅读并遵守；本文只做摘要，与 `AGENTS.md` 冲突时以其为准。开发流程见 `CONTRIBUTING.md`（含隐私约定）。

## 摘要

- 用简体中文回答与写注释。
- **诚实红线**：简历每个动词都要经得起 5–10 分钟追问；知识缺口用诚实的桥梁回答，永不编造经历。
- **三层分离**：`tools/` 领域无关（不得出现领域术语或个人信息）；领域知识进 `template/profiles/`；个人事实进 `personal/`（已 gitignore，**其内容禁止提交或外泄**）。
- **Web 层铁律**：后端复用 `tools/` 函数并显式传 `workspace`；写操作持锁；路径过 `safe_join`；不加缓存。
- **验证链**：`python -m pytest tests/ -q` + 前端 `npm run build`（Windows 用 `npm.cmd`）。
- **不自动 commit**：生成提交信息，待确认后再提交。
