# 研究计划：相似项目的开发流程调研

- 日期：2026-09-01
- 触发：用户要求分析「后续开发流程」，或去 GitHub 查找相似项目的开发流程。
- 澄清：**开发流程 ≠ 工程配置**。
  - 已调研（`report_dev_setup_benchmark.md`）= 工程配置层：打包、数据目录、CI/锁文件/日志。
  - 本轮调研 = **开发流程层**：迭代节奏、版本规划、分支策略、issue/PR 管理、路线图、发布流程、自用与产品化的平衡。
- 查询类型：**Breadth-first**（三个独立子问题，边界清晰不重叠）

## 背景：本项目当前状态（调研对照基线）
- 形态：本地优先求职工作台。React+TS 前端 + Python 3.8 FastAPI 后端 + Electron 壳，数据 Markdown+CSV。
- 团队：**单人维护**（用户自己），自用优先，但要能分发给他人。
- 已完成：差异化点（评分下钻/硬门槛前置）、workspace + BYOK、追踪硬化、Electron 打包（PyInstaller exe）。
- 仓库：仅本地 git，不推送远程（当前），无 CI、无测试、无 issue 流程、无版本规划。
- 用户身份：2027 届硕士（暖通制冷方向）求职者，本项目既是自用工具也是产品化尝试。

## 检索关键词与时间范围
- 英文：`open source solo maintainer development workflow`、`GitHub flow vs gitflow solo developer`、
  `open source project milestone release process`、`maintainer issue triage workflow`、
  `dogfooding open source project development`、`electron app release process github`
- 中文（公众号，带时间）：`独立开发者 开源项目 开发流程 迭代`（2025-01 至 2026-09）
- 时间：以 2024-2026 活跃项目为主。

## 子任务与 subagent 分工（3 个，并行）
| # | 子任务 | 范围 | 预期产出 |
|---|---|---|---|
| A | 迭代节奏与版本规划 | 单人/小团队维护的开源桌面应用（Joplin、Logseq、Cherry Studio、Anything LLM 等）怎么排迭代？多久发一版？怎么决定做什么 | 每个案例：迭代周期、版本粒度、优先级决策方式；3 条对单人项目的可借鉴点 |
| B | 分支策略与发布流程 | GitHub Flow / GitFlow / Trunk-based 在单人项目的适用性；tag/semver/CHANGELOG/hotfix 怎么做；release 流程 | 分支与发布策略对比 + 对单人项目的推荐（是否需要分支、如何打版本） |
| C | 需求管理与自用平衡 | 怎么管理需求与 issue（GitHub Projects/Milestone/issue 模板）；"自用优先"项目如何平衡自己需求与他人需求；路线图怎么公开 | 需求管理做法 + **自用与产品化平衡的具体建议**（本项目核心矛盾） |

## 并行与必要性
- A/B/C 互相独立（节奏/分支/需求管理），可完全并行。
- 主会话用 wechat-article-search 补中文视角（带时间参数），与英文源交叉印证。
- 不派发：产品功能调研（已做过）、工程配置调研（已做过）。

## 预期产出
`research_report_dev_workflow.md`：三张对比表 + 对本项目「后续开发流程」的具体建议
（迭代节奏、分支策略、版本管理、需求管理、自用与产品化平衡），并给出可直接执行的流程清单。
