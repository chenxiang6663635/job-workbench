# CODEBUDDY.md — CodeBuddy 项目入口

@AGENTS.md

> **精简适配层。** 共享规则（诚实红线、三层分离、工程约定）由 `AGENTS.md` 提供（canonical）；
> 本文件只保留进入仓库后必须立即遵守的最小上下文。与 `AGENTS.md` 冲突时，以 `AGENTS.md` 为准。
>
> - 共享规则与工作流知识 -> `AGENTS.md` + `skills/`（单一源在 `skills/`）
> - 开发流程 -> `CONTRIBUTING.md`；隐私条款见其「隐私约定」节

## 立即约束

- **始终用简体中文回答**。
- **诚实红线**：简历每个动词都要经得起 5–10 分钟追问；知识缺口用诚实的桥梁回答，永不编造经历。
- **三层分离**：`tools/` 领域无关（不得出现领域术语或个人信息）；领域知识进 `template/profiles/`；个人事实进 `personal/`（已 gitignore，**其内容禁止提交或外泄**）。
- **Web 层铁律**：后端直接复用 `tools/` 函数并显式传 `workspace`；写操作持锁；路径过 `safe_join`；不加缓存。
- **验证链**：改 `tools/` 或 `web/backend/` 后跑 `python -m pytest tests/ -q`；改前端后跑 `npm run build`（Windows 用 `npm.cmd`）。
- **不自动 commit**：生成提交信息，待确认后再提交。
