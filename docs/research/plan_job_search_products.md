# 研究计划：GitHub 求职类开源产品调研（为工作台产品化提供借鉴）

- 日期：2026-08-31
- 查询类型：**Breadth-first**（可拆为彼此独立的子问题，边界清晰不重叠）
- 原始问题：用户想把本地求职工作台（JD 解析→评分→简历→追踪）变为面向普通用户的求职产品（Tauri 桌面应用为候选形态），需要回答：① 桌面产品化后 LLM API 怎么解决（BYOK/托管/本地模型）；② GitHub 上有哪些同类产品，各自怎么做，我们可借鉴什么。

## 检索关键词与时间范围

- 英文：`resume builder open source github`、`resume matcher job description LLM`、`job application tracker open source`、`auto apply jobs AI agent github`、`BYOK bring your own key desktop app`
- 中文（公众号，带时间参数）：`开源 求职工具 简历 AI`（2025-01 至 2026-08）
- 时间范围：以 2024-2026 活跃项目为主，历史项目（如 Tailor 2023）仅作模式参考

## 子任务与 subagent 分工（3 个，并行）

| # | 子任务 | 范围 | 预期产出 |
|---|---|---|---|
| A | 简历构建/优化类 | OpenResume、Reactive Resume、JSON Resume、Resume Matcher 等，GitHub topic:resume-builder 头部项目 | 每产品：star/活跃度/功能/技术栈/LLM 接入方式/商业模式；3 条产品化启示 |
| B | JD 解析与匹配类 | Tailor、Resume-Matcher 的匹配链路、job-matcher 类项目——与工作台核心"JD→评分"最重叠 | JD 解析靠 LLM 还是规则、评分输出形态、用户 LLM 提供方式；与四维加权评分框架对比 |
| C | 投递追踪与自动化类 | AIHawk 现状、easy-apply bot 系、开源 tracker；Teal/Simplify 闭源标杆的免费功能边界 | 追踪数据模型/阶段枚举借鉴、自动化账号风险、免费↔付费功能切分 |

补充：主会话用 wechat-article-search 检索公众号中文视角（2025-2026），与 subagent 英文源交叉印证。

## 并行与必要性说明

- A/B/C 互相独立（简历工具 / JD 匹配 / 追踪自动化），可完全并行，无依赖。
- 主会话公众号检索与 subagent 并行。
- 不派发：产品定价调研（无公开数据，纯猜）、竞品 UI 设计细节（截图无法验证）。

## 预期最终产出

`research_report_job_search_products.md`：产品全景表 + 逐类分析 + 对工作台产品化的具体借鉴清单（架构/评分呈现/商业模式/风险）。
