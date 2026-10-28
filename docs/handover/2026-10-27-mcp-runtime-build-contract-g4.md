# MCP 运行时构建合同（G4 前置设计稿）

> **性质**：设计稿，不是执行记录。**本文件不声称任何一项已通过**——它把「26.11.0 落章时该怎么做、按什么判、失败怎么办」写成可照单执行的形态。
> 依据：`scripts/build_mcp_exe.ps1`、`scripts/check_mcp_build_environment.py`、`scripts/mcp_prebuilds.py`、`scripts/verify_mcp_prebuilds.py` 的**当前 HEAD 实现**（`5703873`）。
> 前序：`docs/handover/2026-10-27-mcp-build-lock-contract.md`（v1 合同，已合并）。

## 一、范围与明确不承诺

| 覆盖 | 不覆盖 |
|---|---|
| `jobws-mcp.exe` + onedir `bin/` 运行时 | **Electron/NSIS 安装包** |
| 平台子包 `integrations/dsh/platform/win32-x64/` | npm registry 上的发布状态 |
| `prebuilds.json` 清单与其校验 | 跨机器可比性（未验证，不承诺） |
| 双 tarball（主包 + 平台子包） | 主包 `platform/` fallback 的取舍（有意保留） |

关于 NSIS 的准确表述：**本轮可复现性合同仅适用于 MCP 运行时，不覆盖 Electron/NSIS 安装包。当前 NSIS 构建流程不保证字节级复现；未来是否实现属于另一项独立工程目标。**

## 二、四级证据的当前状态（2026-10-27）

| 等级 | 状态 | 依据 |
|---|---|---|
| `LOCK_CONTENT_VALIDATED` | ✅ | PR #418：37 包闭包比对，519 个 hash，`.in`≡`.lock` 有测试 |
| `HASH_INSTALL_TESTED` | ✅ | PR #418：干净 venv `--require-hashes` → exit 0，38 包（37 + pip），certifi=2026.10.19 |
| `DECLARATIVE_BUILD_ENV_READY` | ✅ | `-FromLock` 已实现并实测：全新 venv + 按锁装 + `--no-build-isolation` + wheel 候选断言 |
| `REPRODUCIBILITY_EVALUATED` | ✅ | 四轮比对（§5.2b）：三个根因逐个消除 |
| **`REPRODUCIBILITY_PASS`** | ✅（**有边界**） | 227/227 文件逐字节一致；边界见 §5.2b——同机同路径，跨机器未证明 |

> 上一行那个"有边界"不是谦辞：跨机器仍会因 venv 路径不同而不同（`Scripts/*.exe` 内嵌绝对路径、
> `RECORD` 记录其哈希）。把构建路径相对路径化属独立工程目标，不在本轮。

## 三、当前构建链实际做了什么（逐段核对）

`build_mcp_exe.ps1`（232 行）在 HEAD 上的真实顺序：

| 行 | 动作 | 性质 |
|---|---|---|
| 64 | `import PyInstaller, mcp, mcp_types, jobws_core, jobws_mcp` + `sys.version_info >= (3,12)` | 环境存在性 |
| 82–98 | certifi 版本下界 `2026.10.19` + 随包 PEM SHA `50F79F98…` | **安全门禁** |
| 105–139 | 调用 `check_mcp_build_environment.py --strict`（集合相等 + 缺口即拒绝） | **依赖身份门禁** |
| 145–153 | 第一方包非 editable | 来源形态门禁 |
| 167 | `PyInstaller --clean --noconfirm pyinstaller.spec` | 构建 |
| 176–200 | 产物存在 + 再次校验随包 PEM | 安全门禁（构建后复检） |
| 217 | `mcp_prebuilds.py` 生成 `prebuilds.json`（扫 `bin/` 全量 sha256） | 清单生成 |
| 224 | `verify_mcp_prebuilds.py` 校验清单与 PEM | 清单门禁 |

**关键事实**：这条链里**没有任何 `pip install`**。文件头注释 L9 写的是人工命令：

```powershell
<任意 3.12 解释器> -m venv D:\tools\venvs\jobws-mcp-build
D:\tools\venvs\jobws-mcp-build\Scripts\python.exe -m pip install "pyinstaller<7" .\packages\jobws-core .\mcp
```

所以现状是「**换台机器按 commit 重建**」不成立——重建依赖一串没人记录的手工步骤。

## 四、改造设计：从「事后校验」到「声明式」

### 4.1 新增开关（不改默认行为）

```
build_mcp_exe.ps1 -FromLock
```

`-FromLock` 时的流程替换「假设 venv 已就绪」：

```powershell
# 1) 用指定基础解释器建**全新** venv（不复用既有构建 venv）
& $BasePython -m venv $freshVenv

# 2) 第三方：按锁安装，强制哈希（这一步把 setuptools==84.2.1 也装进 venv）
& "$freshVenv\Scripts\python.exe" -m pip install --require-hashes --only-binary :all: `
    -r mcp/build-requirements.lock

# 3) 先清掉旧构建输出——避免上一次的 wheel 被当成这一次的产物装进去
Remove-Item .\dist\jobws_core-*.whl, .\dist\jobws_mcp-*.whl -ErrorAction SilentlyContinue

# 4) 第一方：**关掉构建隔离**构建 wheel
#    见 §4.3：两个包的 build-system 都是开放下界，默认隔离会另建环境重新解析，
#    装到的 setuptools 版本不受锁控制。--no-build-isolation 让它用 venv 里那份（= 锁里的）。
& "$freshVenv\Scripts\python.exe" -m pip wheel .\packages\jobws-core .\mcp `
    -w dist --no-deps --no-build-isolation

# 5) 明确取到「每个包恰好一个」wheel，不靠通配符
#    多于一个候选直接失败——不要装上"碰巧排在前面的那个"
$coreWhl = @(Get-ChildItem .\dist\jobws_core-*.whl)
$mcpWhl  = @(Get-ChildItem .\dist\jobws_mcp-*.whl)
if ($coreWhl.Count -ne 1) { throw "jobws-core wheel 候选数=$($coreWhl.Count)（须为 1）" }
if ($mcpWhl.Count  -ne 1) { throw "jobws-mcp wheel 候选数=$($mcpWhl.Count)（须为 1）" }
& "$freshVenv\Scripts\python.exe" -m pip install --no-deps `
    $coreWhl[0].FullName $mcpWhl[0].FullName

# 6) 第一方 wheel 身份入收据：绝对路径 + sha256 + 版本（不是只记文件名）
```

### 4.2 为什么第一方必须走 wheel 而不是目录安装

`pip install .\packages\jobws-core`（目录）在 `direct_url.json` 里只有 `dir_info`，**没有 wheel 哈希**——于是 C5b 只能记 SKIP，而 strict 模式会因此拒绝产出。这不是障碍，是合同在逼正确做法。

### 4.3 构建工具链**也要锁**（设计稿初版漏了这一点）

#### 事实

两个第一方包的构建系统都是**开放下界**：

```
mcp/pyproject.toml:                 requires = ["setuptools>=61.0"]
packages/jobws-core/pyproject.toml: requires = ["setuptools>=64"]
```

而 `pip wheel` **默认开启构建隔离**：它在临时环境里按上面那些下界**重新解析** setuptools，用的是解析当时的最新版——不是锁里的那个。

```
mcp/build-requirements.lock: setuptools==84.2.1   ← 运行时环境是钉死的
                               但构建隔离用的那份：不受锁控制
```

`--no-deps` **不会**关闭这个机制——它只管"不要装这个包的依赖"，不管"构建这个包需要什么工具"。

#### 后果

即使 37 项运行时依赖完全一致，两次构建仍可能因为构建工具版本不同而产出不同的 wheel 字节——进而污染 `REPRODUCIBILITY_EVALUATED` 的结论。

#### 处置（已并入 §4.1 的步骤 4）

| 项 | 做法 |
|---|---|
| 关隔离 | `pip wheel --no-build-isolation`，让构建用 venv 里那份 `setuptools==84.2.1` |
| 前提 | `setuptools` 必须在 lock 里（**已经在了**：`setuptools==84.2.1`），否则关隔离后会找不到构建后端 |
| 记录 | 构建收据里记 `build_tools.setuptools`、`build_tools.pip` 的实际版本 |

**这条不能靠"碰巧版本相同"来满足**——要显式关闭隔离，让版本由锁决定。

### 4.4 `DECLARATIVE_BUILD_ENV_READY` 的签署判据

| # | 判据 | 怎么验 |
|---|---|---|
| D1 | `-FromLock` 能从空 venv 一路构建成功 | 在一台**没有** `jobws-mcp-build` venv 的机器/容器上跑 |
| D2 | 过程中没有任何手工 `pip install` | 构建日志里只有脚本发出的 pip 命令 |
| D3 | 安装用了 `--require-hashes` | 命令可回看 |
| D4 | 第一方 wheel 有 sha256 记录 | 构建收据里能查到 |
| **D5** | **构建工具链由锁决定**（`--no-build-isolation`） | 收据里记 `setuptools` 实际版本，且等于 lock 里的值 |
| **D6** | **每个第一方包恰好一个 wheel 候选** | 候选数 ≠ 1 时脚本必须失败，不是取第一个 |

**D1 是分水岭**：在本机复用既有 venv 跑通不算——那证明的是"这台机器恰好能构建"。

**D5 是最容易漏的**：`--no-deps` 让很多人以为"依赖已经锁住了"，但构建隔离是另一条路径——见 §4.3。

### 4.5 构建收据要记的输入身份（完整清单）

只记最终 exe 的哈希不够——出问题时无法回答"这串哈希是由什么造出来的"。收据至少要能重建这个问题：

| 段 | 字段 |
|---|---|
| 源码 | `git_sha`、`dirty`（工作树是否有未提交改动）、`branch` |
| 解释器 | `python_version`、`sys.executable` 绝对路径 |
| 依赖 | `lock_sha256`、`lock_package_count`（37）、`lock_hash_count`（519） |
| 构建工具 | `build_tools.setuptools`、`build_tools.pip` |
| 第一方 | 每个包的 wheel 绝对路径 + `sha256` + `version` + 是否 `--no-build-isolation` |
| 安全基线 | `certifi_version`、`pem_sha256` |
| 产物 | `jobws-mcp.exe` 的 sha256、`prebuilds.json` 的 sha256、文件总数 |
| 环境 | `declarative_venv`（是否由 `-FromLock` 新建）、`isolated_from_existing` |

**`dirty` 字段尤其重要**：一个带未提交改动的构建，其 `git_sha` 无法代表实际源码。

## 五、可复现性：`EVALUATED` 与 `PASS` 是两级

初版设计稿把这两个词混着用了，先分清：

| 等级 | 含义 | 什么时候能签 |
|---|---|---|
| `REPRODUCIBILITY_EVALUATED` | **做过**两次独立构建，并产出差异报告 | 只要真的做了就能签——**无论结果好坏** |
| `REPRODUCIBILITY_PASS` | 全量文件与哈希**满足** R1–R6 冻结判据 | 只有全部满足才能签 |

**"做过评估" ≠ "通过评估"。** 前者回答「我们查过」，后者回答「查下来是一样的」。
收据里两个字段都要写，不允许用一个含糊的 `REPRODUCIBILITY = OK` 盖住。

### 5.1 比什么

**比整个 onedir 文件集合，不只是 exe。** 理由来自实测：

- 同一源码三次构建得到三个 EXE 哈希（`8eebafb8` / `c8a9b4bc` / `fbf76ef1`）；
- 文件数出现 211 / 215 两种；
- PyInstaller 的构建环境与 `uv.lock` 有实际差异。

### 5.2 判据表

| # | 判据 | 通过条件 |
|---|---|---|
| R1 | 两个**独立** venv（各自 `-FromLock` 建） | 不复用同一个 |
| R2 | `bin/` 文件集合相同 | 路径集合完全一致 |
| R3 | 每文件 sha256 相同 | 全量比对，不是抽样 |
| R4 | `prebuilds.json` 的 `files` 映射相同 | 两份清单逐键比 |
| R5 | 两个 `jobws-mcp.exe` 的 sha256 相同 | 核心判据 |
| R6 | 17 工具冒烟两个都过 | `verify_mcp_prebuilds.py` + 工具数断言 |

**R1 不可省**：同一 venv 连续跑两次，即使哈希相同，也只有"该环境的重复构建一致性"，不能推到"独立环境可复现"。

### 5.2b 实测记录（2026-10-27，本机四轮）

从「6 个文件不同」一路收敛到「227 个文件逐字节一致」。三个根因、三次修复，每次都有前后数据。

| 轮 | 改了什么 | R2 集合 | R3 哈希 | R5 exe |
|---|---|---|---|---|
| ① 基线 | — | ✅ 227 | ❌ 221/227（6 差） | ❌ `745ab93a` ≠ `5284e768` |
| ② | `SOURCE_DATE_EPOCH` + 固定 wheel 暂存 | ✅ 227 | ⚠️ 224/227（3 差） | ✅ `3e2a2e2d` |
| ③ | 固定 **venv** 路径 | ✅ 227 | ⚠️ 226/227（1 差） | ✅ `ace7654b` |
| ④ | 再加 `PYTHONHASHSEED=0` | ✅ 227 | ✅ **227/227** | ✅ `ace7654b` |

#### 根因一：`pip wheel` 的 ZIP 时间戳（第 ①→② 轮）

`direct_url.json` 里 wheel 的 `sha256` 两次就不同（`062669d1…` vs `937c80d8…`）——
说明**不可复现的是 wheel 本身**，不是安装过程。对照实验（独立 venv、同设
`SOURCE_DATE_EPOCH=1700000000`）产出 `bec27ea2…` = `bec27ea2…`。

修法：`SOURCE_DATE_EPOCH` = HEAD commit 时间（确定值、语义正确；取不到就拒绝构建）。
这一轮同时让 `jobws-mcp.exe` 变得一致。

#### 根因二：venv 绝对路径被嵌进 launcher exe（第 ②→③ 轮）

`RECORD` 里有一行 `../../Scripts/httpx2.exe`。实测该 launcher 的二进制里**含 venv 路径**
（`jobws-mcp-build-c0f69a6f` vs `-ba71ea7b`），而 RECORD 记录它的 sha256，随 onedir 打包。

修法：venv 路径固定为 `jobws-mcp-build-fromlock`（每次先删后建，仍是全新环境）。
加上第 ② 轮固定的 wheel 暂存路径，`direct_url.json` 与两个 `RECORD` 全部不再漂移。

#### 根因三：`PYTHONHASHSEED` 导致的 zip 条目顺序（第 ③→④ 轮）

`base_library.zip` 的时间戳**早已固定**为 `(1980,1,1,0,0,0)`（PyInstaller 硬编码），
所以不是时间问题。但条目顺序不是字母序（`genericpath.pyc` 在 `copyreg.pyc` 之前），
说明是遍历序——PyInstaller 内部大量用 `set` 收集模块，而 str 哈希默认随机。

修法：`PYTHONHASHSEED=0`。这一轮之后 155 个 `.pyc` 逐字节一致。

#### 最终签署

```
REPRODUCIBILITY_EVALUATED = true
REPRODUCIBILITY_PASS      = true
R1 两个独立 venv（同路径串行重建）✅
R2 文件集合 227 = 227            ✅
R3 每文件 sha256 227/227         ✅
R4 version 26.10.0               ✅
R5 jobws-mcp.exe ace7654b…       ✅
```

**必须一起读的边界**：

- 已证明的是**同机 + 同固定路径 + 同 `SOURCE_DATE_EPOCH` + 同 `PYTHONHASHSEED`** 下的字节一致；
- **跨机器未证明**：venv 路径不同（`C:\Users\<名>\AppData\Local\Temp\…`）会改变 launcher 与
  `RECORD`，因此跨机器目前**仍会不同**。要实现跨机器可复现，需要把构建路径相对路径化，
  属独立工程目标；
- 因此本 PASS 的实际价值是：**「同一版本重建两次，字节是否一致」可回答**，
  以及**「制品是否被意外改动」可对账**——不是"任何人都能复现出同一字节"。

### 5.3 如果 R3/R5 不相等

```
REPRODUCIBILITY_EVALUATED = true      ← 确实做了两次构建
REPRODUCIBILITY_PASS      = false     ← 但没通过
differences = [ ...逐文件差异清单... ]  ← 必须落进收据，不许只写"不一致"
```

**不得**通过"多试几次直到哈希相同"来制造一致——那是把随机性当成功。第一次不等就要停下来记录差异，而不是换一次重跑。

差异清单至少要能回答：**哪些文件不同、差在字节还是只差时间戳、差异是否集中在某类文件**（例如 `_internal/` 下的 `.pyc`）。

## 六、当前已知障碍（写在这里，避免落章时才发现）

| # | 障碍 | 影响 | 处置 |
|---|---|---|---|
| 1 | ~~工作树有另一条 certifi 2026.10.23 未提交线~~ | 会让校验门禁（10.23）与构建门禁（10.19）互相打死 | ✅ **已处置（2026-10-27）**：按裁决撤离，三处恢复 10.19；原始 diff 与文件存于 `.codebuddy/tmp/certifi-1023-backup/` |
| 2 | ~~无测试保护 certifi 三方一致~~ | 基线漂移只在真机构建时暴露 | ✅ **已补**：`tests/test_certifi_baseline_parity.py`（4 项，红绿双向验证过） |
| 3 | `prebuilds.json` 的 `version` 停在 `26.10.0` | 与 26.11.0 落章不同步 | 落章时随重建刷新 |
| 4 | 主包与平台子包各带一份 `platform` | 体积重复（有意 fallback） | **不删**；缩包实验留后续 |
| 5 | npm 两包尚未发布（registry 404） | 首次公开分发未开始 | 落章后独立授权 |
| 6 | ~~构建工具链不受锁控制~~（`setuptools>=61` 开放下界 + pip 默认构建隔离） | 两次构建可能用不同 setuptools | ✅ **已处置**：`-FromLock` 带 `--no-build-isolation`，实测 `setuptools=84.2.1` = 锁内值（D5） |
| 7 | ~~产物不可复现~~ | 「重建同一版本」无法对账 | ✅ **已处置**：三个根因逐个消除，227/227 文件逐字节一致（§5.2b） |
| 8 | **跨机器可复现未证明** | 不同机器的 venv 路径不同 → `Scripts/*.exe` 与 `RECORD` 会不同 | **本轮不承诺**；要做得把构建路径相对路径化，属独立工程目标 |

## 七、落章执行顺序（26.11.0）

```
1. 冻结源码身份（tag 前的 commit），记录 git_sha + dirty 状态
2. 确认工作树干净（障碍 1/2 已处置；否则 dirty=true，源码身份不可信）
3. 同步五处版本：web/electron/package.json、integrations/dsh/package.json、
   platform/win32-x64/package.json、9 个 SKILL.md、CHANGELOG
4. -FromLock 构建（第一次）：
     a. 全新 venv + --require-hashes 装锁（含 setuptools==84.2.1）
     b. 清 dist/ 旧 wheel
     c. pip wheel --no-deps --no-build-isolation（D5）
     d. 每包恰好一个候选，记绝对路径 + sha256（D6）
     e. 安装 + PyInstaller + prebuilds.json
     f. 收据写入 §4.5 的全部字段
5. -FromLock 构建（第二次，**另一个**全新 venv）→ 比 R2–R5
6. 差异为零 → REPRODUCIBILITY_PASS = true；否则记 EVALUATED=true / PASS=false + 差异清单
7. verify_mcp_prebuilds.py（清单 + PEM）
8. npm pack 双 tarball → 记 sha256
9. 17 工具冒烟
10. 结论按两级如实写：EVALUATED / PASS 分开签
```

第 4 与第 5 步必须用**不同 venv**；第 9 步的结论只对 MCP 运行时有效。

## 八、本文件**没有**做的事

- 没有执行任何构建；
- 没有修改 `build_mcp_exe.ps1`（`-FromLock` 仍是设计，不是实现）；
- 没有声称任何一级证据已通过；
- 没有改 `prebuilds.json`。
