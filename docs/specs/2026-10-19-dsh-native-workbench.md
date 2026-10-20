# DSH 原生求职工作台（方案 D）设计文档

- 状态：**待确认**（设计期；G1 冻结中，**不进入 `v26.11.0` 候选**）
- 日期：2026-10-19（起草，含当日隔离环境实测）
- 相关：[`docs/four-ends.md`](../four-ends.md)（能力矩阵）、[`integrations/dsh/README.md`](../../integrations/dsh/README.md)（安装落地页）、[`docs/handover/2026-10-19-g2g3-runbook.md`](../handover/2026-10-19-g2g3-runbook.md)（G2/G3 验收）

---

## 一、问题陈述（不含解决方案）

DSH 是本项目的**第一等交付入口**之一（与桌面端/CLI/MCP 并列），但当前形态只有「17 个 MCP 工具 + 9 个技能」——**没有任何用户可见的界面**。用户装完之后，只能靠"模型突然会用了"来推断它生效。

更关键的是能力映射的落差。以 `tools/four_ends_matrix.json` 为唯一数据源（2026-10-19 机械核对）：

| 象限 | 能力数 |
|---|---:|
| 桌面端与 MCP 都有 | 16 |
| **仅桌面端有** | **34** |
| 仅 MCP 有（`jd.score`） | 1 |
| 两端都无（CLI/插件独有） | 3 |
| 合计 | 54 |

所以「装了 9 个技能」≠「9 种工作流在独立 DSH 里都能跑完」。此前评估过的 A（只显示状态）/ B（状态+待办）/ C（再加简历卡）**是同一种轻量插件的三个信息量版本，不是三种产品形态**——即使选 C，用户仍然看不到岗位决策、面试训练、招聘邮件、联系人、Offer 与知识素材。

---

## 二、目标 / 非目标 / 反目标

**目标**

1. 一个 DSH 原生「求职工作台」入口，内部八模块导航——不占满宿主侧栏，也不拆成八个顶层 tab。
2. 左栏（AI 对话）负责思考、分析与操作；右栏负责状态、提醒与发现。**右栏只读。**
3. 能力状态如实可见：每个能力条目标注五态之一，不让用户把"规划中"误读成"已可用"。
4. UI 与 AI **共享同一个 MCP 服务实例**，不复制领域逻辑、不增加第二套常驻进程。

**非目标**

- 不把桌面端 React 应用搬进 DSH（宿主 React 18 + primitives，与桌面端 React 19 + Tailwind + Radix 不通）。
- 不追求 54 项能力全覆盖；高风险操作（凭据/备份/迁移/删除）刻意留给用户在受信任界面执行。
- 不进入 G1 冻结候选；不新增 MCP 写入工具。

**反目标（出现任一即失败）**

- 空壳模块、假按钮、永远"即将推出"的空白面板、虚构的状态数据。
- 「前端传工具名、Node 就执行」的通用工具代理。
- 建立 DSH 专属的第二套业务真源（评分、事实校验、工作区归属仍归 `jobws_core`）。
- 用宿主通用文件/终端工具绕过 MCP 两段式确认协议。

---

## 三、已核实的架构事实（2026-10-19 隔离实测，非推断）

实验方法：在隔离 `DSH_HOME` 里装本插件 + 一个一次性探针插件（`inject: ['tools']`，不 spawn 任何东西），用 `dsh headless "say ok" --profile <p>` 无头启动宿主，探针把证据写进 `<DSH_HOME>/probe-evidence.json`。

| # | 事实 | 证据 |
|---|---|---|
| 1 | **客户端（web）不能调 MCP** | `deepseek-ai/deepseek-harness` 的 `packages/client/` 66 个包无 mcp 相关；`dsh-client-connection`/`api-remotes`/`store` 的导出里无 `callTool`；第三方 `dsh-mcp-view` 也只走宿主 HTTP 且明言"只能列工具不能调" |
| 2 | **node 半可跨插件执行工具** | 探针实测 `ctx.tools.execute({callId,name,arguments,signal})` 成功调用 `mcp__jobws__dashboard_summary` 与 `mcp__jobws__score_calibration`，返回**真实台账数据**；`ToolRuntime` 公开方法 `register/restrict/guard/presentAs/get/schemas/executionMode/execute` 全部在位 |
| 3 | **调用无鉴权** | 未提供 session/caller/agent 即调用成功——**这是安全设计的起点，不是便利** |
| 4 | **工具名会加哈希** | `jobws.info` 实际注册为 `mcp__jobws__jobws_info_50bd514446ab`（名字含点 → 规范化后追加 sha256(12)）；`dashboard_summary`（无点）为本名。**名称不可硬编码** |
| 5 | **启动有 ~2.1 秒空窗** | 探针 `apply()` 后 201ms 内调用全 `UNKNOWN_TOOL`；监听 `tools/change` + 轮询后，工具在 **2105ms** 集中可见（事件 1846–1847ms 爆发） |
| 6 | **进程** | 方案 (a) 零新增进程；每次宿主启动 spawn 1 个 `jobws-mcp.exe`，实测 RSS ≈ **76MB** |
| 7 | **宿主不回收子进程** | SIGKILL 宿主后 MCP exe 残留（实验因此留下 5 个孤儿宿主，已清理）；优雅退出是否回收**未验证** |

---

## 四、信息架构

### 4.1 八模块导航（紧凑式，非顶部横排胶囊）

右栏实测宽度约 320px，八个模块若横向平铺会换行挤压内容。采用「常用 + 更多模块 ▾」：

- **常用**：总览 / 投递管理 / 面试准备 / 岗位决策（按 MCP 覆盖厚度选，**此归类为设计者判断，可调**）
- **更多模块**：简历工坊 / 招聘进展 / 事实与素材 / 工作台设置（八个均保持可发现）

### 4.2 模块定位与当前 DSH 基础

| 模块 | 当前 DSH 基础 | 在方案 D 中的定位 |
|---|---|---|
| 总览 | 摘要、筛选校准 | 默认首页，可直接使用 |
| 岗位决策 | 岗位读取、评分校验 | 部分可用，重点补完整 JD 工作流 |
| 投递管理 | 新增、更新、导入、查询 | 当前最成熟的核心业务区 |
| 简历工坊 | 技能指引为主 | 模块可见，明确引导桌面端；后续补事实与版本读取 |
| 面试准备 | 题库查询、新增、导入 | 部分可用，后续发展对话式训练 |
| 招聘进展 | 面试相关 MCP 工具 | 部分可用；邮件/联系人/Offer 主要在桌面端 |
| 事实与素材 | 缺少专用 MCP 读取工具 | 模块可见；重点说明事实库与反编造能力 |
| 工作台设置 | `jobws.info` | 连接诊断在 DSH；高风险配置由用户操作 |

### 4.3 五态徽标（能力态，与连接态分离）

| 徽标 | 含义 |
|---|---|
| `● DSH 可用` | 当前版本已实现并验收，有明确可执行入口 |
| `◐ 部分可用` | 已实现部分步骤，并说清缺失环节 |
| `↗ 桌面端支持` | 产品已实现，但 DSH 当前不能独立完成 |
| `🔒 需本人操作` | 因权限/安全设计，必须由用户在受信任界面执行 |
| `○ 规划中` | 尚未实现，且已进入计划 |

**连接态单独一行**（服务在线/离线）。功能已实现但 MCP 断开时显示「功能已支持，当前连接不可用」，**不得**把条目降级为「待开发」。

---

## 五、数据通道（方案 a）与五个前置条件

### 5.1 链路

```
DSH Client UI（右栏，只读）
  → 官方客户端通信层（ctx.connection.rpc.call；不自建未保护 HTTP）
  → DSH Node 插件（白名单 + 名称发现 + 三态）
  → ctx.tools.execute（宿主工具执行接口）
  → 既有 jobws MCP（宿主已 spawn 的同一实例）
  → jobws_core（领域逻辑唯一真源）
```

### 5.2 五个前置条件（缺一不实施）

1. **工具名运行时发现**：扫 `ctx.tools.schemas()` 匹配，禁止硬编码（事实 4）。
2. **严格白名单**：只放行 `jobws.info` / `dashboard_summary` / `score_calibration` 三个只读工具；其余一律拒绝——**包括 `mcp__jobws__apply_approval` 等写工具**（事实 3 证明可调）。
3. **UI 三态**：连接中（工具未注册，~2s 空窗）→ 已连接 → 功能已支持但连接不可用（事实 5）。
4. **通信走官方 RPC**：优先 `ctx.connection.rpc.call`；若最终必须自建 HTTP，须处理身份、Origin、权限、脱敏与失败态（只读不等于不敏感）。
5. **ptc 模式补验**：`executionMode()` 的正确调用方式未验证；若宿主跑 ptc 模式，无 `parent` 的直接调用可能只允许 `run_code`，调 `mcp__*` 会得 `UNKNOWN_TOOL`。
6. **官方 RPC 往返实测**：`ctx.connection.rpc.call` 是链路第一跳，但方向性未实测（见 §9.2 Q2）；实施前必须先做一次浏览器 → Node 插件 → 回显的最小往返。不通则整体换备选通道。
7. **网络出站实测**：见 §6.3——不能只靠代码审查证明"没有 fetch 到外网"，因为请求可能来自宿主、模型 SDK 或第三方插件。

### 5.3 前置条件 6 的实测进展：RPC-E1（2026-10-19，隔离 web profile）

实验内容：写一个双半探针插件（Node 半 `ctx.connection.rpc.handle('/com.jobws.echo', …)`；
Client 半 `ctx.connection.rpc.call(...)` 回显 nonce 并渲染到 DOM），装进**全新隔离**
`DSH_HOME` 的 `e1` profile，用 `dsh --profile e1 web` 启动真实浏览器客户端。

| 验证项 | 结果 | 证据 |
|---|---|---|
| Node 半能否拿到 `connection` 服务 | **FAIL** | 三种配置全部 `pending (waiting for service: connection)`：① `inject:['connection','webServer']` ② `inject:['connection']` ③ 再加 `peerDependencies`（照 better-sidebar 的写法声明 `@deepseek-ai/dsh-client-connection`） |
| web profile 是否提供 `connection` | **否** | `--dump-config` 装配清单（20 个宿主内置插件）里**没有**提供者；`typert-gateway`(`@deepseek-ai/dsh-api-gateway`) 是**消费方**不是提供方 |
| 第三方有无先例 | **无** | `dshmarket` 的 node 半不 inject 任何服务；`dsh-better-sidebar` 的 peerDeps 里没有 connection |
| Client 往返能否验证 | **未验证** | 隔离环境无模型凭据，web 服务起不来——宿主进程活着但**零监听端口**（`Get-NetTCPConnection` 无记录） |

### 5.3.1 desktop profile 复测（2026-10-20，用户执行）：两条官方路都断了

在 desktop profile 实测（隔离 `DSH_HOME`，探针 0.3.0 → 0.4.0 → 0.5.0）：

| 步骤 | 结果 |
|---|---|
| `ctx.connection` / `ctx.connection.rpc` / `rpc.handle` 可用性 | **全部 true**——desktop profile **确实提供** `connection`（与 web profile 不同） |
| **路 A `rpc.handle('/com.jobws.echo', …)`** | **FAIL**：`cannot get property "webServer" without inject`。即使插件自己 `inject: ['connection','webServer']` 也无效——源码里 `get rpc()` 的 `owner = this.ctx` 绑的是 **connection 服务自己的 fiber**，`register()` 走 `owner.webServer.register(route)`；宿主的 desktop 装配没给 connection 接上 webServer |
| **路 B `rpc.intercept('/api', matches, …)`** | 注册**成功**（`PASS(node)`），但约 3 分钟后**宿主崩溃**：`desktop welcome: Web request failed`（`openInitialWindow → settingsAndReference`）。宿主自己的 `@deepseek-ai/dsh-api-gateway` 同样 intercept `/api`——第三方再拦同一通道会破坏宿主欢迎流程。**此为推断**（未做对照实验），但同期 0.4.0（只试 handle、异常被捕获、不碰 `/api`）在同样环境下启动正常，两次唯一差异就是这次拦截 |
| 客户端调用 | 0.3.0 下得到 `HTTP 405`（路由未注册）；0.5.0 下因宿主崩溃**未能验证** |

**结论：官方 RPC 对第三方插件实质关闭。** `handle` 因宿主接线缺口不可用；`intercept('/api')` 虽能注册，但与宿主自有 gateway 抢同一通道、有把宿主搞崩的风险。**不得**在方案 D 里使用任何一条。

**连带教训（实验纪律）**：本轮由用户执行脚本，实验实例在用户屏幕开出窗口并弹出崩溃对话框——**GUI 类实验必须先告知用户会看到什么、并备好一键清理**。

**结论：E1 记 FAIL（环境/契约限制，不是代码错误），不得宣称 PASS。**

按实验纪律，**没有**用 Node 侧结果冒充浏览器往返——因为浏览器侧从未加载成功。

> **重要更正（2026-10-20）**：`integrations/dsh/scripts/install.ps1:46` 的默认 profile 是
> **`desktop`**（`[string]$Profile = 'desktop'`），README 的安装命令同样指向 desktop。
> 也就是说**我们的插件实际运行在 desktop profile，而 E1 测的是 web profile——测错了目标**。
> 因此上面的 FAIL **不能**用来判定方案 (a) 不成立：它只说明"web profile 不向第三方
> bundle 插件提供 `connection`"。**决定性实验是 desktop profile 的复测。**

**剩余路径（按优先级）**：

1. **desktop profile 复测（决定性）**——`connection` 很可能由 Electron 主进程提供
   （web profile 没有）。约束：本机已有 DSH 实例运行时，Electron 单实例锁会阻止第二个
   实例，需在用户侧执行；步骤见 §5.4；
2. 向 DSH 宿主提一个**最小的只读能力请求**（官方支持比私接稳）；
3. 退回"受保护的 host HTTP 路由"（`dsh-mcp-view` 模式）——需自行处理身份 / Origin / 权限 / 脱密。

> 在 desktop profile 复测给出结论前，数据通道应视为**未定**，不得按 (a) 写实施计划。

### 5.4 desktop 复测的操作步骤（需用户在自有机器上执行）

因 Electron 单实例锁，第二个隔离实例无法与用户正在运行的 DSH 共存，所以这一步
**必须由用户执行**。脚本：`.codebuddy/tmp/e1-desktop-retest.ps1`（纯 ASCII，避开编码坑）：

1. 建全新隔离 `DSH_HOME`；
2. 先启动一次 app 让 desktop profile 初始化，然后按 PID 树退出；
3. `dsh plugin --profile desktop add jobws-rpc-echo-0.3.0.tgz`；
4. 再启动一次，等 40 秒；
5. **Node 半答案自动可取**：读 `<DSH_HOME>\rpc-e1-node.json`——`verdict` 为
   `PASS(node)` 即说明 desktop profile **能**提供 `connection`；
6. **Client 往返答案需人眼**：app 窗口**左下角**应出现绿底黑字块，内容含
   `"nonceMatch": true` 与 `PASS(client)`；没有则记 `FAIL(client)`。

只清理本次创建的进程树，不碰用户真实的 `~/.dsh`。

---

## 六、安全边界

- 右栏**只读**；一切写入仍走左栏对话里的 MCP 两段式确认（preview → 用户确认 → `apply_approval`）。
- Node 侧白名单是硬边界，不做"通用工具代理"。
- 不通过宿主文件/终端工具编辑 CSV、读取邮箱正文或覆盖简历。
- 凭据、备份还原、数据迁移、删除类操作标 `🔒 需本人操作`，不交给模型。

### 6.1 实验纪律（2026-10-19 自查发现，必须遵守）

本次隔离实验**读到了真实台账**：`DSH_HOME` 隔离了宿主状态，但**数据根由 Job Workbench 自己决定**（默认 `%APPDATA%\job-workbench\data`），所以探针拿到的 `dashboard_summary` 是真实工作区数据（证据文件含真实路径与聚合统计，已删除）。

此后任何实验必须：

1. 先设 `JOBWS_DATA_DIR` 指向**虚构工作区**（`jobws init` + 假数据），再启动宿主；
2. 运行前打印并核对实际数据根，**未确认即终止**；
3. 证据日志不得包含真实公司、岗位、简历或凭据；实验结束后按第 1 条清理。

### 6.2 四条隐私原则（与 [`docs/data-flow-matrix.md`](../data-flow-matrix.md) 一致，不另立口径）

1. **默认本地处理**：工作区数据、统计计算、右栏展示与本地状态查询，**不得**为了渲染 UI 而调用远程模型。
2. **AI 出站可知可控**：用户主动调用云端 AI 时，明确当前模型服务商；简历、事实库、邮件等敏感数据采用更严格的读取与授权策略。
3. **不提供任意工具代理**：Node 桥接只放行审核过的只读能力；客户端不得任意指定工具名，不得用通用文件操作绕开写入确认。
4. **必须有网络出站实测**：见 6.3。

### 6.3 隐私承诺的准确表述

**不得**把 DSH 版本宣传为"所有数据绝不上传"——只要用户启用云端 AI，相关输入与工具结果就可能发给其配置的模型提供商。准确表述（已同步进 [`docs/data-flow-matrix.md`](../data-flow-matrix.md)，那是隐私承诺的权威底稿）：

> Job Workbench 默认在本地保存和处理求职数据，不自动同步到项目方服务器。DSH 原生界面的常规数据展示不需要云端模型。只有用户启用云端 AI 或其他联网功能时，相关请求数据才可能发送给所配置的第三方服务。数据发送范围、使用条件和服务商应当明确披露，并接受验证。

---

## 七、留给构建者的未知

| 项 | 状态 |
|---|---|
| ptc 模式下 `mcp__*` 可否被第三方调用 | **未验证**（`executionMode()` 调用方式待查） |
| 宿主优雅退出是否回收 MCP 子进程 | **未验证**（只测了 SIGKILL，结论是残留） |
| 右栏最终排版（320px 实测下的信息密度） | 待真实宿主内验证 |
| i18n：宿主 `ctx.locale.register(ns,{zh,en})`，不用 i18next | 契约已明，未实跑 |
| 常用模块的归类（4 个） | 设计者判断，可能调整 |
| 能力投影视图（canonical capability ID → DSH 状态） | 建议作为 `four_ends_matrix.json` 的**扩展映射**，不建第二套业务定义 |

---

## 八、与 G1 冻结和发布的关系

- 本文档是**设计期产物**，不进入 `v26.11.0` 候选；下一正常研发周期才正式实现。
- `v26.11.0` 首发时 DSH 只有现有 MCP 能力（17 工具 / 9 技能），**发布说明必须如实写支持范围**，不得以"已打包九个技能"暗示"桌面八大模块都在"。
- 用户指南另见 [`docs/dsh-user-guide.zh-CN.md`](../dsh-user-guide.zh-CN.md)（英文主版待补）。

---

## 九、构建者检查的处置（2026-10-19）

换一双新鲜眼睛审本文档后提出 6 个问题。逐条处置如下——**标注「设计者判断」的是我定的，标注「待确认」的必须由维护者拍板。**

### 9.1 待确认（维护者拍板，会实质改变计划）

**Q1 · 是否允许为方案 D 新增只读 MCP 工具？——已裁决：有条件允许（2026-10-19）**

三条原则：① 优先补核心 AI 工作流**必需**的读取能力（事实证据、简历版本、结构化招聘记录），
已有 17 个工具能做的**不重复开发**；② 新工具属**通用 Job Workbench MCP 协议**，
不为 DSH 单独实现一份业务逻辑，读取与校验继续复用 canonical 领域层；③ **只读不等于可
随意外传**——必须限定数据范围、大小与授权边界，**不新增任意路径读取工具**，更不默认把
结果送给云端模型。

| 批次 | 能力 |
|---|---|
| 第一批 | 事实资料的结构化安全检索；简历版本与基本元信息读取 |
| 第二批 | 投递阶段时间线；Offer / 联系人等**受限摘要** |
| 后续独立审查 | 邮件正文与更敏感资料（需额外隐私授权与数据最小化设计） |

**验收指标不是工具数量**：一个完整求职任务能否从「读取证据 → 分析 → 预览 → 确认」安全完成。

**Q4 · 发布载体——已裁决：并入现有 `dsh-job-workbench` 主包（2026-10-19）**

采用同一个插件包，内部双入口：`.`（Host/Node：MCP 接入、受控数据桥接）+
`./client`（Client/UI：八模块导航、状态与展示）。理由：与"单产品、多交付端"架构一致——
用户只装一个包、复用既有 MCP/技能安装机制、不新增第二个 marketplace 产品身份、避免版本
与能力漂移。Windows 平台运行时子包继续作为**分发内部组件**，不构成第二个产品。

**但同一个包不等于所有代码写在一起**：Node 桥接 / Client UI / MCP 接线 / 领域工具必须保持
明确模块边界。且双入口须通过**目标 DSH 版本的实际装载、通信与安全实测**——不能凭跨插件
`ctx.tools.execute()` 实验成功就宣称完整链路成立。

### 9.2 设计者判断（已写入计划假设）

**Q2 · `ctx.connection.rpc.call` 的方向性未实测。**
文档 5.1 把它列为链路第一跳，但只验证了"客户端不能自己调 MCP"，没验证 RPC 能否让浏览器调到 Node 插件。
→ **升级为第六个前置条件**：实施前必须先做一次最小 RPC 往返实测（浏览器 → Node 插件 → 回显）。若不通，整条链路改用备选通道（自建带身份校验的 HTTP），工作量按数量级变化。

**Q3 · ptc 模式是否必须支持？**
→ **v1 只在 native 模式支持**；ptc 会话下右栏显示降级提示（"当前会话模式不支持面板，请在普通会话查看"），**不假装可用**。不做第二套调用逻辑。

**Q5 · 五态投影的权威位置与更新责任。**
→ 投影作为 `tools/four_ends_matrix.json` 的**扩展映射**（维护者已定的方向：不建第二套业务定义）；更新节奏与 `assets_registry` 同批——**每版落章时由维护者更新**，实现期把它当冻结输入，不在开发中随手改。

**Q6 · UI 的验收方式。**
现有 G2/G3 验收全是无头/CLI，没有 DSH 右栏的界面验收手段。
→ **v1 用手动验收清单**（复用 `docs/handover/2026-10-19-g2g3-runbook.md` 的一页纸形态：每项三勾 + 预留实际状态），并**保留本次的探针插件作为回归手段**（它能验证工具可见性与调用结果，正好覆盖"连接中/已连接/不可用"三态）。
