# 调研报告：DSH 插件发行物与宿主 Python feasibility spike

- 调研日期：2026-10-06
- 方式：2 个子代理并行调研（本机 DSH 生态勘察 / 跨生态 Web 实践）+ 1 个限时本机 spike（≤60 分钟，不改产品代码、不碰真实数据、不改任何 profile）
- 本文的用途：**冻结 DSH 插件发行物的 runtime 决策**——「宿主自带 Python」能否作为分发基础，还是必须走自包含 runtime。后续若质疑该决策，先读 §0 结论与 §6 未确认清单。
- 阅读提示：这是调研 + 实验记录，不是设计文档。发行物装配见 `integrations/dsh/`。

## 0. 结论摘要（决策级）

> **Decision: 宿主 Python 路线——技术 PASS，契约 INTERNAL-ONLY；公开发行版仍以 self-contained runtime 为第一设计，宿主 Python 作为「探测到即加速」的优化项与自用/开发形态。**

三句话展开：

1. **技术链路全通（本机实证）**：DSH 宿主自带 Python 3.12.14；用它 + 插件本地依赖，jobws-mcp 完整跑通 MCP 握手（initialize / tools/list 15 工具 / jobws.info 端到端）。两种工程形态都验证通过（PYTHONPATH 组合 / 插件本地 venv）。全程未写宿主 site-packages。
2. **契约层面只到「模型工具」级**：官方有 `load_workspace_dependencies` 工具（tool-catalog 登记，返回 bundled Python 绝对路径）与 `DSH_PRIMARY_RUNTIME` 环境变量等机制，但它们是**模型/技能面向**的；没有找到第三方**插件（JS 侧）**可程序化解析 runtime 的公开 API。直接写死 `resources/runtime/...` 路径属于依赖内部实现。
3. **所以**：宿主 Python 不能作为公开发行版的唯一 runtime 路线（No-Go as sole runtime）；可以作为自用/开发形态立即使用，并为「技能驱动 CLI」场景提供受支持的路径（模型经工具拿 Python 路径跑 jobws CLI）。

### Evidence（实验记录摘要）

| 问题 | 结果 | 证据 |
|---|---|---|
| Q1 第三方能否稳定定位宿主 Python | ⚠️ PARTIAL | 路径存在（`<dsh>/resources/runtime/primary-runtime/dependencies/python/python.exe`，3.12.14）；官方工具有文档化 schema；但**插件侧程序化定位未证实** |
| Q2 该 Python 能否从插件目录执行代码 | ✅ PASS | 执行、venv 创建、脚本运行均实证 |
| Q3 不写宿主 site-packages 加载 jobws | ✅ PASS | 两条路线：PYTHONPATH 组合（含 pywin32 修正）、插件本地 venv |
| Q4 MCP initialize + tools/list | ✅ PASS | `server=jobws ver=0.1.0`；15 工具（注解正确）；jobws.info 端到端（沙盒数据根） |
| Q5 升级/重启后仍成立 | ⚠️ UNRESOLVED | 官方有 runtime 生命周期机制（构建器 / 安装器 / 签名检查 / `DSH_PRIMARY_RUNTIME`），无第三方契约承诺 |

### Rejected

- **uvx 作为普通用户默认路径**：要求用户自备 uv，违反「装插件即用」；保留为开发/高级用户渠道。
- **裸依赖系统 python**：awslabs/mcp 事故（系统旧 Python + 编译依赖绑定 → 报错）是教科书反例。
- **向宿主 site-packages 安装依赖**：违反隔离硬原则（多插件污染、升级覆盖、卸载残留）。

### Fallback

- **Self-contained runtime/binary**（官方 libreoffice-kit 模板：平台包 + `prebuilds.json` 哈希清单）——若宿主 Python 契约长期不开放，作为公开发行的第一选择。
- 若 DSH 提供「第三方 runtime 解析 API」或 mcp-client 支持 runtime 别名，立即重估（触发条件见 §5）。

## 1. 背景：为什么要这个 spike

- 定位讨论已收敛：Job Workbench = 多入口产品，DSH 是平级入口之一；DSH 发行物要做「自包含」形态。
- 上一轮调研发现 **DSH 宿主自带 Python 3.12.14**。若该事实对第三方成立，发行物可从「带一套 Python runtime 的重插件」压缩为轻配置/技能包；若不成立，需维护二进制发行链。未知数价值高、验证成本低 → 限时 spike 先行。
- 硬约束：不改产品代码、不碰真实数据、不改任何 profile（离线实验）、60 分钟 timebox，超时即判 UNRESOLVED。

## 2. 调研发现小结

### 2.1 DSH 插件生态（本机第一手勘察）

- **配置型 bundle** 的 manifest = `dsh.bundle.patch`（指向包内 `cordis.patch.yml`，相对路径字符串），第三方样本 ×3 验证（本机已装的 `dshmarket` / `dsh-better-sidebar` / `@linxin666/dsh-client-ui-skill-explorer`）；patch 本体可以只有 3 行。
- **安装动作** = `dsh plugin --profile <p> add <pkg|link:...>`（CLI 自动写 profile 的 `dependencies` 与 `dsh.profile.bundles`）；`link:` 支持本仓免构建直挂。市场 catalog = `awesome-dsh-plugin`（社区目录宣称 4200+ 插件）。
- **skills 随包分发**机制：`skill-filesystem` 的 `customSkillDirs` 可指向 npm 包内 `skills/` 目录（官方内置技能即此装配）——发行物可自持技能，不必污染用户全局 skill root。
- **宿主自带 Python 3.12.14**（`runtime.json` + 目录实证；site-packages 为 office 栈：numpy / pandas / python-docx / openpyxl / Pillow / lxml / XlsxWriter，另含 pip 26.2.1；**无 mcp / pydantic**）。
- **`load_workspace_dependencies`**：官方工具（`@deepseek-ai/dsh-tool-workspace-dependencies`）——返回 bundled python / node / pnpm 的绝对路径与 pythonPackages；文档含构建器（`prepare:primary-runtime`）、`DSH_PRIMARY_RUNTIME` 环境变量（SDK / 容器场景）、Harness-home 安装与签名检查（Desktop 场景）。**它不在默认装配**（web / headless 合成树中未出现）——是场景化插件。
- 官方另有二进制分发模板（libreoffice-kit 一族：`optionalDependencies` + `os`/`cpu` 平台包 + `prebuilds.json` 哈希清单）。

### 2.2 跨生态先例（Web 调研）

- **Python MCP server 分发事实标准 = PyPI + uvx**（官方 servers README 推荐）——要求用户自备 uv；mcpb 规范 `server.type: "uv"`（宿主代管 uv）是「用户零装 Python」的官方蓝图，但依赖宿主实现。
- **VS Code + LSP**：宿主插件 = 「任意语言子进程 + JSON 协议」是 20 年成熟架构，非 hack。
- **兼容声明惯例**：VS Code `engines.vscode`（必填 semver）；Zotero「保守上限 + `updates.json` 事后放宽不重发包」——最值得抄，但等生态有正式覆盖协议再引入。
- **严格同构先例（非 Node runtime + 多入口产品接入 DSH）未发现**——本项目很可能是第一个；官方自带 Python/二进制的自用先例 = 默许空间存在，不违规。

## 3. Spike 实验记录（本机实证）

### 3.1 环境

- DSH 0.2.0-rc.2；宿主 Python 3.12.14（完整 CPython：**`venv` 模块与 pip 均可用**）。
- 沙盒：`.codebuddy/tmp/dsh_hostpy_spike/`（数据根 + `spike-ws` 工作区 + `venv-test`）。**真实数据零接触。**
- 握手客户端：jobws-mcp venv 的 MCP SDK（离线探针，不启动 DSH）。

### 3.2 实验一：PYTHONPATH 组合（复用现有依赖目录）

- 形态：宿主 python 跑 `-m jobws_mcp.server --workspace spike-ws`；PYTHONPATH = 仓库 `mcp/` + `jobws-core/src` + jobws-mcp venv 的 site-packages。
- 首跑失败：`ModuleNotFoundError: No module named 'pywintypes'`。**根因 = PYTHONPATH 注入不处理 site-packages 里的 `.pth`**（`pywin32.pth` 只在 site 机制下生效）——这是「手工拼接 PYTHONPATH」的通用坑。
- 修正（手工补 pywin32 的 `win32` / `win32/lib` / `pywin32_system32` 路径）后：
  - `initialize OK  server=jobws ver=0.1.0`
  - `tools/list OK  count=15`（14 只读 + 1 写入，注解正确读出）
  - `jobws.info OK`（`state=ok`、`source=env`、沙盒数据根——数据根诊断链路完整）

### 3.3 实验二：插件本地 venv（正式工程形态）

- **宿主 Python 创建 venv 成功**（`venv-test`，`sys.base_prefix` 指向宿主 Python）；`uv pip install` 向其安装 `mcp==2.2.0` 成功（连带 starlette / uvicorn / truststore 等）。
- 握手：command = venv 内的 python；PYTHONPATH 仅插件源码目录 → `initialize` / `tools/list` / `jobws.info` **全通过**。
- 意义：依赖隔离（不碰宿主 site-packages）+ 无 `.pth` 补丁，是发行物可直接采用的工程形态。

### 3.4 工程注意（给第二阶段）

- jobws-mcp 的依赖（mcp SDK / pydantic / httpx 等）**必须 vendored 到插件本地**（venv 或 payload）——宿主 Python 是 office 栈，不能假设它有。
- 手工 PYTHONPATH 拼接有 `.pth` / DLL 路径坑；**用 venv 形态规避**。
- stdio 协商的「探针 + 服务」双进程与 `--patch` 一次性纪律，此前的 D2 结论继续有效。

## 4. Verdict 详表（对齐 Go / No-Go）

| Go/No-Go 行 | 是否命中 | 说明 |
|---|---|---|
| 有正式第三方 API + 可隔离加载依赖 + MCP 全通过 | 否 | API 是「模型工具」级，非插件侧 API |
| Python 能跑，但只能靠私有路径 / 内部 API | **是（最接近）** | → No-Go for public release 作为唯一路线；开发 / 自用可用 |
| 必须向宿主 site-packages 安装依赖 | 否 | 两条隔离路线均通过 |
| DSH 更新后无兼容承诺 | 部分 | 工具契约有文档；写死路径无承诺 |
| host Python 不可访问 | 否 | 可访问且能力完整（venv / pip 可用） |
| uvx 需要用户自行安装 uv | — | 仅作为高级安装方式 |

**综合判定：INTERNAL-ONLY（技术 PASS / 契约未对第三方开放）。**

## 5. 决策与后续

### 5.1 发行物 runtime 路线（更新后的条件式排序）

1. **若 DSH 提供第三方 runtime 解析 API**（或 mcp-client 支持 runtime 别名）→ 宿主 Python 第一选择（发行物可压缩为轻量配置/技能包）。
2. **否则 → self-contained runtime / binary 第一选择**（官方 libreoffice-kit 模板）；宿主 Python 作为「探测到即用」的优化项（显式标注 INTERNAL-ONLY 风险，探测失败即回退）。
3. **uvx → 开发 / 高级用户渠道**，不作为普通用户默认安装路径。

### 5.2 技能场景的受支持路径

- 「模型调 `load_workspace_dependencies` 拿 Python → 跑 jobws CLI」= **技能驱动模式**，受工具契约覆盖（前提：该工具装配在目标 profile）。
- 与 MCP 工具面互补：MCP 走数据面（15 工具、两段式写入），技能 + CLI 走重活（PDF 生成等）。

### 5.3 与自用形态的关系

- 自用 / 开发形态可立即使用宿主 Python（本机路径 + 本地 venv），并可用 `link:` 免发布直挂（开发模式）。
- 公开发行随「自包含 runtime + bundle manifest」一起做（第二阶段），发布节奏与仓库同 tag 同步。

## 6. 未确认清单（不能拿来支撑决策的部分）

1. `!!js` 装配表达式能否程序化解析 runtime 路径（未实验）——若可，Q1 或可升级为「半公开」。
2. DSH 官方对第三方使用 bundled Python 的态度（无成文政策）——需向官方渠道确认。
3. `load_workspace_dependencies` 是否可被第三方技能/插件稳定依赖（装配条件、跨版本承诺未确认）。
4. DSH 升级对 `resources/runtime` 布局的兼容承诺（未见文档）。
5. `dsh-tool-workspace-dependencies` 的 JS API 是否公开导出（实现源码在 asar 内，未读）。
6. 二进制路线未实测（体积 / 杀软 / 签名影响待第二阶段评估）。

## 附录：实验器材

- 器材在 `.codebuddy/tmp/`（不入库）：`dsh_b_spike_search.py` / `dsh_b_spike_extract*.py`（asar 只读搜索）、`dsh_b_spike_handshake.py` / `dsh_b_spike_handshake_venv.py`（两种形态的 MCP 握手）、`dsh_hostpy_spike/`（沙盒数据根 + venv）。
- 复现要点：宿主 Python 路径 = `<dsh>/resources/runtime/primary-runtime/dependencies/python/python.exe`；握手客户端用 jobws-mcp venv 运行；全程离线、零 profile 改动。
