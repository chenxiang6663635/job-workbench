# 单一 canonical 数据根与历史工作区迁移（2026-10-04）

- 日期：2026-10-04 · 状态：已定稿（用户确认路线；六项决策随本 spec 冻结，实施从 A1 开始）
- 相关：[`decisions/single-canonical-data-root.md`](../decisions/single-canonical-data-root.md)（决策留档）、[`support-and-compatibility.md`](../support-and-compatibility.md)（兼容承诺）、[`data-flow-matrix.md`](../data-flow-matrix.md)（隐私底稿）、[`four-ends.md`](../four-ends.md)（四端契约）、[`glossary.md`](../glossary.md)（术语）、[`mcp-integration.md`](../mcp-integration.md)（宿主接入）
- 前置材料：[`research/report_agent-integration.md`](../research/report_agent-integration.md)（2026-09-10 的 dsh 插件解剖；本 spec 的宿主侧结论引用它）

## 〇、一句话

**同一台机器上，产品的不同调用端在「没有显式配置」时会解析到不同的数据根；这个机制已经真实产生过一次静默分叉。** 本 spec 把它当成**数据位置契约缺失**来收口：先建立唯一解析器与可见性（A），再做正式迁移事务（B），最后收缩危险的 legacy 默认（C'）。

## 一、问题

### 1.1 现状：两条互不知情的解析链

单一解析原语是 `packages/jobws-core/src/jobws_core/pathres.py:147-177` 的 `resolve_workspace_root()`，优先级是 **`JOBWS_DATA_DIR` → 便携（非 frozen 时可写即胜出；frozen 需 `portable.txt`）→ `user_data_dir()`**。但"传不传应用根"由各端自己决定：

| 端 | 注入点 | 默认结果 |
|---|---|---|
| Web 后端 | `web/backend/main.py:30` 注入仓库根 → `deps.py:21,45-51` | 非打包 → **便携＝仓库根** |
| CLI | `tools/jobws.py:69` 注入仓库根 → 同上 | 同上 |
| 桌面端（打包 NSIS） | frozen 且安装包**排除** `portable.txt` | **`%APPDATA%\job-workbench`** |
| **MCP** | `mcp/jobws_mcp/paths.py:40-41,59-71` **有意不传应用根** | **`%APPDATA%\job-workbench`** |

一句话：**源码形态的数据根是仓库，打包形态与 MCP 的数据根是用户目录。**

### 1.2 已发生的事故：一次 silent workspace fork

2026-10-04 只读盘点（脚本与 manifest 见对应 issue/PR；数字为该日快照）：

| | `%APPDATA%\job-workbench\personal` | 仓库 `personal/` |
|---|---|---|
| 文件数 / 体量 | 358 / 23.4 MB | 359 / 20.2 MB |
| 最后写入 | **2026-09-26 05:08（冻结）** | 现役（09-29 一轮 105 文件批量更新） |

差异分类与定性：

| 类别 | 数量 | 定性 |
|---|---|---|
| 仅 AppData 有 | 11 | **全部有对应物**：`99_归档/` 同名同字节 3 个（快照 zip `235277B`、事实卡 `8058B`、讨论纪要 `68627B`）、6 个被更新版取代的简历 PDF、1 个改名合并的岗位目录 → **无独有事实** |
| 仅仓库有 | 12 | 09-28/09-29 的新工作（面试复盘、面试记录、README） |
| 同路径不同大小 | 105 | 仓库侧更新更大（09-29 批量更新） |
| 同路径同大小、内容不同 | 1 | `03_面试准备/训练卡/项目表达/项目一/02_数据从哪里来，输入和标签是什么？.md`：差异是样本数口径（AppData「约 2.1 万」vs 仓库「约 2.0 万」）；仓库侧 `AGENTS.md:108` 与 `00_事实库/项目1事实卡_v0.1.md:25` 均记「2026-09-29 用户裁决：统一 **19,724 条 ≈ 约 2.0 万条**；原 21,372 / 2.1 万 一律废止」→ **AppData 侧为已废止旧口径，无独有语义** |
| `05_投递追踪/tracker.csv` | 两侧各 6 条数据行、同 17 列表头 | **记录集一致**（938B vs 1225B 只是字段填充差异） |

**定性：历史上发生过一次 default-root fork，但没有未合并的数据损失。** AppData 那份的准确定位是 **verified legacy snapshot**（保留备查，不做逐文件手工合并）。真正严重的是**机制仍然允许下一次分叉**。

### 1.3 最危险的形态：安装版「一切正常」

1. 开发态后端在 8765 上运行（数据根 = 仓库）
2. 安装版 Electron 启动 → 探到 8765 已被本服务占用 → **复用**
3. 用户看到**仓库那份最新数据**（因为复用的是开发后端）
4. 开发后端退出
5. 安装版自己拉起 frozen 后端 → 数据根 = `%APPDATA%` → **界面照常、无任何提示** → 用户开始读写 09-26 的旧副本

第 5 步的破坏性不在崩溃，而在 **everything looks healthy**：没有错误、没有红字、没有「你切换了工作区」的反馈。对个人数据产品，这比显式启动失败严重得多。

**这不是新问题**：CHANGELOG「Unreleased」里那条「修好『外部改动不再自动刷新』的静默失效（2026-09-26，#222）」正是同一条分叉的第一个症状——当时的归因原文就是「两者数据目录不同」。那次修的是**症状**，本 spec 收口的是**机制**。

### 1.4 为什么必须由产品堵，而不是「用户设个环境变量」

MCP 端**不可能**知道源码 checkout 在哪（它可能装在任意 venv / site-packages，见 `mcp/jobws_mcp/paths.py:2-23` 的既有解释，以及 `mcp/pyproject.toml:32-36` 的安装说明）。因此只要「默认根」依赖应用根，就**必然**存在至少一端解析不到同一答案。要让「无配置时四端同根」，默认根必须**不依赖应用根** —— 这是决策 6 的由来，也是把「非打包即便携」从默认降级为显式选择的原因。

## 二、目标与非目标

**目标**

1. 四端**只经同一个解析器**得到根，且**同一配置下结果逐字相同**（契约矩阵见附录 A）。
2. 用户可**持久化**选择数据根；选择一旦失效则 **fail-closed 且不静默回落**。
3. 机器上同时存在多个候选根时**产品主动告知**（诊断 + 界面），且破坏性操作在未解决歧义时被拒。
4. 迁移是**可续跑、可回滚、未经确认不移动也不丢弃数据**的事务。
5. 诊断对象单一化：CLI / API / MCP / 设置页**只做序列化与呈现**。

**非目标（本次明确不做）**

- 不改工作区内部布局（`personal/` 名字、目录结构、CSV 表头）——那是 `support-and-compatibility.md` §三 的领地。
- 不支持「一个进程多个数据根」，不支持按工作区分别选根。
- 不改快照根语义：仍在 `user_data_dir()/snapshots`，且**有意不跟随**便携/自选根（`pathres.py:180-193`）。
- **不新增** invocation 级数据根覆盖入口（理由见决策 1）。
- 不改宿主侧配置形态（DSH 等）；本 spec 只给出约束：**数据根不写入宿主配置**。

## 三、六项决策

每条格式：**取值 → 为什么 → 反面代价 → 怎么验收**。

### 决策 1：解析优先级

**取值**：`JOBWS_DATA_DIR`（环境变量） > **持久化选择** > legacy 默认（便携判定 / `user_data_dir()`）。

- **不新增 invocation 级覆盖**：实测全仓 `--data-dir|--data-root` **0 命中**，四端都没有这个入口。v1 不新造——多一个入口就多一维契约矩阵，而 env 已覆盖「临时换根」的全部诉求（测试隔离、spike、排障）。将来若要加，必须**四端同名同义**，且只能定位为诊断/迁移期开关。
- **相对路径一律拒绝**：现在 `pathres.py:164` 会对 env 值做 `os.path.abspath()`，相对值会**静默绑定到 cwd**——与「cwd 不该是隐式输入」直接冲突。env 与 persisted 都只接受绝对路径，否则 fail-fast。
- 空字符串视为未设置（保持现状 `.strip()` 语义）。
- **env 遮蔽 persisted 时必须可见**：诊断对象带 `source=env`，并在 `shadowed_by` 命中 persisted 时输出告警（四端一致）。
- **为什么不让 persisted 高于 env**：env 是唯一跨端可用的临时通道（`mcp/tests/test_stdio_smoke.py:61` 就用它做隔离）。让它输给一个文件，会造出「我明明设了变量却不生效」这类**新**静默 bug。**纪律用可见性治，不用优先级治。**
- **反面代价**：忘记清理的旧 env 会改变行为 → 由「启动可见 + doctor」兜住。
- **验收**：契约矩阵（附录 A）四端逐格一致；`doctor` 对 `env 遮蔽 persisted` 输出告警。

### 决策 2：持久化选择的位置与 schema

**取值**：`<user_data_dir>/state/data-root.json`（Windows：`%APPDATA%\job-workbench\state\data-root.json`）。

- **位置不依赖应用根**（决策 1.4 的决定论）。
- **不用 `config/` 这个名字**：本仓 `config/` 已专指**工作区领域配置**（`personal/config/directions|imap|provider`）；控制面再用同一个词会制造第二含义。`state/` 也为将来把 `zoom.json` / `window-state.json` / `reminders.json` 收进控制面留了位置。
- schema（最小、可版本化）：

```json
{
  "format": 1,
  "data_root": "<绝对路径>",
  "root_id": "<uuid>",
  "selected_at": "<ISO 时间>",
  "selected_by": "user|migration|cli",
  "migration_state": "idle",
  "schema_version": "<工作区数据语义版本>"
}
```

- 写入必须**原子**（临时文件 + 同目录 rename）；并显式承认「**不 fsync 即无崩溃耐久性**」（与宿主侧 `dsh-atomic-write` 同口径）——因此在**切换点**额外做一次落盘确认。
- 不写路径以外的机器相关字段（`root_id` 属于**数据身份**，路径属于**本机配置**；路径搬家后 `root_id` 不变，这正是"同一份数据搬了家"的唯一判据）。
- **反面代价**：多一个文件 = 多一处能坏；缓解 = 坏文件按「未设置」处理，且诊断里报 `persisted_read_error`。
- **验收**：断电/半写不产生坏 JSON（原子写）；`root_id` 随数据目录移动而保持。

### 决策 3：歧义行为（多候选根，且无 persisted）

**取值**：三档。

- **READ**：允许 + 显式告警（`state=ambiguous`，附候选清单与各自是否含同名工作区）
- **WRITE**：**不做一刀切禁止**（否则老用户升级后正常写操作会突然失败，违反兼容承诺）；写入结果里带 `state` 提示
- **DESTRUCTIVE**（删除类、迁移、覆盖恢复）：**拒绝**，除非用户在本次操作里显式确认目标根

**检测口径**：只对**已知候选**做 `stat`（persisted / env / `user_data_dir()` / 源码形态的应用根）；「像真实工作区」用现成信号——`<root>/<ws>/config/profile.md`、`05_投递追踪/tracker.csv`、有 `.jobws-root.json` 时比 `root_id`。**启动路径绝不做哈希**（哈希属于 doctor 与迁移）。

**已知盲区（必须写进 `mcp-integration.md`）**：MCP 只看得到它掌握的两个候选（env / `user_data_dir()`），看不到源码形态的应用根 → **MCP 的「无歧义」不等于全局无歧义**。

- **反面代价**：告警可能被用户忽略 → 告警必须上界面（设置页徽章 + 诊断包字段），不能只进日志。
- **验收**：人工造出「仓库 + APPDATA 两份 workspace」→ 四端都能报 `ambiguous`；破坏性操作被拒。

### 决策 4：失效选择行为（persisted 指向的根不存在或不可写）

**取值**：**fail-closed**，错误码 `sys.dataRootUnavailable`，**禁止静默回落**到便携或用户目录。

- **为什么**：静默回落 = 立刻再制造一次 fork（用户以为在读 A，实际在读 B）。
- 用户可走三条明路：修复磁盘/路径、**重选数据根**、显式清除选择——**这些补救命令必须在三态下都可用**（否则用户在失效态被锁死）。
- 与「未初始化」严格区分（见 §四）：根在、但工作区还没建 ≠ 失效；后者是**正常首启**，应走初始化流程而不是报错。
- **验收**：把 persisted 指向一个已删除的盘符 → 四端一致报 `sys.dataRootUnavailable`，且 `jobws data-root set/clear` 仍可用。

### 决策 5：迁移状态机与回滚

**取值**：`plan → copy → verify → switch → done failed`，`migration_state` 落在 `state/data-root.json`，**switch 是唯一生效点且最后写**。

- 纪律：**copy-first / switch-second / delete-never**（源目录在 `done` 之前**只读不删**；第一版完全不自动删）。
- **同卷也不能想当然**：同卷可用 rename 加速，但仍须「复制/暂存 → 校验 → 切换 → 旧目录保留一个观察期」的次序；不允许「先删后切」。
- 校验项（不只是字节）：清单 + 哈希；**工作区语义**（`tracker.csv` 主键集合与行数、`config/profile.md`、`config/directions/*.md` 数量、`config/imap.json`/`provider.json` 的凭据引用在新根可解析）；Windows 特有 preflight（跨卷空间、长路径、中文目录名、大小写、junction/symlink 一律拒绝）。
- 触发：**无歧义时自动**（唯一候选 + 目标已确认）；**有歧义时**走「清单预览 + 一键确认」——复用既有的**预览→确认协议形状**（与 `preview_*` → `apply_approval` 同构，但不是复用其工具）。
- **幂等**：`root_id` 已是当前值即跳过（跨版本重复升级安全）。
- 失败：任何阶段失败都不影响源目录可用；`state=failed` + 原因；下次启动可续跑或干净放弃。
- **验收**：迁移中途杀进程 → 下次启动能续跑或干净放弃；旧根始终可读；`root_id` 不变。

### 决策 6：新装默认位置

**取值**：新装默认根 = `<user_data_dir>/data`（Windows：`%APPDATA%\job-workbench\data`），工作区仍是 `<root>/personal`；**「非打包即便携（仓库即数据根）」从默认降级为显式选择**（env / persisted / `portable.txt` 或便携标记）。

- **为什么**：这是「无配置时四端同根」能成立的**前提**（见 1.4）——MCP 无法算出仓库位置，只有「不依赖应用根」的位置才是四端可共同计算的默认。
- `state/`（控制面）与 `snapshots/`（快照）**留在 `<user_data_dir>` 顶层**，不进 `data/`：控制面 / 领域数据 / 备份三者职责分离，也避免「备份与数据同处一地」。
- **Roaming vs Local**：v1 **保持 `user_data_dir()` 现有语义**（Windows = Roaming）——同时改「默认根」与「漫游语义」等于两次迁移。把「Roaming 会被域/漫游配置同步」登记为**已知风险**与复评条件（若出现多机同步冲突，或产品支持多机，再评估切 `LOCALAPPDATA`）。
- **验收**：全新安装（无 persisted、无 env）四端都解析到 `<user_data_dir>/data/personal`；源码形态默认不再是仓库。

## 四、三态与错误码

| 状态 | 定义 | 读 | 写 | 破坏性 | CLI 退出码 |
|---|---|---|---|---|---|
| `ok` | 解析成功且可写 | 允许 | 允许 | 允许 | 0 |
| `uninitialized` | 根在、工作区未建 | 允许（空集） | 允许（走初始化） | 允许 | 0 |
| `ambiguous` | 多候选且都存在真实工作区 | 允许 + 告警 | 允许 + 结果带 state | **拒绝**（需本次显式确认） | 0（带告警） |
| `unavailable` | persisted 指向不可用 | **拒绝** | **拒绝** | **拒绝** | 非零 |

错误码：`sys.dataRootUnavailable`（失效）、`sys.dataRootAmbiguous`（破坏性操作遇歧义）、`sys.dataRootUninitialized`（需显式初始化的动作）——与既有 `sys.unknownTarget`（`web/backend/routers/system.py`）同族。落地时按 `jwb-api-review` 补齐 `api_code` + `err.<code>` 中英双语 i18n 键（`lint four-ends` 会双向对账，缺一即红）。

## 五、诊断对象单一化

```
ResolvedDataRootDiagnostic
  path                 绝对路径
  source               env | persisted | legacy_portable | legacy_userdata
  form                 source_form | portable | packaged | mcp_only
                       （**刻意不叫 `mode`**：API 既有字段 `mode` 表示 portable/user 的解析结果，
                        同一个响应里出现两个"mode"会制造同名两义）
  state                ok | ambiguous | uninitialized | unavailable
  writable             bool
  root_id              数据根身份（来自根标记文件；缺省为 null）
  schema_version       工作区数据语义版本
  persisted_selection  { path, readable, shadowed_by } 或 null
  legacy_candidates    [{ path, has_workspace, root_id }]
  migration_state      idle | planned | copying | verifying | switching | failed
  workspace            当前工作区绝对路径
  snapshot_dir         快照根下该工作区的目录
```

呈现分工（**只做 presenter，禁止各算一份**）：

- **CLI**：新增 `jobws doctor`（现状只有 `jobws prefs doctor`，且只打印工作区路径，见 `tools/prefs.py:102-118`）
- **API**：扩展 `/api/system/paths`（`web/backend/routers/system.py:168-205`）——它已经是**单一事实源**（`routers/diagnostics.py:134-138` 显式复用它，注释写明"诊断包不该另算一份"），新增 `state` / `source` / `legacyCandidates` / `persistedSelection`
- **MCP**：新增 `jobws.info` 工具（现状**没有**任何 info/health 工具；版本只存在于 `_server_version()`，`mcp/jobws_mcp/server.py:26-35`）
- **桌面端**：设置页「数据位置」卡（`web/frontend/src/pages/Settings.tsx:167-212`）显示 root + source + state 徽章
- **不要把本机路径塞进 MCP `instructions`**：它会作为字面文本进入宿主系统提示词（既烧 token 也泄露本机路径）。仅在歧义时给一行提示，详情走 `jobws.info` 的结构化输出。

## 六、实施顺序与门禁

| 步 | 主题 | 关键判据 | 回滚 |
|---|---|---|---|
| A1 | 解析器收敛 + 诊断对象（**行为零变更**） | 先用 golden 测试锁死现有语义：`tests/test_domain_root.py`（3 条）、`tests/test_portability.py`（env > 便携 > userdata、快照不跟随便携）、`tests/test_ws_param_guard.py`（`?ws=` 全套）现有断言**全绿且不改** | 纯重构，回退分支即可 |
| A2 | 三态守卫 + 四端可见性（含 `jobws.info`） | 歧义/失效有错误码与中英 i18n；契约矩阵测试进 `lint four-ends` | 守卫可关，解析不变 |
| A3 | 持久化选择（`state/data-root.json` + 选择命令） | 原子写；坏文件按未设置处理；**仍不改任何默认** | 删文件即回到现状 |
| B1 | 迁移命令 + 状态机（`jobws data-root migrate`，默认 dry-run） | 断点续跑、幂等（`root_id`）、回滚演练 | 源目录未删 |
| B2 | 引导式迁移（无歧义自动 / 有歧义一键确认） | 升级夹具证明「不需手工搬文件」；复用预览→确认形状 | 同上 |
| B3 | 新装默认切到 `<user_data_dir>/data` + 便携降级为显式 | 全新安装与旧安装两条路径各有夹具 | 默认值可回；旧根未删 |
| C' | 收缩危险 legacy 默认（「非打包即便携」剩余语义） | 四端矩阵全绿 + 文档同步 | 由 A/B 铺垫，风险最低 |

每步：**一主题一分支一 PR**（`docs/<slug>` 或 `fix/<issue号>-<slug>`）、`CHANGELOG.md` 字节级插入、`tools/size_allowlist.txt` 只许变小、七个扫描器全绿；文档侧同步 `support-and-compatibility.md` 与 `glossary.md`。

## 七、风险与已知盲区

1. **MCP 看不到源码形态的应用根** → 它的「无歧义」是局部判断（必须写进 `mcp-integration.md`）。
2. **Roaming 同步**：域/漫游配置会把数据根放进同步范围（新一类分叉源）→ 登记为风险 + 复评条件（见决策 6）。
3. **跨卷迁移**（本机即为实例：仓库在 `D:`、`%APPDATA%` 在 `C:`）→ 需要空间与续跑；不能想当然当同卷处理。
4. **Windows 路径面**：长路径、中文目录名、大小写不敏感、junction/symlink——`web/backend/snapshot_entries.py:80-111` 的「先归一化再判定」是同族纪律，迁移必须复用同一套。
5. **索引类工具会记住旧路径**：`.gitnexus/`、`.codegraph/` 索引与宿主缓存不跟随根变化（换根后需重建）。
6. **观察期内两个历史根都在磁盘上**：任何「两个都像真的」的自动判断都禁止——必须用户确认。

## 八、兼容承诺的措辞（要落在 `support-and-compatibility.md`）

> **升级不需要你手工搬文件**——产品自己完成迁移；
> **并且在未经你确认前，不会移动、替换或丢弃任何数据**（迁移采用复制→校验→切换，旧目录保留一个观察期）。

第二句是新增的硬约束：它把「自动」从承诺里摘出去，同时把「不静默」立成原则。相应地：§三 增第 5 条（数据位置变更由产品完成）、§四「升级路径」增一行说明。

## 九、附录 A：契约矩阵

列 = 配置场景；行 = 形态；格 = 解析结果 · `source`。

| 形态 \ 场景 | 无配置 | 仅 env | 仅 persisted | env + persisted | persisted 失效 | 多候选（无 persisted） |
|---|---|---|---|---|---|---|
| 源码形态（checkout） | `user_data_dir()/data` · `legacy_userdata` | env · `env` | persisted · `persisted` | env（**告警遮蔽**）· `env` | **拒绝** · `unavailable` | 告警 + 需确认 · `ambiguous` |
| 便携标记形态 | 应用根 · `legacy_portable` | env · `env` | persisted · `persisted` | env（告警）· `env` | 拒绝 | 告警 |
| 打包 NSIS | `user_data_dir()/data` · `legacy_userdata` | env | persisted | env（告警） | 拒绝 | 告警 |
| MCP-only 安装 | `user_data_dir()/data` · `legacy_userdata` | env | persisted | env（告警） | 拒绝 | 仅两个候选（盲区） |

**注意**：B3 之前，源码形态「无配置」一格是**仓库根**（`legacy_portable`）——这是现行行为，也是本 spec 要改掉的那一格。

## 十、本次不做的

不做云端/多机同步；不做多根并存；不做按工作区选根；不改快照语义；不新增 invocation 覆盖；不动宿主侧配置。

## 十一、复评条件与待办

- **复评**：出现多机同步需求 / 用户报 Roaming 冲突 / 宿主（DSH 等）对「数据根查询」提出正式接口需求时，重审决策 6 与 §五 的呈现面。
- **本文发现的两处文档债**（随本次一并订正）：
  1. `support-and-compatibility.md:32` 仍写「凭证在工作区 `config/`」——**已过期**（#203 之后凭据在系统安全存储，工作区只留 reference）。
  2. `glossary.md` 需新增：canonical 数据根 / legacy 根 / 歧义 / 失效选择 / `root_id` / 三态。
