# 研究计划：本地优先桌面应用的开发设置基准调研

- 日期：2026-09-01
- 触发：用户在执行 PyInstaller 打包（a+b 路径 B）前，要求先借鉴 GitHub 相似项目的开发设置，找亮点与空白。
- 查询类型：**Breadth-first**（三个独立子问题，边界清晰不重叠）
- 与既有调研的区别：`docs/research/report_job_search_products.md` 调研的是**产品功能层**（简历/JD匹配/追踪/自动化）；
  本次调研的是**工程配置层**（打包分发、数据目录、依赖环境、CI/跨平台），是不同维度。

## 背景：本项目当前状态（调研要对照的基线）
- 形态：本地优先求职工作台。前端 React+TS+Vite，后端 Python 3.8 FastAPI（import tools/ 脚本），数据 Markdown+CSV。
- 桌面壳：Electron 主进程 spawn 后端（`python -m uvicorn`），前端 dist 由后端同源托管（消除 CORS）。
- 正在做：PyInstaller 打包后端为独立 exe（免用户装 Python），数据与 dist 放 exe 旁。
- 已完成：workspace 切换、BYOK Provider、追踪约束（终态/去重/原因码）、评分下钻、硬门槛前置。
- 硬约束：Python 3.8；tools 领域无关；脚本数 ≤6；仅本地 git 不推送。

## 检索关键词与时间范围
- 英文：`PyInstaller FastAPI Electron desktop app github`、`local-first app user data directory cross platform`、
  `self-hosted desktop app data folder best practice`、`Python backend Electron app packaging`、`GitHub Actions cross platform build desktop app`
- 中文（公众号，带时间）：`开源 桌面应用 打包 Electron Python 数据目录`（2025-01 至 2026-09）
- 时间：以 2024-2026 活跃项目为主。

## 子任务与 subagent 分工（3 个，并行）
| # | 子任务 | 范围 | 预期产出 |
|---|---|---|---|
| A | 打包与分发实践 | PyInstaller 打包 Python/FastAPI 后端、Electron 整合 Python 后端的开源案例（如 Cherry Studio、Cherry-Studio 类、Lobe Chat 桌面版、Anything LLM 桌面版、Open WebUI 桌面化等） | 每个案例：打包方式、体积、是否免环境、启动/退出流程、踩坑；3 条可借鉴点 |
| B | 用户数据目录与配置 | 本地优先应用把用户数据放哪（exe 旁 vs AppData / ~/.config / ~/Library）、跨平台路径策略、数据迁移与备份、多工作区/多配置 | 数据目录策略对比 + 对我们"数据放 exe 旁"决策的评估（是否合理） |
| C | 开发工程设置 | CI/CD（GitHub Actions 跨平台构建）、依赖锁定、版本号管理、测试策略、release 流程、自动更新 | 工程设置清单 + 我们缺什么（空白） |

## 并行与必要性
- A/B/C 互相独立（打包/数据目录/工程设置），可完全并行。
- 主会话用 wechat-article-search 补中文视角（带时间参数）。
- 不派发：产品功能调研（已做过）、定价/商业模式（无公开数据）。

## 预期产出
`research_report_dev_setup_benchmark.md`：三张对比表 + 亮点清单 + 空白清单 + 对 PyInstaller 打包决策的具体建议（是否调整"数据放 exe 旁"）。
