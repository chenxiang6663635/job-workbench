# 文档索引

按阅读顺序排列。不确定先看哪份时，从第一份开始。

## 先读这两份

| 文档 | 说明 |
|---|---|
| [`usage-guide.md`](usage-guide.md) | **使用手册（英文主版）**：环境准备、一键启动、七个页面详解、AI 工作流、CLI 速查、备份、常见问题 |
| [`usage-guide.zh-CN.md`](usage-guide.zh-CN.md) | 上述手册的**简体中文同步版**（内容与主版一致，互链在各自开头） |
| [`../README.md`](../README.md) | 项目主入口：定位、三层架构、快速开始、目录说明 |

## 设计文档

| 文档 | 状态 | 说明 |
|---|---|---|
| [`specs/2026-08-30-general-workbench-design.md`](specs/2026-08-30-general-workbench-design.md) | **现行** | v2.0 通用工作台架构：三层分离、领域插件契约、脚本参数化、迁移映射 |
| [`specs/2026-08-30-web-prototype-design.md`](specs/2026-08-30-web-prototype-design.md) | **现行** | Web 界面层：架构、API 契约、数据契约、并发与安全、验证记录 |
| [`specs/2026-08-31-job-workbench-productization.md`](specs/2026-08-31-job-workbench-productization.md) | **现行** | 产品化三期路线（差异化点/架构/桌面壳/扩展）+ 一期与 P0+P1 完成记录 |
| [`specs/2026-09-02-tracking-enhancement.md`](specs/2026-09-02-tracking-enhancement.md) | **现行** | 投递追踪增强：面试/联系人/Offer 独立 CSV、反编造护栏、时间线 |
| [`specs/2026-09-02-resume-data-driven.md`](specs/2026-09-02-resume-data-driven.md) | **现行** | 简历数据驱动「标准版式」：JSON + 内置模板渲染 PDF + ATS 校验 |
| [`specs/2026-09-02-resume-probe.md`](specs/2026-09-02-resume-probe.md) | 已完成 | 简历 PDF 文本抽取探针（ATS 阈值定的依据） |
| [`specs/2026-09-03-p0-p3-roadmap.md`](specs/2026-09-03-p0-p3-roadmap.md) | **现行** | P0–P3 四批：工程底座、投递后闭环、增强、长期资产（含验收记录） |
| [`specs/2026-09-05-batch1-3-roadmap.md`](specs/2026-09-05-batch1-3-roadmap.md) | **现行** | 第一~三批：导入导出闭环、题库与健康度、失败聚类与 JD 抓取（含验收记录） |
| [`specs/2026-09-07-open-source-release.md`](specs/2026-09-07-open-source-release.md) | **现行** | 开源发布：隐私清洗、MIT、治理入口、CI 与发布流程 |
| [`specs/2026-08-30-autumn-recruit-workbench-design.md`](specs/2026-08-30-autumn-recruit-workbench-design.md) | ⚠️ **已废弃** | v1.0 个人工具设计。目录结构已失效，**勿据此开发**。保留作评分框架的设计依据追溯 |

## 调研报告

| 文件 | 说明 |
|---|---|
| [`research/report_job_search_products.md`](research/report_job_search_products.md) | GitHub 求职类开源产品调研（**产品功能层**）：竞品全景、LLM 接入共识、差异化机会（评分可追溯/硬门槛前置）、产品化借鉴清单 |
| [`research/plan_job_search_products.md`](research/plan_job_search_products.md) | 上述调研的研究计划（检索词、subagent 分工、并行策略） |
| [`research/report_dev_setup_benchmark.md`](research/report_dev_setup_benchmark.md) | 本地优先桌面应用开发设置基准（**工程配置层**）：打包分发（PyInstaller onedir/onefile）、用户数据目录策略、工程设置（CI/锁文件/日志）亮点与空白 |
| [`research/plan_dev_setup_benchmark.md`](research/plan_dev_setup_benchmark.md) | 上述调研的研究计划（工程配置层三路分工） |
| [`research/report_dev_workflow.md`](research/report_dev_workflow.md) | 相似项目的**开发流程**（迭代节奏、分支与发布、需求管理、**自用与产品化平衡**）及本项目可执行流程建议 |
| [`research/plan_dev_workflow.md`](research/plan_dev_workflow.md) | 上述调研的研究计划（开发流程层三路分工） |
| [`research/report_next_features.md`](research/report_next_features.md) | 下一步**功能级差距分析**：四域检索（其中一路中断）后的功能清单与借鉴优先级（与上表的产品化定位调研分工不同——那份答「做成什么」，这份答「还缺什么」）。注意：第四路检索中断，但结论不依赖该路，缺失部分在文首列明 |
| [`research/plan_next_features.md`](research/plan_next_features.md) | 上述调研的研究计划（四个互不重叠功能域的检索分工） |
| [`research/report_agent-integration.md`](research/report_agent-integration.md) | **定位与宿主集成**调研整合（决策级）：agent 插件/工具这条路的成本与反面证据、dsh 插件解剖、agent-first 分层、Python 工具的 agent 暴露方式。**这是「AI 助手是一等宿主、界面是可选查看器」这一方向判断的依据**。性质是结论整合（子代理报告被调度器截断），未能确认的部分集中列在文末「未确认清单」，不要当完整调研用 |

## 开发流程

| 文件 | 说明 |
|---|---|
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | **开发流程规范**：新需求四道门、分支策略、提交与版本规则、发布流程、可持续性约定、隐私约定与 CI 验证链 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 变更记录（Keep a Changelog 格式）；版本号唯一来源为 `web/electron/package.json` |
| [`../.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) | Issue 模板：bug 报告专用；功能请求走 CONTRIBUTING 四道门 |

## 约定文件

| 文件 | 说明 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | AI 工作约定：三层架构铁律、通用/个人边界、工程约束、目录约定 |
| [`../template/AGENTS.example.md`](../template/AGENTS.example.md) | 候选人档案模板，含逐项填写说明与真实样例 |
| [`../template/workspace/README.md`](../template/workspace/README.md) | 六个模块的用途、填写顺序、关键纪律 |

## 领域插件

| 文件 | 说明 |
|---|---|
| [`../template/profiles/hvac-cooling/profile.md`](../template/profiles/hvac-cooling/profile.md) | 暖通制冷与数据中心冷却插件 |
| [`../template/profiles/software-backend/profile.md`](../template/profiles/software-backend/profile.md) | 软件后端与数据工程插件（用于验证跨领域可扩展性） |

新增领域只需新增一个插件目录，无需改代码，见通用设计文档第 5 节。

## 技能文件（工作流定义）

`../skills/` 下五个：`jwb-recruit-coach`（评分标准与红线）、`jwb-jd`、`jwb-apply`、`jwb-track`、`jwb-resume`。

这些既是 AI 可加载的技能，也是各工作流的规格说明——读它们等于读流程定义。

## 已归档代码

| 文件 | 说明 |
|---|---|
| [`deprecated/fix_links.py`](deprecated/fix_links.py) | 个人重组时用的一次性断链修复工具，已停用。保留作路径替换逻辑的参考 |
