# G1 冻结记录（**已批准生效**，钉死 `4dd5364`，2026-10-19）

> **性质**：**已批准生效**（用户于 2026-10-19 批准）。G1「冻结」= ①停止向 `main`
> 合并功能改动 ②钉死候选 SHA ③转入 G2/G3 真机验收。
> **生效后纪律**：`main` 只接 G2/G3 暴露的**阻断类**修复；其余改动排队到下一个 `N`。
>
> 冻结的意义不是"做完了一切"，而是**"凡是要进这一版的，都已经在了"**——
> 之后只允许修复 G2/G3 暴露的阻断问题。

## 一、候选与范围

| 项 | 值 |
|---|---|
| **钉死 SHA** | **`4dd536497cc7974983d63ff304f5dbcecb3632f9`**（`main`，批准当日实测）——本记录自身的合并提交**不在**范围内，差异仅本文件 |
| 基线 | `v26.10.0`（2026-10-06） |
| 区间提交数 | **67**，**全部来自 PR**（直接推送 0 个——可复核：`git log --pretty=%s v26.10.0..HEAD` 每条都以 `(#N)` 结尾） |
| 版本号 | 仍 `26.10.0`（取号在 G3 落章时做，届时元数据变更后成品须重建重验） |

## 二、本版并入（按主题分组）

**安全与数据根**：#300（岗位读取三级归属 + 字节有界读）、#302（已生效迁移禁止指针式回滚）、
#305（反向迁移如实说明）、#307/#308（领域层读取与追加边界收口）、#311/#312（根解析按显式选择
分流，不再跨根回退）、#313/#314（CLI 默认工作区跟随持久化数据根）、#326（JD 抓取出网守卫）。

**门禁与 CI**：#294/#295（CodeQL 接入与站收尾）、#306（依赖审计两条命令都执行）、
#316（S4 门禁升级记录）、#317（CodeQL 不再按路径跳过 PR）、#327/#328（CodeQL 债务姿态与机制实测）。

**桶一（取号前小修）**：#287 —— 评分档位缝隙、插件回退、工作区校验、令牌簿记、`history.csv` 双保险。

**桶二（积累期主线）**：#288（测试盲区）、#289（读放大 + xdist，全量 45s→19s）、
#290（重复实现收编 + `tools_readonly` 拆分）。

**前端体验与可访问性**：#273（笔记搜索状态行）、#291（路由懒加载 / 长表窗口化 / 数据根重选入口 /
笔记插图端点）、#292（i18n 长尾 + skip-link）、#293（英文对照文档四件）、#303（笔记互链返回栈）。

**DSH 接入**：#281（npm 包化）、#282（随包 `jobws-mcp.exe`）、#283（一键安装 + 幂等迁移）、
#284（版本兼容声明与准入实测）、#285（parity 矩阵收口）、#286（接入页与支持策略）+ #324（exe 重建到 17 工具）。

**E 批筛选校准**：#318（ADR 三点决策）、#323（实现，四端同源）。

**设置页**：#280（凭据「清除即删」）。

**发布记录与文档**：#275–#279、#310（交接包纳管）。

## 三、明确不做 / 顺延（附理由，避免"以为漏了"）

| 项 | 处理 | 理由 |
|---|---|---|
| `26.10.1` hotfix | **不做** | 风险矩阵裁决：四条风险共同前提都是非默认布局、无实际事故；证据落在第二档（tag 树实测完成、安装包未复核），签署条件已写 4 条 |
| E-03「放掉记账」写入口 | 顺延 | 本批只读；写入口需单独立项（设计文档 §四 反目标） |
| CodeQL 存量（**基线读数 2026-10-18**：184 条） | 12 条非路径告警已根因修复；182 条 path-injection 已分诊、不逐条改 | #331–#335 修完 ReDoS / URL 判定 / stack-trace（194→184，实测关闭）；#338 分诊；#339 实测发现 `resolve_profile` 的 domain 可穿越并修掉 |
| #325（#194 修复） | **已合并**（`60a366d`，2026-10-19；#194 告警自动转 `fixed`） | 已补三处链接边界负向测试；CodeQL 对该 PR 报 **0 new alerts**（`unsafe_links` 被识别为 SafeAccessCheck），不再需要 dismissal 或 QL 包 |
| P1-B ②③（反向迁移） | 不做，如实说明 | #305：技术上当前不可行，写在文档里而不是假装有 |
| 全站 WCAG AA 专项 | 延后 | 按审计建议：避免 a11y 收口无限扩张（最小键盘可达性已闭环） |

## 四、验证读数（2026-10-18 当前 main）

| 项 | 读数 |
|---|---|
| 主套件（本地） | **2036 passed / 37 skipped**（17.1s，`-n 4`）——37 skip 是本机 Windows 建不了文件符号链接；这些用例在 CI 上真实执行 |
| CI（`main` @ 钉死 SHA） | **pytest 2061 passed / 12 skipped**（22.2s）；前端 **228 passed / 26 文件**；E2E 冒烟 **68 passed** |
| MCP 套件 | **101 passed / 10 skipped**（4.7s，MCP venv） |
| 扫描器 | i18n / size / four-ends / legacy-imports / ui-tokens / themes（10 套）/ domains（2 个）**全部通过**；另 `skills check` 9/0、`assets_registry --check` OK |
| MCP 工具面 | **17 个**（冒烟钉住数量 + 末位 `score_calibration` + 真调两个后补工具） |
| 随包 exe | `prebuilds.json` **211 条**，逐文件 sha256 复核 0 不符 / 0 多余 |
| npm 预检（2026-10-19，`npm pack --dry-run`） | 子包 **213 文件 / 解包 41.9 MB / tarball 20.3 MB**（含 `prebuilds.json` + `bin/jobws-mcp.exe`）；主包 **233 文件 / 42.0 MB / 20.34 MB**（含 `cordis.patch.yml`、9 个技能目录、`scripts/install.ps1`、`locale/*.json`、`platform/**` 含 exe、`README.md`、`icon.svg`）；两包 `repository` 均指回本仓库、`license=MIT`、未设 `private` |
| 门禁 | S1–S4 生效中；本区间 **0 次直接推送 main**（67 个提交全部以 `(#N)` 结尾） |
| code scanning | open **183**（`py/path-injection` 182 + `py/full-ssrf` 1）——**这是本文的权威读数**（测得 2026-10-19，`4dd5364` 之后含 #347 的 `#239`）；其余段落里的 184 / 182 是**更早时点**的历史读数，已逐个标时点 |

## 五、冻结后要你执行的四件事（G2/G3，须在场）

1. **干净环境构建**（从候选 SHA 全新构建后端/前端/桌面端，确认无本地残留依赖）；
2. **Windows 真机安装 / 卸载 / 升级**（本机两次被 UAC 交互阻断，无法无交互完成）；
3. **`v26.10.0` 隔离安装探针**三场景 —— **P2 错根写** / **S2 越界** / **env→不存在的根**
   （用临时目录、不碰真实数据）；结果回填风险矩阵，其裁决由"暂定"转"正式"；
4. **回滚演练**（安装 → 回滚到上一版 → 数据完好）。

## 六、挂起项与它的代价（说明为什么冻结不受影响）

**#325（CodeQL #194 命令行注入修复）——已合并（2026-10-19，`60a366d`）**。合并后实测：`#194` 告警状态转 **`fixed`**，`py/command-line-injection` 归零；`tools/pdf_print.py` 在 main 上产生 **0 条新告警**。以下为合并前的挂起经过，保留备查：分支 `fix/command-line-injection` 除 CodeQL 门禁外全绿
（2006 passed 时的那次运行），PR 分析里 `py/command-line-injection` **已 0 条**——说明修复有效；
但新文件的 4 处"写用户自选输出路径"被判 `py/path-injection`（high），门禁按"新增"拦下。

- **不做 `paths-ignore`**：它关掉的是该文件**全部**规则，包括刚修好的那条；
- **不做 QL 概念包**：Python 的扩展点是 `Path::SafeAccessCheck::Range`（带状态机），不是加个类名；
  且需 fork/打补丁标准库包，长期维护负担 > 收益；
- **风险现状**：`tools/pdf_print.py` 的 argv 只剩候选表字面量与临时固定名，**当前不可利用**。

→ 因此它**不构成冻结阻断**：主干上不存在这个缺陷（缺陷只在旧版 exe 的构建里，而 exe 已重建）。

## 六之二、CodeQL 现状（2026-10-19）

| 项 | 状态 |
|---|---|
| open 告警总数 | **184**（**#325 合并前**读数；基线 194，12 条非路径告警已根因修复并实测关闭）——最新值看 §一 的 183 |
| `py/stack-trace-exposure` | **0**（5 条全收，#332–#335；三级源头：路由层 / `dataroot_migrate` / `dataroot_semantics`） |
| `py/polynomial-redos` | **0**（3 条；20k 空白 3.78s → 0.11s，性能用例钉住） |
| URL 子串判定（py+js） | **0**（2 条；改主机名相等，收进 `outbound.host_is`） |
| `py/full-ssrf` #2 | 代码已修并合并（#326）；告警 open（不认自定义校验器） |
| `py/command-line-injection` #194 | **已关闭（`fixed`）**——#325 于 2026-10-19 合并后自动置 fixed |
| `py/path-injection` | **182** 条：181 条存量 + **1 条新（`#239`，`tools/pdf_print.py:164`）**；存量已分诊（`report_path_injection_triage.md`），按策略不逐条改 |
| `#239`（本次唯一新增） | 2026-10-19 07:57 由 **#347** 引入。落点是 `os.path.islink()`——**一个检查，不是文件读写**；同一调用在 #325 里未被报，是 #347 改动了那个循环体后被重新归因。**如实记账，不当作已豁免**：G2/G3 之后若要清零，手段是把这个 `islink` 调用合并回单一遍历（去掉重复调用点），不是 dismiss |

**#325 为什么从 BLOCKED 变成 CLEAR**（实测确认，非偶然）：新增的

> **22 条候选的姿态（2026-10-19 审计纠正）**：`path_injection_candidates.md` 里那 22 条是
> "具备进一步复核价值"的集合，**不是**已证明安全的误报；属既有安全债务。**不阻塞** G2/G3
> 发行验收，也**不批量 dismiss**——先由维护侧补足 source→sink 证据，人工批准发生在有证据
> 之后，不用维护者的勾选代替技术审计。
`pdf_print.unsafe_links()` 在**任何文件操作之前**逐个检查输入路径（`islink` / `isjunction` /
递归 `os.walk`），命中即 `return False` —— CodeQL 的 path-injection 有 `SafeAccessCheck`
概念，把它识别成合法 barrier。为排除"分析没覆盖到"的假阴性，特意**碰了一次该文件**
强制重新分析：仍是 `0 new alerts`。这是结构性修复被识别，不是抑制。

**合并后核对（#325 合并当时，2026-10-19）**：open 告警 184 → **182**（`py/path-injection` 182→181、`py/command-line-injection` 1→0）；main 上 `tools/pdf_print.py` **0 条新告警**。

## 七、复现命令（任何人接手都能重跑）
---

## 八、冻结例外：#357 首次使用自动初始化（2026-10-19 批准）

> **本节只追加，不改写上文**。原钉死 SHA `4dd5364` 的历史记录保持原样；本节记录
> 冻结生效后**唯一一次**经批准的产品代码例外，以及它带来的候选 SHA 变更。

### 8.1 为什么算阻断（而不是"顺手改进"）

npm 独立安装是**本版新增的发布形态**，而当时的产物上：`<数据根>/personal` 不存在时
MCP server 直接退出、**17 个工具一个都不注册**——"装着就能用"只对"装过桌面版"的机器
成立。这推翻的是该形态的核心承诺，属**发行阻断**，不是功能增强。

### 8.2 改了哪些文件

| 文件 | 改动 |
|---|---|
| `mcp/jobws_mcp/init_workspace.py` | **新增**：模板定位 + 铺骨架 + `ensure_workspace`（默认根缺失才自动建） |
| `mcp/jobws_mcp/server.py` | 新增 `--init` 入口；启动改走 `ensure_workspace` |
| `mcp/jobws_mcp/paths.py` | 报错文案改为指向 `--init` |
| `mcp/tests/test_init_workspace.py` | **新增** 8 条（先红后绿 + 反作弊） |
| `integrations/dsh/scripts/install.ps1` | 步骤 4：装完自动跑一次 `--init`（找不到 exe 只警告） |
| `integrations/dsh/README.md` / `docs/release-checklist.md` | §一 改"脚本做五件事"；§五 加「首次使用必须有工作区」；构建必须用 `pwsh 7` |
| `integrations/dsh/platform/win32-x64/{bin/**, prebuilds.json}` | 重建产物（exe 哈希随之变化） |
| `CHANGELOG.md` / `docs/handover/2026-10-19-g2g3-runbook.md` | 记账 + 判据更新 |

### 8.3 验证证据（合并前实测）

- 新测试 **8 条**；反作弊：把"缺失则自动建"改成"永不建" → 对应用例**变红**（已还原）
- MCP 套件 **109 passed / 10 skipped**；主套件 **2036 passed / 37 skipped**
- **打包形态**：重建 exe 后 `--init` 铺出 **14 个文件 / 6 个模块**
- **端到端**：覆盖 `APPDATA` 到干净目录、不设 `JOBWS_DATA_DIR` → 首次启动自动建工作区并注册 **17 个工具**
- exe 冒烟 `SMOKE OK`（17 工具 / 3 资源 / 2 模板 / 两处越界拒绝正常）

### 8.4 对数据根协议的影响：**不变**（关键，别被"自动"二字误导）

| 场景 | 行为 | 实测 |
|---|---|---|
| 未设 `JOBWS_DATA_DIR`，默认根缺 `personal` | **自动建**空骨架 + stderr 说明 | ✅ |
| **显式** `JOBWS_DATA_DIR` 指向不存在的根 | **仍然报错**，退出码 2 | ✅ 实测 exit 2，且**未静默建目录** |
| 已有工作区 | 原样返回，不覆盖 | ✅ |
| 重复 `--init` | 幂等，文件哈希不变 | ✅ |

即：只新增"默认根 + 缺失"这一条；`env → 不存在的根` 的 **fail-closed 行为原样保留**
（§四 探针 C 仍按 503 / 404 判据验收，不因本例外改变）。

### 8.5 候选 SHA 规则（本节是权威）

- **当前发行候选 = `6b52a88`**（含 #357 及其后的治理文档提交）。
- 判据：`git log --oneline 4dd5364..6b52a88 -- "*.py" "*.ts" "*.tsx" "*.json" "*.yml"`
  应**只列出 #357 一个**；`git diff --name-only 6b52a88..HEAD -- <同上>` 应为空。
- **若发行前再要加阻断修复**：先更新本节（原因/文件/证据/新候选 SHA），再重跑 G2/G3 §二，
  **不得默默替换候选**。

---

## 九、冻结例外 #2：certifi 安全修复 #369（2026-10-21 批准）

> **本节只追加，不改写上文**（含 §八及其 §8.5 的 `6b52a88` 候选规则——那是当时的有效记录）。
> 本节记录冻结生效后**第二次**经批准的安全例外及其候选 SHA 变更。

### 9.1 候选演变（追加式链）

| 阶段 | SHA | 说明 |
|---|---|---|
| 原始 G1 钉死 | `4dd536497cc7974983d63ff304f5dbcecb3632f9` | §一 / §八 |
| 例外 #1 后候选 | `6b52a8827945d4aaee593d34b97afa4d79b790f5` | §八（#357 自动初始化） |
| **例外 #2 后候选（当前）** | **`fc2ad96c86cb2b62f0e85d4fb37d8568356558fd`** | 本节（#369 certifi） |

### 9.2 为什么算阻断（而不是"依赖日常维护"）

PYSEC-2026-4320 / GHSA-6q48-6c7w-9gw2：certifi 捆绑的 emSign 根 CA 所用**中间 CA 密钥泄露**
（CVSS v4 9.1 Critical，VC:H/VI:H；影响 `>=2019.03.09, <2026.10.19`）。pip-audit 漏洞库
**2026-10-20 21:41** 收录该记录后，CI「安全扫描（依赖 audit）」（**required check**，
`enforce_admins: true`）由绿转红，**阻塞一切 PR 合并**（含 #368 文档 PR）。项目出站 TLS
（邮件同步 / JD 抓取）经 certifi 校验信任链，属**已公开的安全事件 + 发行门禁机械拦截**，
不是版本偏好。

### 9.3 改了哪些文件（受控差异，零业务代码）

| 文件 | 改动 |
|---|---|
| `web/backend/requirements.lock` | `certifi==2026.7.22` → `certifi==2026.10.19` + 两个 PyPI 权威 digest（wheel `42d35340…` / sdist `035c1e85…`，结构不变） |
| `web/backend/requirements.txt` | 下界 `certifi>=2026.7.22` → `certifi>=2026.10.19`（收紧第二入口：dev 链经 `-r requirements.txt` 引入、CI 后端 exe 构建亦用该文件；旧下界在镜像滞后场景仍允许解析到受影响版本） |

> 差异核查口径：本条例外改的是 `.lock` / `.txt`，**不适用** §8.5 的 `*.py *.ts *.tsx *.json *.yml`
> 检查式；本次受控差异 = 上述两文件、共 +4/-4 行，合并时已独立核对（PR #369，squash 单父提交）。

### 9.4 验证证据（合并前 / 合并后）

- **漏洞事实**：OSV 记录 published 2026-10-20 21:41；受影响区间与修复版与 GitHub Advisory 一致
- **CA 内容实证**：certifi 2026.7.22 的 `cacert.pem` SHA256 = `9cc2a774b5198dcf…`（121 证书，
  含 `emSign ECC Root CA - G3`）；2026.10.19 = `50f79f98dac192b2…`（120 证书，**移除 G3**，
  其余序列号不变）
- **CI**：#369 10/10 success（含依赖 audit `No known vulnerabilities found`）；合并后 main
  CI + CodeQL success、**E2E 全量 132/132 真实执行**
- **本地**：pip-audit 对 2026.10.19 零告警；候选 venv 全量测试 **2036 passed / 37 skipped / 0 failed**
- **供应链**：构建工具 uv 同步更新至 0.13.4（GHSA-hq85-5cpj-mr62，同 emSign 事件影响 uv 内置信任库）

### 9.5 重建范围（已执行）

从 `fc2ad96` 全新克隆（SHA 断言逐位一致）重跑 §二 并重建 B 组：新 exe
`c77d0e73710844b927d849eeb2fc5502a8e9a93541c8798eb10a1706bafdd27d`（138,137,065 B），
四重互核全过；**frozen 后端随包 `cacert.pem` 实测 `50f79f98…`（G3 零残留）**；Frozen 冒烟
三前提通过（双隔离 + 独立端口 8799 + 真实用户目录前后指纹 606→606 零变化）。
旧 B 组（`c7f26746…`，自 `6b52a88` 构建）标记 **SUPERSEDED**，原文件与哈希保留。

### 9.6 未结案声明（本例外**不**声明全部完成）

**本例外只修复桌面后端依赖路径。** 以下三项独立于本例外，未随 #369 完成：

1. **DSH MCP 分发链的 manifest 仍声明旧 CA 清单**：`integrations/dsh/platform/win32-x64/prebuilds.json`
   登记的 `bin/_internal/certifi/cacert.pem` 哈希 `9cc2a774…` 与 certifi 2026.7.22（受影响版）
   **逐位一致**。**证据边界**：已独立核实的是**受控预构建 manifest**；实际 MCP EXE 与 npm
   tarball 仍需逐文件回读（`bin/` 未纳入 Git 源码树）。该分发路径的修复（重建 MCP EXE +
   更新 prebuilds + npm pack 内容核验 + 17 工具冒烟）须作为**独立的安全变更**另行申请
   G1 例外，**不在本例外范围**，亦不得在纯文档 PR 中夹带二进制改动。
2. **已发布 `v26.10.0` 的旧版安全风险**：独立 Hotfix 裁决（旧版安装包实际 CA 清单 + TLS
   回退路径可达性 + 系统信任库层），不与发行动作捆绑。
3. **系统信任库**：更新随包 certifi ≠ 清除操作系统层对受影响链的信任——按部署环境评估
   （归入第 2 项）。

### 9.7 候选 SHA 规则（本条生效后）

- **当前发行候选 = `fc2ad96`**（= `aee9c263` + #369 两依赖文件修复；`aee9c263` 是 #369 合并前的实际主线）。
- **单次安全例外的差异判据**（勿用候选链区间——那会混入其间的治理提交）：
  `git show --format= --name-only fc2ad96` 与 `git diff --name-only aee9c263..fc2ad96`
  都应**只有两行**：`web/backend/requirements.lock` 与 `web/backend/requirements.txt`。
- **候选演变 ≠ 单次补丁审查**：`6b52a88..fc2ad96` 实为 **9 个提交 / 7 个文件**
  （#360–#367 八个治理文档提交 + #369）——那是候选链的历史跨度，**不是**本例外批准的改动面。
- 后续若再加阻断修复：按 §8.5 同款纪律——先更新本节（或新增 §十），再重跑 §二，
  **不得默默替换候选**。




## 历史附录：G1 批准当日的复现命令（2026-10-19，`cd464e0` 时点）

> **勿对当前候选执行**——`cd464e0` 是 G1 批准当日的旧候选；当前候选为 `fc2ad96`（见 §九）。
> 保留原文是为可复现当时的验证读数，不是现行操作步骤。

```powershell
git checkout cd464e0
python -m pytest tests/ -q -p no:cacheprovider -n 4        # 2001 passed
D:\tools\venvs\jobws-mcp\Scripts\python.exe -m pytest mcp/tests -q   # 101 passed
python tools/jobws.py lint i18n,size,four-ends,legacy-imports,ui-tokens,themes,domains
D:\tools\venvs\jobws-mcp\Scripts\python.exe scripts\smoke_mcp_exe.py # 17 工具 + SMOKE OK
```

## 十、冻结例外 #3：DSH 插件 MCP 运行时证书安全修复（2026-10-21 批准并合并）

### 10.1 为什么算阻断（G3 P0，不是 G4 普通核验）

DSH 插件（产品对 DSH 的交付单位）的 **MCP 运行时组件**用**独立构建 venv**，不受桌面
`requirements.lock` 约束。实测该 venv `certifi 2026.7.22`（PYSEC-2026-4320 受影响版），
`integrations/dsh/platform/win32-x64/prebuilds.json` 登记的 `bin/_internal/certifi/cacert.pem`
= `9cc2a774…` 与之**逐位一致**。旧构建脚本的 pip 安装行无版本下界 → 镜像滞后或旧 venv 复用
会静默打出受影响 CA。不能带已知受影响清单进入新的正式分发。

### 10.2 实际改动（8 文件：3 新增 + 5 修改，零业务代码）

| 文件 | 类型 | 改动 |
|---|---|---|
| `scripts/build_mcp_exe.ps1` | 修改 | certifi 下界 fail-fast、产物 PEM 硬门禁（无 G3 + SHA=基线）、失败产物失效保护（`.stale`）、PEP 610 editable 检测、UTF-8 BOM |
| `scripts/smoke_mcp_exe.py` | 修改 | 双隔离、realpath 精确断言、exit 2 精确断言、真默认启动自动初始化、超时自检 |
| `integrations/dsh/platform/win32-x64/prebuilds.json` | 修改 | 重建：`cacert` `9cc2a774…` → `50f79f98…`，215 文件 |
| `integrations/dsh/package.json` | 修改 | 加 `scripts.prepack`（校验内嵌副本） |
| `integrations/dsh/platform/win32-x64/package.json` | 修改 | 加 `scripts.prepack`（校验本包） |
| `scripts/mcp_smoke_support.py` | 新增 | StdioPipe 真实超时 + 隔离环境 + peek_stderr 非阻塞 + check_pipe_timeout |
| `scripts/verify_mcp_prebuilds.py` | 新增 | pack 前置闸（Python 版） |
| `scripts/verify_mcp_prebuilds.js` | 新增 | **prepack 门禁（Node 版）**——`npm pack` / `publish` 自动执行 |

### 10.3 合并身份与门禁

- PR **#370**，Head `e6ca5ba3512b2663c24b3b2f1639af1a182363ee` → Squash 合并；
- 合并后 **main = `7c248405a731c656f3d44523542670fb0a6fa7e8`**；
- main CI `39598705022` **success（4m52s，含全量 E2E）**；CodeQL `39598705137` success（2m5s）。

### 10.4 验证证据（本地 + 打包命令级）

- 构建环境：certifi 2026.10.19 / pip **26.2.2** / PyInstaller 6.22.3 / mcp 2.3.0 / Python 3.12.8；
- 产物 PEM `50F79F98…`、G3 零残留；prebuilds **215 文件全量核验 0 不符 0 缺失**；
- **门禁接入 npm 生命周期**：两包 `prepack` 自动执行；四种负向（`.stale` / 未登记文件 /
  缺 PEM / 篡改 DLL）+ **只改版本不重建**均使 `npm pack` 失败（`npm error code 1`）；
- 冒烟：17 工具 / 3 资源 / 2 模板 / 两工具行为 + 隔离精确断言 + 缺根 exit2 + 真自动初始化 + 越界 exit2 + 超时自检；
- npm 双包解包：各 **215 文件 0 不符 0 缺失**、PEM `50f79f98…`、G3 为 0；
- 非预期变更：9 skills / preset / install.ps1 / 版本号 **零改动**；旧构建工具版本未留档（证据缺口）。

### 10.5 Desktop B 组范围化重建豁免（已批准）

- B 组真实来源 `fc2ad96`，SHA256 `c77d0e73710844b927d849eeb2fc5502a8e9a93541c8798eb10a1706bafdd27d`，
  **不得改写、不得表述为由本例外合并后的 SHA 构建**；
- 可用于 G2 真实 NSIS 安装 / 证书回读 / 数据根 / 升级回滚验收；
- **豁免生效条件**：本例外净差异不触及 Desktop 构建输入（8 文件均在 `scripts/` 与
  `integrations/dsh/`，不触及）——已满足；
- 新候选仍须完整自动化回归；**G4 后 C 组必须从最终源码完整重建**；
- 该项是**重建步骤豁免，不是 G2 测试豁免**。

### 10.6 未结案（不得因本例外关闭）

1. **G3 真实 DSH 安装验收**：npm 双包构建/校验通过 ≠ 真实安装、17 工具、9 Skills、Preset 验收通过；
2. **5b PDF（G3 阻断）**：修复 PR #371（`jwb-resume` 边界段）待隔离 DSH 按原语义复跑；
3. **`26.10.1` Desktop 安全 Hotfix**：**已获路线授权**（一次性政策例外，B 路线），
   正式政策文件**待独立入库**（入库后在本节补准确路径）；发布前官网同步 P0 未关闭；
4. **G4/G5**：未授权。

## 十一、冻结例外 #4：pypdf 依赖安全修复（2026-10-22 批准并合并）

### 11.1 为什么算阻断（跨 Desktop G2 / Hotfix 的发行安全 P0）

pypdf==6.19.0 被新披露 5 个 CVE（2026-113786 / 113792 / 113793 / 113794 / 113795），
main CI 的 **pip-audit 必需检查失败**（run `39723447801`）。pypdf 有两条实际业务调用路径：
`web/backend/resume_import.py`（`PdfReader` 读用户导入的 PDF）与 `tools/resume_build.py`
（文本提取 / A4 纸型 / ATS 校验）。

**风险边界（不夸大）**：五个 CVE 的 CVSS 4.0 均为**可用性影响**（`VA:L`/`VA:H`），机密性/
完整性为 `N`；未证明五者在本项目全部可达（部分依赖可选组件或特定解析路径）；**无已发生攻击证据**。
P0 依据 = 公开依赖风险 + 实际 PDF 输入面 + 现行必需检查失败。

### 11.2 受控差异（2 文件 +4/-4）

| 文件 | 改动 |
|---|---|
| `web/backend/requirements.txt` | `pypdf>=6.19.0` → `>=6.21.2` |
| `web/backend/requirements.lock` | pypdf 块 `6.19.0` → `6.21.2` + 两官方 sha256（wheel `1d44d1a3…` / sdist `0a3e1c5c…`） |

**零漂移校验**：uv 重新编译并以「现有 lock（去掉 pypdf）」为约束比对——22 包**零新增零删除**，
仅 pypdf 变化。uv 0.13.4 的 `# via` 多行格式与旧 lock（0.12.5 生成）不同，采用最小替换避免 44 行无关噪音。

### 11.3 合并身份

- PR **#375**，Head `e72f11db85ca09dd96bb84afb7be9c40bf282f63` → Squash 合并；
- 合并后 **main = `9d733b4bb836c477d228c2a545ea6fd67a0461dc`**；
- main CI `39731924847` **success（4m31s）**；CodeQL `39731924846` success（3m9s）——pip-audit 恢复绿。

### 11.4 验证证据

- `pip-audit`：**No known vulnerabilities found**（本地 + CI 双证）；
- PDF 定向回归 **44 passed / 4 skipped**（resume api / cli lock / pdf argv / templates / tmp prefix /
  pdf link boundary / mirror budget / mirror scope / error message hygiene）；
- 全量 **2047 passed / 37 skipped / 0 failed**（CI 侧 2072 passed / 12 skipped，总数一致、跳过条件不同）；
- Frozen 后端重建（35.5 MB）+ 冒烟通过（health ok、`/api/system/check` 实际执行 tools 代码）。

**证据边界**：Frozen 内 pypdf 版本在 PYZ 归档中不可直读，版本由构建 venv（6.21.2）决定；
真实 PDF 导入 / ATS 需在安装验收中用测试 PDF 最终确认。

### 11.5 Desktop B 组资格变化（本例外的主要影响）

pypdf 是 **Desktop Frozen 后端的运行依赖**，触及 Desktop 构建输入 → **旧 B 组直接复用资格失效**：

| 对象 | 处理 |
|---|---|
| 旧 B 组 `fc2ad96` / `c77d0e73…` | 保留文件、哈希与构建日志为**历史证据**，不改写 |
| §十 10.5 的 DSH 范围化豁免 | 保留为**历史决定**（当时净差异确实不触及 Desktop 输入） |
| pypdf 修复后的新候选 | 需从新候选 SHA（`9d733b4b`）**重建 Desktop B 组**并执行 G2 验收 |
| 已完成的测试证据 | 可作对照，不得冒充新候选验收 |
| G4 后 C 组 | 仍须从最终源码完整重建 |

> 这是**新安全例外导致的重建要求**，不是推翻 §十 的历史裁决。

### 11.6 未结案

1. **`26.10.1` Hotfix**：一次性政策例外（PR #374）待合并签署；Hotfix 已含 certifi + pypdf 两项，
   新 dry-run `39733251853` success（`f90a94e`）；真实安装升级验收与发布授权未做；
2. **5b PDF**：PR #371 待隔离 DSH 复跑；
3. **G2 Desktop**：从 `9d733b4b` 重建的新 B 组完成后，执行真实 NSIS 安装、安装目录 PEM 回读、
   PDF 导入与数据/快照验收——**新 B 组是 G2 的前置**；
4. **G3 DSH 插件**：使用 MCP EXE / npm 双包 / Skills / Preset 独立验收，**不依赖** Desktop 新 B 组；
5. **G4/G5**：未授权。