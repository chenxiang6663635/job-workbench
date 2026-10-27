# MCP Build Lock Contract v1（构建依赖准入）

- 日期：2026-10-27
- 范围：**MCP 运行时（`jobws-mcp` onedir）** 的构建依赖身份、完整性与准入检查
- 明确**不覆盖**：Electron / NSIS 安装包（见 §六 边界）
- 基线：`main = 4e2b027`

---

## 一、这份合同解决什么

此前 `scripts/build_mcp_exe.ps1` 每次从各 `pyproject.toml` 的**开放版本范围**（如 `mcp>=2.2,<3`）重新解析依赖，导致同一 commit 实测构建出**三个不同哈希**的 EXE（`8eebafb8` / `c8a9b4bc` / `fbf76ef1`）。依赖是其中**可消除的一部分**。

本批只解决依赖身份与准入，不宣称可复现已经达成（§五 的四级证据）。

## 二、证据等级：四个不同的断言，不可互相冒充

| 等级 | 含义 | 判据 | 本轮状态 |
|---|---|---|---|
| **LOCK_CONTENT_VALIDATED** | 锁的内容完整：第三方闭包齐全、版本自洽、每项带 SHA256 | `tests/test_mcp_build_lock.py`（`.in`≡`.lock`、certifi 基线、每项有 hash） | ✅ **已签署** |
| **HASH_INSTALL_TESTED** | 锁**能被实际消费**：干净 venv `--require-hashes` 安装成功 | §四 实测记录 | ✅ **已签署** |
| **DECLARATIVE_BUILD_ENV_READY** | 正式构建入口**用锁装环境**，而不是"检查现有 venv" | 构建脚本从"校验"改为"`uv pip sync`/`pip install -r`" | ❌ 未签（G4 前置批次） |
| **REPRODUCIBILITY_EVALUATED** | 两个独立环境构建，产物一致 | 比**整个 onedir 文件集合**，不只 exe | ❌ 未签（G4） |

**当前构建入口仍是"事后校验"**：`build_mcp_exe.ps1` 调用检查器判断现有 venv 是否与锁集合相等，不等即 `exit 1`。它**不**替你装依赖——因为改动开发者环境是另一件事，fail-closed 是它的职责边界。

## 三、判据（`scripts/check_mcp_build_environment.py`）

集合语义是**相等**，不是 `LOCK ⊆ INSTALLED`：「该有的都有」不保证「不该有的没有」。
PyInstaller 的 hook 会把 venv 里多装的包 collect 进制品（`setuptools` 就这样进的制品目录）。

| ID | 判据 | 失败条件 |
|---|---|---|
| C1 | 解释器 = Windows x64 CPython 3.12 | 平台/架构/版本/实现不符 |
| **C2b** | **锁中不含第一方包**（分层未被破坏） | `jobws-core` / `jobws-mcp` 出现在锁里 —— 否则它会被当第三方静默比对版本，绕过 C5 的来源核对 |
| C2 | 无缺失依赖 | 锁中有、venv 无 |
| C3 | 无多余依赖 | venv 有、锁中无、且不在引导工具例外（仅 `pip`） |
| C4 | 版本与锁一致 | 同名包版本不符 |
| C5 | 第一方包存在且**非 editable** | `jobws-core` / `jobws-mcp` 缺失或为 editable 链接树 |
| **C5b** | **第一方包 wheel 身份可审计** | 无 wheel 哈希（目录安装）或来源不可读 → **SKIP 缺口**，不算产品失败但必须可见 |
| C6 | 无重复包元数据 | 同规范化包名出现多份安装 |
| C7 | `pip check` 无依赖冲突 | 依赖不满足（无 pip 时记 SKIP，不冒充 PASS） |

**C5b 为什么必要**：只防 editable 防不了「装的是上一次构建的旧 wheel」——第一方包在开发期的版本号常常不变，光比版本号无法区分两次构建。pip 安装本地 wheel 时 `direct_url.json` 里有 `archive_info.hash`；目录安装（`pip install .`）没有，记缺口并要求改用 wheel。

**例外只有 `pip`**。刻意**不**把 `setuptools` / `wheel` / `packaging` 或 PyInstaller 的辅助依赖设为白名单——它们参与实际构建，必须进锁。

包名按 PEP 503 规范化（大小写、`-`/`_`/`.` 归一）后比对。

**为什么规则独立成文件**：同一实现被构建入口与负向测试复用。若规则写在 PowerShell 里，测试只能"扫描脚本里有没有关键字"，那是假测试。

## 四、实测记录（2026-10-27）

### 1. 锁生成

```
uv pip compile mcp/build-requirements.in `
    --python-version 3.12 --python-platform windows `
    --only-binary :all: --generate-hashes `
    --output-file mcp/build-requirements.lock
```

**版本闭包比对**（不能只看 exit=0）：

```
原 lock 包数 = 37 | 新 lock 包数 = 37
仅旧有 = 无 | 仅新有 = 无
版本变化 = certifi 2026.10.23 -> 2026.10.19   ← 唯一变化，按 2026-10-27 裁决回基线
非预期漂移 = 无
hash 条数 = 519
```

> **hash 的准确口径**（2026-10-27 审查修正）：`--python-platform windows` **只影响解析**，
> 不限制 hash 收集——519 个 hash 里含多平台的 wheel。纯 Python 包通常 2 个（wheel + sdist），
> 带二进制扩展的包则很多（实测 `pydantic-core` 137 / `rpds-py` 128 / `cffi` 100 / `cryptography` 59）。
> 这不影响正确性：`--require-hashes` 只要求**当前平台**那一份存在。
> 但不要在文档里写成「只锁了 Windows 的 wheel」。

### 2. 干净 venv 的哈希安装（HASH_INSTALL_TESTED）

```
python -m venv <tmp>
<python> -m pip install --require-hashes --only-binary :all: -r mcp/build-requirements.lock
→ exit=0，装出 38 包（37 锁包 + pip）
→ certifi = 2026.10.19
```

> **网络说明（如实记录）**：本机直连 PyPI 时 `/simple/altgraph/` 持续 `SSL: UNEXPECTED_EOF_WHILE_READING`
> （两个源地址均失败），改用清华镜像完成本次验证。**hash 校验与镜像无关**——`--require-hashes`
> 比对的是 wheel 文件本身的 SHA256，镜像提供同一文件。这不是"放宽检查"。

### 3. 同一环境回跑检查器（证明"只装锁不够"）

```
[PASS] C1 解释器 = Windows x64 CPython 3.12
[PASS] C2 无缺失依赖          [PASS] C3 无多余依赖
[PASS] C4 版本与锁一致        [PASS] C6 无重复包元数据
[FAIL] C5 第一方包非 editable 且存在 — jobws-core 未安装; jobws-mcp 未安装
[PASS] C7 pip check 无依赖冲突
结论：FAIL（1 项）
```

这正是要表达的：**第三方锁装对 ≠ 环境可用**，第一方包必须从本次检出构建成非 editable wheel。

### 4. 负向测试（`tests/test_mcp_build_lock.py`，11 项全过）

| 用例 | 期望 | 机制 |
|---|---|---|
| 与锁集合相等 | PASS（exit 0） | 注入模式 |
| 多装 `pytest` | C3 FAIL | 多余包 |
| 删 `mcp` | C2 FAIL | 缺包 |
| `mcp` 版本改 `2.2.0` | C4 FAIL | 版本错 |
| `jobws-core` / `jobws-mcp` 置 editable | C5 FAIL | 来源错（参数化两例） |
| 同名 `mcp` 两份 | C6 FAIL | 重复元数据 |
| `.in` ≡ `.lock` | 必须相等 | 防手改 lock 与输入脱节 |
| `certifi == 2026.10.19` | 必须 | 防再次被顺带升级 |
| 每项都有 `--hash` | 必须 | 无 hash 防不了内容替换 |
| 构建入口调用检查器 | 必须 | 防两套规则漂移 |

## 五、certifi 基线（2026-10-27 裁决）

- 锁固定 `certifi==2026.10.19`，与 `main` 上 `build_mcp_exe.ps1` 的 `$CertifiMin` / `$CertifiSafePemSha`
  （`50F79F98…`，120 证书）**自洽**。
- `2026.10.23`（PEM `2EF52AD5…`，118 证书）已可用，但**不得**借"构建可复现性改进"顺带生效；
  须独立走安全基线升级四条门禁（逐字节对账 / 证书差集依据 / G3 零命中 / 四处同步 + 17 工具与真实 TLS 冒烟）。
- 本 PR **不含**任何 certifi 常量改动——那是另一条工作线。

## 六、边界（写死，防将来被读宽）

1. **本轮可复现性合同仅适用于 MCP 运行时**（`jobws-mcp` onedir），**不覆盖 Electron / NSIS 安装包**。
   当前 NSIS 构建流程不保证字节级复现；未来是否实现属另一项独立工程目标（不排除技术可能性，只是不在本合同内）。
2. 即使 G4 的双次构建一致，也**只**证明"指定条件下"的一致性：同机同 venv 连续两次 ≠ 跨机器独立重建。
   G4 应至少做到两个**独立环境** + 比较**整个 onedir 文件集合**（此前已实测过 211/215 的文件数量差异）。
3. 本合同的 `HASH_INSTALL_TESTED` 只证明"锁可被消费"，**不**证明"正式构建入口已强制哈希安装"。

## 七、维护

- 升级任何依赖 = 改 `mcp/build-requirements.in` → 重生成 lock → **比对版本闭包** → 重建 EXE →
  跑 17 工具冒烟 → 记新哈希。
- 与各 `pyproject.toml` 的版本范围冲突时：**锁优先**；`uv.lock` 不参与构建。
- 重建 lock 后若出现非预期版本漂移，**停下来**，不要"反正 CI 绿了"就接受。

## 八、2026-10-27 自审修正（5 项）

初版 PR #418 提交后按"当成别人写的"标准自查，发现以下问题并已修：

| # | 发现 | 性质 | 处置 |
|---|---|---|---|
| 1 | C5 只防 editable，**没有记录 wheel 哈希/版本/来源** —— 防不了"装的是上次构建的旧 wheel" | **MAJOR**（裁决 §二、§四 明确要求） | 新增 C5b：读 `direct_url.json` 的 `archive_info.hash`；读不到记 SKIP 缺口，不冒充通过 |
| 2 | `build_mcp_exe.ps1` 的 `$Py` **会回退到 PATH 里的裸 `python`** | **MAJOR**（裁决 §三 明确禁止"回退到 PATH 中不明来源的 Python"） | 去掉回退：三级显式指定（参数 / 环境变量 / 约定路径）都不满足则 `exit 2` 并打印三种配法；另加 `Test-Path` 校验 |
| 3 | 没有"锁中不得含第一方包"的断言 —— 若有人把 `jobws-core` 写进 `.in`，会被当第三方静默比对版本 | MINOR（分层破损） | 新增 C2b 判据 + 对应负向测试 |
| 4 | 文档写"生成 Windows x64 的 hash"，实际 hash 含多平台 | MINOR（表述误导） | §四 补准确口径（`--python-platform` 只影响解析） |
| 5 | `.in`/`.lock` 一致性测试用正则解析，对带环境标记（`; python_version >= …`）的条目会误判 | MINOR（当前锁内无标记） | 记为已知限制，不预先实现解析器 |

**未改的判定**（保持"MEETS"）：集合相等语义、例外只有 `pip`、七类判据、负向测试真跑检查器、
certifi 固定 10.19 与 `main` 门禁自洽、边界不覆盖 NSIS、四级证据分级。

错误码约定（本脚本）：`0` 通过 / `1` 环境与锁不一致 / `2` 未配置或找不到构建解释器。
