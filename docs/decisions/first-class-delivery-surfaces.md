# 决策：第一等交付面与集成边界（First-Class Delivery Surfaces and Integration Boundaries）

- 状态：已采纳（2026-10-06）
- 相关：[`../four-ends.md`](../four-ends.md)（能力矩阵）、[`../mcp-integration.md`](../mcp-integration.md)（宿主接入）、[`../../integrations/dsh/README.md`](../../integrations/dsh/README.md)（DSH 装配）、[`../research/report_dsh_plugin_distribution.md`](../research/report_dsh_plugin_distribution.md)（发行物调研与宿主 Python spike）、[`single-canonical-data-root.md`](single-canonical-data-root.md)（数据同源）

## 背景

Job Workbench 的调用面已经不止一个：Web 后端、命令行、桌面端、通用 AI 宿主（MCP / 技能），以及 DeepSeek Harness（`integrations/dsh/`）。[`../four-ends.md`](../four-ends.md) 的能力矩阵从 2026-09 起就在登记「同一能力由谁提供、哪里不提供及其原因」。

2026-10 的 DSH 接入（工具注解 / caller-scope 实证 / 接入件 / 会话内验收）与发行物调研（[`../research/report_dsh_plugin_distribution.md`](../research/report_dsh_plugin_distribution.md)）把一类边界问题推到了台前：DSH 端要不要拆成独立项目 / 独立仓库？「完整 DSH 插件」与「独立项目」是不是一回事？「第一等入口」是不是要求所有端都已有独立安装器？这些问题在第二阶段（bundle / runtime / 自包含分发）开工前必须冻结答案——否则每引入一个宿主都会重新讨论一遍。

一条实测事实为讨论托底：`integrations/` 在全部代码与配置（Python / TS / JS / JSON / YAML / 打包脚本）中**零外部引用**（唯一命中为该集成目录自身）——「删除 DSH 集成模块，其余端照常成立」当前就成立。

## 决策

> Job Workbench is one product with multiple first-class delivery surfaces. Desktop, Web, CLI, generic AI-host integrations, and DeepSeek Harness may be installed and used independently. Each surface owns its runtime integration and native UX, while domain logic, workspace semantics, mutation protocols, and product versioning remain shared. Runtime independence must not create a forked domain implementation.

> Job Workbench 是一个具有多个第一等交付面的单一产品。Desktop、Web、CLI、通用 AI 宿主和 DeepSeek Harness 可以独立安装和使用；各端拥有自己的运行时集成与宿主原生体验，但共享领域逻辑、工作区语义、变更协议和产品版本体系。**运行时独立不得演变为领域实现分叉。**

### 不变量

1. **第一等交付面**：用户不应为了使用一个端，被迫安装另一个不需要的端（DSH / CLI / Web 不要求 Desktop 已安装；MCP 不要求 Web 后端已运行）。各端以**能力等价（capability parity）**衡量，而非实现等价：每个第一等端都能覆盖核心领域工作流，但不要求相同 UI、相同命令名或相同技术实现（桌面端用表单 / 表格 / 看板，命令行用命令，DSH 用自然语言 + 技能 + MCP 工具）。**不得以「某端没有另一端的 Dashboard / 表单」判定其不是完整端。**
2. **单一产品 / 单一发布线**：产品版本 = Job Workbench `YY.MM.N`（见 [`ship-once-per-release.md`](ship-once-per-release.md)）。DSH bundle 等各端制品是**同一发布线上的不同 artifact**，不是独立产品、不设独立版本号；宿主兼容范围（如 `dsh.engines.dsh` 声明）是**另一个维度**的兼容声明，不构成独立版本体系。
3. **运行时独立、领域共享**：各端可自带运行时集成、技能资产、preset 与健康检查；但 JD 规则、工作区 schema、方向、投递语义、preview/apply 协议、简历规则等**必须来自 canonical 实现**（`packages/jobws-core` 与既有协议），不得复制维护第二份。
4. **依赖方向**：`jobws-core ← CLI / Web / MCP ← DSH integration`；**禁止反向**——core / runtime 功能不得反向依赖任一宿主集成实现。（推论：「删除某宿主集成目录，其余端照常成立」是架构性质，不是偶然现状。）
5. **复评触发条件**：仅当组织、发布、贡献或生态约束**实质超过** monorepo 的同步收益时，才重新评估拆仓——信号清单见文末「复评条件」。

### 架构状态 vs 分发成熟度（两个维度）

「第一等」是架构与产品路线属性，不等于「今天已有独立安装器」。两者分开看待：

| 端 | 架构状态 | 当前分发成熟度 |
|---|---|---|
| Desktop | 第一等 | 已打包（安装包 + 自动更新） |
| Web | 第一等 | 源码 / 运行时形态 |
| CLI | 第一等 | 源码 / 运行时形态 |
| MCP（通用 AI 宿主） | 第一等 | 专用 venv（独立 artifact 属第二阶段） |
| DSH | 第一等（架构） | 预正式化（仓库内装配；runtime 方向已冻结于调研报告） |

### 模块边界与目录位置

DSH 集成是**独立模块边界**；当前目录为 `integrations/dsh/`。**目录位置是实现摆放，不是本决策的对象**：若集成未来获得实质的可执行 / 包实现（如运行时桥接的 JS 外壳），允许迁往更合适的位置（如 `packages/`）——**迁移不改变产品身份、发布线归属或上述架构边界**。

### 打包纪律（对第二阶段的约束）

- **技能同源生成**：canonical 技能真源 = `skills/`；`.agents/` `.claude/` `.codebuddy/` 等镜像与未来 DSH bundle 内的 `skills/` **都必须是生成物**，由同一同步机制产出并纳入 `lint four-ends` 的镜像一致性治理——bundle 的 skills 不得成为第五份人工维护真源。
- **领域代码同源**：DSH artifact 允许在**打包时**收录（vendor / package）Job Workbench 领域代码；**禁止**维护 DSH 专属 fork（构建时拷贝 ✅ / 分叉后各自手改 ❌）。「运行时独立」的经济性正来自这一条。

### 验证（architecture fitness）

- **删除判据**：删除 DSH 集成模块后，core / CLI / Web / Desktop / 通用 MCP 的运行时行为不受影响。当前已成立（零代码引用）；它是本决策的**架构体检项**，随集成演进定期复核（可进入集成验收清单）。
- 未来的自动化检查（若做）应检查**运行时依赖 / import 方向**（有无代码从 core 侧加载宿主集成），而不是对仓库全文做字符串禁令——发布脚本、打包、治理与文档**允许**引用集成目录。

## Non-goals（本决策不决定）

- DSH 运行时的最终形态（宿主 Python / 自包含二进制 / 其它——调研结论与重估触发条件见[调研报告](../research/report_dsh_plugin_distribution.md)）；
- DSH 集成的最终目录位置、npm 包名与 scope；
- marketplace 发布方式与时机；
- 是否实现 DSH 客户端 UI；
- 各端分发成熟度的排期（本决策只要求不把它们设计成 Desktop 的附属品）。

## 已评估的替代方案

- **拆成两个仓库 / 两个项目**：DSH 没有独立领域模型（schema、协议、规则全部住在 `jobws-core`），拆分会把同一套 schema 的演化拆成跨仓库协议，并制造两套 issue / 版本 / changelog / CI / 兼容矩阵与跨仓库 PR 顺序——而目标恰恰是同版本、同 tag、同节奏。当前无任何拆仓触发条件成立。
- **把 DSH 定位为 Desktop 的附件**：要求 DSH 用户先装桌面端，直接削弱多入口架构的意义，且与数据根契约（四端可共算同一根）的初衷相悖。
- **现在就冻结目录位置**：目录是实现摆放，过早冻结会在出现 JS 外壳时被迫推翻决策；冻结模块边界即可。
- **把「删除判据」做成全仓字符串禁令**：会误杀合法的打包、发布与治理引用；正确的检查对象是依赖方向。

## Consequences（主动接受的收益与成本）

**收益**：各端独立安装与使用；领域一致性由单一实现保证；发布线单一（同 tag 多 artifact）；避免跨仓 schema 漂移与双重治理。

**成本（承认并接受）**：monorepo CI 更复杂（多 artifact、多端契约测试）；发布流水线需要构建多个制品；能力等价需要契约测试（能力矩阵 + 回归网）长期维护；DSH 宿主兼容范围需要独立跟踪（宿主仍处 rc 阶段）。

## 复评条件

当组织、发布、贡献或生态约束**实质超过** monorepo 的同步收益时，重新评估拆仓。下列信号供评估参考（**满足若干条时评估，不是满足任意一条即拆**）：

1. DSH 集成形成完全独立的维护团队；
2. DSH 制品需要独立发布节奏（如主产品按月、DSH bundle 按周）；
3. 集成出现大量与 core 几无共同提交的专属代码；
4. 宿主社区贡献者不需要 checkout 整个仓库；
5. marketplace / CI / 安全策略明确要求独立仓库；
6. 绝大多数 DSH issue 与主产品无关；
7. 跨仓库版本协议已非常稳定。
