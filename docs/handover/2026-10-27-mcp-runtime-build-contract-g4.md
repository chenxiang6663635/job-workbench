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
| `DECLARATIVE_BUILD_ENV_READY` | ❌ | 入口**只校验不安装**：依赖仍靠人工配 venv |
| `REPRODUCIBILITY_EVALUATED` | ❌ | 从未做过两个独立环境构建 + 比整个 onedir |

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

# 2) 第三方：按锁安装，强制哈希
& "$freshVenv\Scripts\python.exe" -m pip install --require-hashes --only-binary :all: `
    -r mcp/build-requirements.lock

# 3) 第一方：先构建 wheel（才有可核验哈希），再安装
& "$freshVenv\Scripts\python.exe" -m pip wheel .\packages\jobws-core .\mcp -w dist --no-deps
& "$freshVenv\Scripts\python.exe" -m pip install --no-deps dist\jobws_core-*.whl dist\jobws_mcp-*.whl

# 4) 记录第一方 wheel 身份（供收据）
#    wheel 文件名含版本；sha256 落进构建收据的 first_party 段
```

### 4.2 为什么第一方必须走 wheel 而不是目录安装

`pip install .\packages\jobws-core`（目录）在 `direct_url.json` 里只有 `dir_info`，**没有 wheel 哈希**——于是 C5b 只能记 SKIP，而 strict 模式会因此拒绝产出。这不是障碍，是合同在逼正确做法。

### 4.3 `DECLARATIVE_BUILD_ENV_READY` 的签署判据

| # | 判据 | 怎么验 |
|---|---|---|
| D1 | `-FromLock` 能从空 venv 一路构建成功 | 在一台**没有** `jobws-mcp-build` venv 的机器/容器上跑 |
| D2 | 过程中没有任何手工 `pip install` | 构建日志里只有脚本发出的 pip 命令 |
| D3 | 安装用了 `--require-hashes` | 命令可回看 |
| D4 | 第一方 wheel 有 sha256 记录 | 构建收据里能查到 |

**D1 是分水岭**：在本机复用既有 venv 跑通不算——那证明的是"这台机器恰好能构建"。

## 五、可复现性判据（`REPRODUCIBILITY_EVALUATED`）

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

### 5.3 如果 R3/R5 不相等

如实记 `REPRODUCIBILITY_EVALUATED = NOT_DEMONSTRATED`，并把差异文件清单落进收据。
**不得**通过"多试几次直到哈希相同"来制造一致。

## 六、当前已知障碍（写在这里，避免落章时才发现）

| # | 障碍 | 影响 | 处置 |
|---|---|---|---|
| 1 | 工作树有另一条 **certifi 2026.10.23** 未提交线（`verify_mcp_prebuilds.{py,js}` + `AGENTS.md`） | 若误提交，会让校验门禁（10.23）与构建门禁（10.19）互相打死 | 该线须独立走四条门禁；落章前确认工作树干净 |
| 2 | 该线原本的 `tests/test_certifi_baseline.py` 已改名为 `.pending-1023` | **当前没有测试保护"PS1 与 verify 的 certifi 基线一致"** | 建议补一条三方一致性测试（PS1 / verify.py / verify.js），与落章同一批 |
| 3 | `prebuilds.json` 的 `version` 停在 `26.10.0` | 与 26.11.0 落章不同步 | 落章时随重建刷新 |
| 4 | 主包与平台子包各带一份 `platform` | 体积重复（有意 fallback） | **不删**；缩包实验留后续 |
| 5 | npm 两包尚未发布（registry 404） | 首次公开分发未开始 | 落章后独立授权 |

## 七、落章执行顺序（26.11.0）

```
1. 冻结源码身份（tag 前的 commit）
2. 确认工作树干净（障碍 1 必须已处置）
3. 同步五处版本：web/electron/package.json、integrations/dsh/package.json、
   platform/win32-x64/package.json、9 个 SKILL.md、CHANGELOG
4. -FromLock 构建（第一次）→ 记 bin/ 全量 sha256 + 收据
5. -FromLock 构建（第二次，独立 venv）→ 比 R2–R5
6. 生成 prebuilds.json → verify_mcp_prebuilds.py
7. npm pack 双 tarball → 记 sha256
8. 17 工具冒烟
9. 结论：REPRODUCIBILITY_EVALUATED = PASS / NOT_DEMONSTRATED（如实）
```

第 4 与第 5 步必须用**不同 venv**；第 9 步的结论只对 MCP 运行时有效。

## 八、本文件**没有**做的事

- 没有执行任何构建；
- 没有修改 `build_mcp_exe.ps1`（`-FromLock` 仍是设计，不是实现）；
- 没有声称任何一级证据已通过；
- 没有改 `prebuilds.json`。
