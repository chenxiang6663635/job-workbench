# 研究计划：不发布积累期的「修改 / 优化 + 新增功能」候选审计

- 日期：2026-10-07 ｜ 状态：执行中 ｜ 交付物：`research_report_accumulate-backlog.md`
- 背景：DSH 二阶段 P2-1..P2-5 已全部合并；用户 10-07 拍板**暂不发布**（发布节点维持 `26.11.0`，十一月发车），要求在积累窗口内摸清「还有哪些要修 / 要优化」与「还有哪些功能该补」。

## 检索与取证范围

- 内部（主体）：`ROADMAP.md`、`CHANGELOG.md`、`docs/`（contributing / release-checklist / mcp-integration / support-and-compatibility / decisions / specs）、`tools/`（含 `size_allowlist.txt` 与各扫描器豁免表）、`packages/`、`mcp/`、`web/`、`scripts/`、`tests/`、`.codebuddy/memory/`。
- 已取的外部登记（不再重复检索）：GitHub 开放 issue #274（笔记返回栈）/ #259（数据根实施跟踪）/ #204（Electron `main.js` 967 行拆分）；远端 8 个已合并分支未删。
- 外部（轻量）：同类求职工具近 12 个月的功能面（web + 中文信息源，含微信公众号检索）。

## 子任务与分工（并行、互不重叠）

| # | 执行者 | 范围 | 预期产出 |
|---|---|---|---|
| A | code-explorer | 已登记待办盘点：ROADMAP / CHANGELOG / 治理文档 / 豁免表 / 代码 TODO 标记 / decisions | 「修·优化类 vs 新增类」双栏事实清单（带 file:line） |
| B | code-explorer | 工程与后端：`tools/`、`packages/jobws-core`、`mcp/jobws_mcp`、`web/backend`、`scripts/`、`tests/` | 测试盲区、性能、规模水位、重复实现、错误处理、安全边界清单 |
| C | code-explorer | 前端 / UX / 文档 / 站点：`web/frontend`、`web/electron`、`site/`、README、`docs/`、`template/` | 未完成交互、i18n、a11y、响应式、性能、文档缺口清单 |
| D | research_subagent | 外部对照：同类工具 / ATS 生态 / 求职者真实痛点 | 新增功能候选 + 「不适合本项目边界」的反面清单（带 URL 与日期） |

不派发的：已开 issue 的三项只做登记归档、不复述分析；发布链五步不属本审计（需用户在场，另行启动）。

## 各步产出与判定

1. 四份子结论 → 去重合并 → 分「修 / 优化」与「新增功能」两栏，并标注影响面、修复成本、与 26.11.0 发布节点的关系；
2. 事实与推断严格分离，缺证据的条目标注「待核实」；
3. 最终报告结构：执行摘要 → 背景 → 修 / 优化清单 → 新增功能清单 → 分析与批次切分建议 → 结论 → 局限性 → References（仅列带 URL 的可点击来源）。

## 时间与并行

- 四个子任务全部并行；目标 ≤ 1 轮侦察 + 报告写作。
