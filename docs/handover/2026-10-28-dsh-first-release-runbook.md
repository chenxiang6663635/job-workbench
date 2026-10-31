# DSH 插件首发执行单（26.11.0）

> **定位**：不是新规范。把散在 `integrations/dsh/README.md` §六/§七、`docs/release-checklist.md`、
> G4 构建合同里的首发条件，汇成一张**可照单执行**的表，并补上 2026-10-27 / 10-28 的实测证据。
> 规范以原文档为准；本文只负责「按什么顺序做、卡在哪、怎么算过」。

## 一、当前状态：**构建探索完成，待最终候选验证与发布授权**

**已完成的（技术侧）**：

| 项 | 状态 | 证据 |
|---|---|---|
| 宿主兼容（本机 `0.2.1-rc.3`） | ✅ 通过 | 读 DSH 源码实测，见 §二 |
| 包能构建 | ✅ | `-FromLock` 从空 venv 一路成功（88–102s） |
| 主包体积 | ✅ 22.4 MB / 249 文件 | `npm pack --dry-run`（npm 上限 100 MB） |
| 平台子包含 `bin/` + `prebuilds.json` | ✅ | `npm prepack` 校验通过 |
| 17 工具冒烟 | ✅ `SMOKE OK` | `scripts/smoke_mcp_exe.py` |
| 产物可复现 | ✅ 227/227 逐字节一致 | G4 合同 §5.2b |

**尚未完成的（这些是工作，不是授权）**：

```
□ 落章（三个 package.json + 主包 `optionalDependencies`；现在仍是 26.10.0）
□ 用 -FromLock 重建（prebuilds.json 的 version 要跟着落章后的号）
□ 对落章后的产物重跑双包预检 + 17 工具冒烟
□ npm 双包发布（子包先、主包后）
□ 发布后从公共 npm 全新安装核验
□ 发布授权                              ← 只有这一项是授权
```

> **此前本节标题写的是「技术侧已就绪，只差节点与授权」——过强，已改。**
> 上面六项里五项都是落章后必须真跑的工作；把它们归成「授权」会让人以为落章当天不会有
> 任何待验环节（2026-10-28 审计指出）。

## 二、核实证据（2026-10-27 / 10-28）

### 2.1 宿主准入机制：读源码，不读文档

从 `D:\tools\dsh\resources\app.asar` 解出的 `@deepseek-ai/dsh-app-boot/lib/index.js`：

```js
function satisfies(runtimeVersion, range) {
  return range.trim() !== "" &&
    semver.satisfies(runtimeVersion, range, { includePrerelease: true });
}
```

**关键：`includePrerelease: true`**。它关掉了 node-semver 的 prerelease 隔离规则。

### 2.2 版本判定实测（npm 自带 semver）

`^0.2.0-rc.2` 展开为 `>=0.2.0-rc.2 <0.3.0-0`：

| 宿主版本 | 纯 semver 默认 | `includePrerelease`（**DSH 实际**） |
|---|---|---|
| `0.2.0-rc.1` | ❌ | ❌ |
| `0.2.0-rc.2` | ✅ | ✅ |
| `0.2.1-rc.1` | ❌ | ✅ |
| **`0.2.1-rc.3`**（本机实证） | ❌ | ✅ |
| `0.2.1` / `0.2.9` | ✅ | ✅ |
| `0.3.0-rc.1` / `0.3.0` | ❌ | ❌ |

> **教训**：只按 semver 规范推断会得出「`0.2.1-rc.3` 装不上」的**错误结论**（10-27 确实这样判断过
> 并写进了文档，10-28 读源码才纠正）。**版本约束要看它怎么调用 semver，不是看规范。**

### 2.3 `engines` 的层级陷阱

同一个 `unmetRequirements(fields, runtimeVersion)` 里：

```js
const engines = Object.hasOwn(fields, "engines") ? objectOf(fields.engines, ...) : {};
```

`fields` 是 **manifest 顶层**。所以：

| 写法 | 是否被检查 |
|---|---|
| 顶层 `"engines": { "dsh": "..." }` | **会**，不满足则整包跳过 |
| `"dsh": { "engines": { "dsh": "..." } }`（**本包当前写法**） | **不会** |

「`engines.dsh` 不被强制」的真正原因是**我们没写在被检查的那层**，不是 DSH 不检查。

> ⚠️ **不要把它「整理」成顶层 `engines`**——那会新开一道门禁，而失败方式是整包**静默跳过**。

## 三、首发前置自检（任何一项不过就不要发）

首发**不可撤销**，所以这 6 项必须逐条过：

| # | 检查 | 命令 / 判据 | 不过的后果 |
|---|---|---|---|
| 1 | 目标宿主满足 `peerDependencies` | 按 §二.2 判定（**别用纯 semver**） | 装了但整包被跳过，**不报错** |
| 2 | 两包版本 == `web/electron/package.json` | `python tools\assets_registry.py --check` | 构建门禁红 |
| 3 | `prebuilds.json` 与 `bin/` 自洽 | `python scripts\verify_mcp_prebuilds.py` | `npm prepack` 拒绝 |
| 4 | 17 工具冒烟 | `python scripts\smoke_mcp_exe.py` | 装上了也没有工具 |
| 5 | 包体积在 npm 限制内 | `npm pack --dry-run` 看 `package size` | registry 拒绝 |
| 6 | 工作树干净 | `git status --porcelain` 为空 | 收据 `dirty=true`，`git_sha` 不代表实际源码 |

## 四、执行步骤

### 4.1 落章：与执行单同源（**细节只在执行单里维护**）

落章的完整字段清单与命令见
[`2026-10-30-2611-release-steps.md`](2026-10-30-2611-release-steps.md) 的 §二；
本节只保留**与 DSH 双包强相关**的三条，避免两处计数再次漂移：

| # | 位置 | 怎么改 |
|---|---|---|
| 1 | `integrations/dsh/package.json` → `version` | 手改 |
| 2 | `integrations/dsh/package.json` → **`optionalDependencies["dsh-job-workbench-win32-x64"]`** | 手改，**精确版本**（`^`/`~` 会被门禁判错）。2026-10-31 审计发现 1：漏了它，主包会去取旧子包而门禁全绿 |
| 3 | `integrations/dsh/platform/win32-x64/package.json` → `version` | 手改（`build_mcp_exe.ps1` 校验 == 主包） |

应用版本、lock 两行、9 个技能、插件壳、CHANGELOG 都在执行单 §2.1–§2.4，不在这里重复。

### 4.2 四道闸（顺序不能反）

```powershell
python tools\jobws.py skills check
python tools\assets_registry.py --check
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\build_mcp_exe.ps1 `
     -FromLock -BasePython "<3.12 基础解释器>"
python scripts\smoke_mcp_exe.py
python tools\jobws.py release check --tag v26.11.0
```

- **必须 pwsh 7**：PS 5.1 会按 ANSI 解码 UTF-8 无 BOM 脚本 → ParserError
- 构建收据落在 `$env:TEMP\jobws-mcp-receipt-*.json`，记 `git_sha` / `dirty` / `setuptools` / wheel 哈希
- 若 PyPI 索引页 TLS 失败（`/simple/altgraph/` 会），脚本会提示 `PIP_INDEX_URL`——
  **`--require-hashes` 校验 wheel 字节，换源不放宽证据**

### 4.3 双包预检与发布（**子包先、主包后**）

```powershell
cd integrations\dsh\platform\win32-x64
npm pack --dry-run     # 应含 bin/ 与 prebuilds.json
npm publish            # dsh-job-workbench-win32-x64@26.11.0

cd ..\..
npm pack --dry-run     # 应含 cordis.patch.yml / skills / platform / scripts/install.ps1
npm publish            # dsh-job-workbench@26.11.0
```

顺序不可反：主包的 `optionalDependencies` 是
`"dsh-job-workbench-win32-x64": "26.11.0"`（**精确版本**）——子包不在架上，主包装不上。

### 4.4 发布后立即核验

```
□ 到 npm 页面核对 repository 指回本仓库（marketplace 的 npm 关联依赖这条，写错会静默不关联）
□ 从**公共 npm** 全新安装（不用 link: / 源码树 / 本机缓存）
□ 真实 DSH Desktop profile：17 工具 + 9 技能 + 卸载
```

## 五、市场收录（**必须在这之后**）

向 `awesome-dsh-plugin/awesome-dsh-plugin` 提 PR，只加一个文件
`data/plugins/chenxiang6663635__job-workbench.yml`（内容见 `integrations/dsh/README.md` §六）。

**时机写死**：未发布时提交 = **给出一条装不上的命令**。

提交前核对：描述里的数字必须与代码一致（**17 工具 / 9 技能**）。

## 六、失败处置

| 症状 | 处置 |
|---|---|
| 用户装了但工具不出现、也无报错 | 先查 §二.2 的宿主版本；再看 `dsh --dump-config` 里有没有 `skipping profile bundle` |
| `npm publish` 报 version 已存在 | **不改已发布版本**；发 `26.11.1` 或 `26.12.0` |
| 子包发布成功、主包失败 | 主包可稍后补发（子包已就位，不影响）；**不要**回滚子包 |
| 发布后发现严重缺陷 | `npm deprecate` 标记版本 + 立即发修复版；**不要 unpublish**（会破坏已装用户） |

## 七、边界与不承诺

- **平台**：仅 Windows x64。其他平台技能可加载，但 **MCP 运行时无制品**——且宿主不报错
  （`failOnStartupError: false`），用户看到的是「没工具」而不是「装失败」；
- **跨机器可复现**：**未证明**。G4 的 `REPRODUCIBILITY_PASS` 只覆盖同机同路径；
- **`jobws://` 深链**：**未实现**。它只出现在文档里，不要对外宣称已支持；
- **收录**：`awesome-dsh-plugin` 是否接受，不由我们决定。

## 八、这份文档没有做的事

- 没有执行任何发布动作；
- 没有改 peerDependencies（§二.2 证明**不需要改**）；
- 没有承诺收录一定通过。
