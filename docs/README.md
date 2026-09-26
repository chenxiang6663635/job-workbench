# 文档索引

按阅读顺序排列。不确定先看哪份时，从第一份开始。

## 先读这几份

| 文档 | 说明 |
|---|---|
| [`usage-guide.md`](usage-guide.md) | **使用手册（英文主版）**：环境准备、一键启动、八个页面详解、AI 工作流、CLI 速查、备份、常见问题 |
| [`usage-guide.zh-CN.md`](usage-guide.zh-CN.md) | 上述手册的**简体中文同步版**（内容与主版一致，互链在各自开头） |
| [`../README.md`](../README.md) | 项目主入口：定位、三层架构、快速开始、目录说明 |
| [`data-flow-matrix.md`](data-flow-matrix.md) | **数据流矩阵**：什么数据、什么时候、去哪里——隐私承诺的权威底稿（界面文案与它冲突时以它为准） |

## 设计文档

| 文档 | 状态 | 说明 |
|---|---|---|
| [`specs/2026-08-30-general-workbench-design.md`](specs/2026-08-30-general-workbench-design.md) | **现行** | v2.0 通用工作台架构：三层分离、领域插件契约、脚本参数化、迁移映射。**注意**：文中「tools/ 下共 6 个脚本」等清单是 2026-08 的当时记录——脚本已归并为 `tools/jobws.py` 唯一入口，现状见 `contributing.zh-CN.md` |
| [`specs/2026-08-30-web-prototype-design.md`](specs/2026-08-30-web-prototype-design.md) | 历史（部分章节已被取代） | Web 界面层：架构、API 契约、数据契约、并发与安全、验证记录。**注意**：依赖版本与 Python 基线等章节是 2026-08 的当时记录（3.8 时代），现状以 `contributing.zh-CN.md` 与 `web/backend/requirements.txt` 为准 |
| [`specs/2026-08-31-job-workbench-productization.md`](specs/2026-08-31-job-workbench-productization.md) | **现行** | 产品化三期路线（差异化点/架构/桌面壳/扩展）+ 一期与 P0+P1 完成记录 |
| [`specs/2026-09-02-tracking-enhancement.md`](specs/2026-09-02-tracking-enhancement.md) | **现行** | 投递追踪增强：面试/联系人/Offer 独立 CSV、反编造护栏、时间线 |
| [`specs/2026-09-02-resume-data-driven.md`](specs/2026-09-02-resume-data-driven.md) | **现行** | 简历数据驱动「标准版式」：JSON + 内置模板渲染 PDF + ATS 校验。**注意**：文中的 `resume_build.py render` 等旧命令现已只打印迁移提示并退出 2（现状：`python tools/jobws.py resume …`）；「Python 3.8 兼容」为当时基线（现为 3.12） |
| [`specs/2026-09-02-resume-probe.md`](specs/2026-09-02-resume-probe.md) | 已完成 | 简历 PDF 文本抽取探针（ATS 阈值定的依据） |
| [`specs/2026-09-03-p0-p3-roadmap.md`](specs/2026-09-03-p0-p3-roadmap.md) | **现行** | P0–P3 四批：工程底座、投递后闭环、增强、长期资产（含验收记录） |
| [`specs/2026-09-05-batch1-3-roadmap.md`](specs/2026-09-05-batch1-3-roadmap.md) | **现行** | 第一~三批：导入导出闭环、题库与健康度、失败聚类与 JD 抓取（含验收记录） |
| [`specs/2026-09-07-open-source-release.md`](specs/2026-09-07-open-source-release.md) | **现行** | 开源发布：隐私清洗、MIT、治理入口、CI 与发布流程。**注意**：开头的「现状审计」一节（LICENSE 缺失、`.github/` 仅 ISSUE_TEMPLATE 等）是 2026-09-07 的当时记录，均已反转，现状以仓库实际为准 |
| [`specs/2026-08-30-autumn-recruit-workbench-design.md`](specs/2026-08-30-autumn-recruit-workbench-design.md) | ⚠️ **已废弃** | v1.0 个人工具设计。目录结构已失效，**勿据此开发**。保留作评分框架的设计依据追溯 |
| [`domain-contract.md`](domain-contract.md) | **现行** | 领域插件契约：结构、格式、边界与校验方式（`jobws lint domains` 的判定依据） |

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
| [`research/report_electron_33_to_44.md`](research/report_electron_33_to_44.md) | **Electron 33 → 44 升级调研**（执行级）：官方破坏性变更逐条对照我们的实际 API 面（对照 `main.js` 行号）→ 风险分级 + 桌面冒烟清单。结论：CI 完全不碰 Electron，所以「CI 全绿」不能作为升级依据；真正要验的是打包链路（v42 起不再 postinstall 下载二进制）、缩放四件套、自动更新与 PDF 预览 |
| [`research/report_full_repo_audit_2026-09-16.md`](research/report_full_repo_audit_2026-09-16.md) | **全仓库审计报告（2026-09-16）**：结构 / 依赖 / 配置 / 规模盘点、发现清单与按优先级改进建议——治理批与整改批的依据（docstring 与数字为当时快照） |
| [`research/oauth2-imap-feasibility.md`](research/oauth2-imap-feasibility.md) | **Outlook / 企业邮箱 OAuth2 for IMAP 可行性调研**（2026-09-24）：Google / Microsoft 应用注册与本地回调要求、令牌安全存放取舍、零依赖下的工作量估算与建议——结论为「v1 不做，触发条件见文内」，每一条带来源、未核实项显式标注 |

## 开发流程

| 文件 | 说明 |
|---|---|
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | **贡献入口（英文短索引，对齐 README 的 English-first）**：隐私红线、环境搭建、本地验证链、提交与 PR 规则、新需求四道门，并指向下面两份完整细则 |
| [`contributing.zh-CN.md`](contributing.zh-CN.md) | **完整中文细则（权威版）**：分支策略与双轨审查、提交规范、版本号体系、CHANGELOG 写法、发布流程与发布治理、可持续性约定、i18n 约定、代码卫生 |
| [`contributing.en-US.md`](contributing.en-US.md) | **英文伴读版（两档承诺）**：贡献者必读节（定位、隐私、四道门、分支与 PR、提交规范、四端一致性、文案 i18n、代码卫生、明确不做、可持续性）与中文版同步；治理节（版本号体系、CHANGELOG 写法、发布流程与发布治理、AI 协作者、开发者工具）只给摘要——全文与决策史在中文版，任何冲突以中文版为准 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 变更记录（单文件两级制：白话「看得见的变化」+ 英文摘要 + 「技术细节」；格式基于 Keep a Changelog）；版本号唯一来源为 `web/electron/package.json` |
| [`four-ends.md`](four-ends.md) | 四端能力对照与例外清单（`jobws lint four-ends` 的说明页，由 `tools/four_ends_matrix.json` 生成，勿手改） |
| [`glossary.md`](glossary.md) | 术语表：文档与 CHANGELOG 里出现的内部术语集中定义一次 |
| [`maintenance.md`](maintenance.md) | 仓库维护说明（英文）：发布节奏、版本号纪律与项目健康度的对外交代 |
| [`support-and-compatibility.md`](support-and-compatibility.md) | **毕业条件、支持策略与数据兼容承诺**：什么时候算正式版（四条判据）、支持哪些环境、升级为什么不需要转换数据 |
| [`release-checklist.md`](release-checklist.md) | **发布检查清单**：CI 自动项（三道闸 / 安装卸载冒烟 / SHA256 / SmartScreen 公告）与人工必做项（真机通知实测 / 人眼验收 / 落章与演练）、发布后 72 小时与回滚 RUNBOOK |
| [`../SECURITY.md`](../SECURITY.md) | 安全策略：威胁模型、local-first 取舍记录（如 unsigned 自动更新链）与报告方式 |
| [`../ROADMAP.md`](../ROADMAP.md) | 路线图：Now / Later 与已完成批次日志（细节进 CHANGELOG） |
| [`../THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md) | 第三方依赖与许可清单 |
| [`../.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) | Issue 模板：bug 报告与功能请求两份（功能请求含 fit check；新需求仍按 CONTRIBUTING 四道门评估） |

## 决策记录（ADR）

单项决策留痕：一条一文件，文件名 = 祈使动词 + kebab-case。「为什么这样定」写这里；路线图与 CHANGELOG 只记「做了什么」。

| 文件 | 说明 |
|---|---|
| [`decisions/keep-hooks-local-and-off.md`](decisions/keep-hooks-local-and-off.md) | 宿主 hooks 保持本地、默认关闭，本批不实现（含替代方案与复评条件） |
| [`decisions/keep-writes-human-confirmed.md`](decisions/keep-writes-human-confirmed.md) | 写入一律人工确认：不做自动投递、不代登录、AI 产出永不直接落盘 |
| [`decisions/ship-once-per-release.md`](decisions/ship-once-per-release.md) | 单一发布节点 + 月粒度 CalVer 版本号（`YY.MM.N`；2026-09-24 自时间戳四段改版，原文保留含更新注记） |
| [`decisions/read-missing-columns-as-empty.md`](decisions/read-missing-columns-as-empty.md) | 工作区数据向后兼容：读时缺列按空、写时统一表头、不要求迁移 |

## 约定文件

| 文件 | 说明 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | AI 工作约定：三层架构铁律、通用/个人边界、工程约束、目录约定 |
| [`../template/AGENTS.example.md`](../template/AGENTS.example.md) | 候选人档案模板，含逐项填写说明与真实样例 |
| [`../template/workspace/README.md`](../template/workspace/README.md) | 六个模块的用途、填写顺序、关键纪律 |

## 领域插件

**`init --domain` 该选哪个**——按专业对号入座（详情点进各插件的 `profile.md`）：

| 插件 ID | 适用人群 | 覆盖岗位 |
|---|---|---|
| `hvac-cooling` | 建环、暖通、能动、制冷及相关专业 | 数据中心冷却/热管理、IDC 基础设施、空调制冷研发、暖通设计、建筑节能、液冷产品、储能热管理 |
| `software-backend` | 计算机、软件工程、数据科学及相关专业 | 后端开发、服务端开发、数据工程、大数据开发、平台工程 |

| 文件 | 说明 |
|---|---|
| [`../template/profiles/hvac-cooling/profile.md`](../template/profiles/hvac-cooling/profile.md) | 暖通制冷与数据中心冷却插件（内置方向：`datacenter`、`hvac`、`thermal-management`、`thermal-fluid-cfd`、`thermal-design-cae`、`energy-storage-thermal`） |
| [`../template/profiles/software-backend/profile.md`](../template/profiles/software-backend/profile.md) | 软件后端与数据工程插件（内置方向：`backend`、`data`；用于验证跨领域可扩展性） |

新增领域只需新增一个插件目录，无需改代码——**契约全文见 [`domain-contract.md`](domain-contract.md)**（结构、格式、边界与校验方式）；提交前跑 `python tools/jobws.py lint domains`（CI 同一实现）。

## 技能文件（工作流定义）

`../skills/` 下九个：五个求职向——`jwb-recruit-coach`（评分标准与红线）、`jwb-jd`、`jwb-apply`、`jwb-track`、`jwb-resume`；一个扩展向——`jwb-domain-setup`（生成 / 定制领域插件，人确认制）；三个开发向——`jwb-cli-contract`（CLI 契约）、`jwb-api-review`（API 审查）、`jwb-mcp-server`（MCP 指南）。

这些既是 AI 可加载的技能，也是各工作流的规格说明——读它们等于读流程定义。

## 组件 README

| 文件 | 说明 |
|---|---|
| [`../web/README.md`](../web/README.md) | Web 界面层：八个页面、与 CLI 的关系、目录结构、已知边界 |
| [`../web/frontend/README.md`](../web/frontend/README.md) | 前端工程说明（构建链与运行方式） |
| [`../mcp/README.md`](../mcp/README.md) | MCP 服务：14 个工具（6 只读 + 7 个两段式预览 + `apply_approval`）、安装与宿主配置、工作区解析 |
| [`mcp-integration.md`](mcp-integration.md) | MCP 接入专篇：安装、宿主配置（三种形态，键名各异）、工作区解析、两段式用法与故障排查 |

## 已归档代码

| 文件 | 说明 |
|---|---|
| [`deprecated/fix_links.py`](deprecated/fix_links.py) | 个人重组时用的一次性断链修复工具，已停用。保留作路径替换逻辑的参考 |
