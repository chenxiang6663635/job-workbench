# 全仓库审计报告（2026-09-16）

> 范围：`D:\tools\autumn-recruit-workbench`，基线 `main` = `9b6b819`（PR #131 合并后）。
> 方法：全部结论基于**实跑命令或读回代码**，标注证据位置。未核实的会明说，不猜。
> 前置健康度：`pytest tests/` → **679 passed**；`pytest mcp/tests/` → **23 passed**；CI 五项全绿。

---

## 一、项目结构

### 1.1 定位

本地优先的求职工作台。单仓库、单发布节点，**桌面（Electron）+ 本地后端（FastAPI）+ CLI + MCP server** 四个入口共享同一份领域层。

### 1.2 目录布局与规模

| 目录 | 跟踪文件 | 内容 |
|---|---|---|
| `web/` | 135 | `backend/`（FastAPI，5354 行）+ `frontend/`（React/TS，68 文件 15073 行）+ `electron/`（桌面壳） |
| `tests/` | 50 | 主干测试（679 项） |
| `docs/` | 40 | specs / research / screenshots（双语 14 张） |
| `template/` | 37 | 工作区骨架 + 领域插件 + demo 数据 |
| `tools/` | 26 | **领域层**，9463 行，领域无关 |
| `mcp/` | 10 | 只读 MCP server（独立包，23 项测试） |
| `.github/` | 10 | 4 个 workflow + dependabot + 模板 |
| `skills/` | 8 | 面向 Agent 的技能资产 |

共 **343 个跟踪文件**。顶层另有 14 个 `research_*.md`、`tmp_demo6/`、`generated-images/`、`demo-shots/`、`__pycache__/` —— **全部已被 `.gitignore` 忽略**（`git ls-files` 对它们返回空），属本地磁盘杂乱，非仓库问题。

### 1.3 三层分离（架构骨架）

```
tools/            领域无关；不得出现领域术语或个人信息硬编码
template/profiles/ 领域知识（hvac-cooling / software-backend 两个插件）
personal/         个人事实；已 gitignore，0 个跟踪文件，历史经 filter-repo 清洗
```

`tools/` 是单一真源：Web 后端**直接 import 并复用**，CLI（`tools/jobws.py`）与 MCP server 是同一份实现的另外两个入口。

---

## 二、技术栈与依赖

### 2.1 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python **3.12** / FastAPI `<0.142` / uvicorn `<0.53` / pydantic `<2.14` |
| 前端 | React 18 / TypeScript ~5.6 / Vite 6.4.3 / Tailwind **3.4** |
| 桌面 | Electron **44**（`^44.3.0`）/ electron-builder 26 |
| 测试 | pytest（主干 + MCP）/ Playwright（UI 冒烟 + a11y） |
| 数据 | CSV / JSON 落盘 + 文件锁；无数据库 |

版本号体系：**时间戳**。发布号 `YY.MM.DD.N`（tag `v26.09.15.1`），机器版本 `YY.M.D`（`26.9.15`）。唯一来源 `web/electron/package.json`。

### 2.2 依赖健康度（实测）

| 面 | 结果 |
|---|---|
| 前端 `npm audit` | **0 漏洞** |
| Electron `npm audit` | **0 漏洞**（48 → 0 已于 v0.3.2 清账） |
| 后端过时包 | 仅 `pydantic_core` / `uvicorn` 两个 patch 级 |
| 未声明依赖 | 无。`python-multipart` 只由 MCP 传递引入，**主干刻意不用**（`resume.py:206-207` 用 base64 规避） |

**结论：依赖面干净**，是本次审计中表现最好的一环。

---

## 三、构建与运行配置

| 环节 | 配置 |
|---|---|
| CI | `.github/workflows/ci.yml`：4 个 job（backend / mcp / frontend / ui-smoke），Python 3.12 + Node 20 |
| 门禁 | `jobws lint {i18n,ui-tokens,domains,themes}` + `skills check` + doc-links 测试 + 双轨审查 |
| 保护 | 4 项必需检查、线性历史、会话解决、`enforce_admins` 全开启；`delete_branch_on_merge` 已开 |
| 发布 | tag `v*` → Windows 构建 → 挂 Release；`workflow_dispatch` 支持演练（dry-run） |
| 本地 | 3.12 venv（仓库内 `.venv/` 或仓库外）+ `web/start.ps1` 自动探测解释器 |
| 钩子 | `.githooks/pre-commit` 跑隐私 / 体积 / pytest / 结构四项 |

治理水平**超出单人项目常态**，几乎无改进空间。

---

## 四、发现的问题

按严重度排序。**每条都经代码或命令核实**。

### 🔴 P0-1 · 真实公司名泄漏到公开文件

**位置**：`web/backend/routers/jobs.py:158`

**证据**：
```
作键会与追踪表系统性失配。
（卡片里填的常是给人看的详细描述（如「示例集团（空调事业部＝…）」），当
```

**核实**：该名字在用户的 `personal/` 工作区（已 gitignore、不进仓库）里出现多处——是**真实投递过的公司**；而它曾出现在已推送到 GitHub 的 `jobs.py` 源码注释里（**已于本批改成虚构示例**）。

> 留档说明：本报告不复述真实公司名——公开仓库里写下它本身就是泄漏，哪怕是在
> 「指出某处泄漏」的语境里。结论落在「已定位并处置」，细节不必复刻。

**性质**：违反 `CONTRIBUTING.md:15`「禁止提交任何 `personal/` 内容：包括…真实公司名」（**时点注记 2026-09-26**：该行号与文件路径在贡献指南改为「根目录英文索引 + `docs/contributing.zh-CN.md` 中文细则」后不再成立；被引用的条款现在位于 `docs/contributing.zh-CN.md` 的「隐私约定」节。原文不改。）。这是**唯一**一处此类泄漏；同文件/同仓库的 `TCL`（`url_infer.py:8`、`test_job_linking.py:136`）是刻意的虚构示例，`云帆智算`/`示例科技` 是通用 demo 数据，均合法。

**处置**：改为虚构公司名（如「示例集团（事业部）」）即可，一行改动。

---

### 🟠 P1-1 · CHANGELOG 声称 18 项功能「未发布」，实际早已交付

**位置**：`CHANGELOG.md:16` 起的 `[Unreleased]` 段

**证据**：`[Unreleased]` 积压 **10 项 Added + 8 项 Changed**，含主题系统（10 套皮肤 + 编辑器）、题库独立化、宣讲会表、字体打包、prefs 体检等重大功能。

**核实这些功能全部已实现可用**：

| 功能 | 实测 |
|---|---|
| `track talk` | 子命令存在 |
| `bank` | 输出「题库：list / add / import」 |
| `prefs` | 输出「工作区偏好与环境体检」 |
| 主题 | `src/themes/*.css` = **9 个文件** |
| 题库页签 | `Progress.tsx` 命中 3 处 |
| 宣讲会页签 | `Progress.tsx` 命中 3 处 |

**影响**：使用者无法判断「升到哪个版本才有主题系统」；而 `v0.3.2` 段只记了构建链升级，**名实不符**。这是对外文档的可信度问题，非数据错误。

**处置**：确认这些功能的实际发布版本，把 `[Unreleased]` 内容归入对应版本段；无法回溯的，在段首注明「实际随 `v0.3.x` 交付，本节为补记」。

---

### 🟠 P1-2 · `file_lock` 是全仓写安全基石，却零测试覆盖

**位置**：`tools/filelock.py`（70 行，**被 0 个测试文件引用**）

> **时点注记（2026-09-22）**：本节是 2026-09-16 的快照，`tools/filelock.py` 此后已搬进领域包（`jobws_core.filelock`），路径与引用数都已过时；结论（"加锁行为本身需要真并发测试"）是否被后续批次兑现，请查当期 `tests/` 与 CHANGELOG，不要按本节的行号去找文件。

**证据**：
- `grep -rn "file_lock" tests/` → 仅 `test_approval_flow.py:291-308` 用 **spy 替换**验证「调用发生了」，**从未测试加锁行为本身**。
- 无任何并发竞争测试（`Thread`/`concurrent` 在 tests/ 中只命中 2 个无关文件）。
- 它是 `tracker.write_rows`（全量重读重写）的唯一并发保护——**注释自己写着**「后写覆盖先写导致静默丢数据」。

**同时发现两个实现缺陷**（经 `inspect.getsource` 核实）：

1. **`timeout` 参数在 Unix 上被完全忽略**（`filelock.py:44-46` 直接 `flock(LOCK_EX)` 阻塞；已实测 `timeout` 在该分支未被引用）。文档字符串也未提及平台差异。→ macOS/Linux 用户遇锁会**无限阻塞**，Windows 上却是 10 秒超时。
2. **Windows 只锁 1 字节**（`msvcrt.locking(fd, LK_NBLCK, 1)`），而 docstring 声称「锁粒度是整个文件」。当前调用方行为凑巧正确（`_release` 前有 `lseek(0)`），但契约与实际不符，是重构时的陷阱。

**处置**：补并发测试（双进程/双线程抢写同一 CSV，断言无丢行）；Unix 分支加 `LOCK_NB` 轮询以兑现 `timeout`；订正 docstring 的粒度描述。

---

### 🟡 P2-1 · 备份端点缺锁，固定暂存名在并发下互踩

**位置**：`web/backend/routers/system.py:247-265`

**证据**：
```python
tmp_path = os.path.join(snap_dir, atomicio.TMP_PREFIX + "backup.zip")   # :256 固定名
...
os.replace(tmp_path, target)                                            # :263
```
端点无 `file_lock`（对比：所有数据写端点均持锁）。两个并发备份共用同一暂存文件，可能产出损坏 zip 或 `os.replace` 撞车。

**准确描述**：`TMP_PREFIX` 是全局约定的临时前缀（`atomicio.py:20` 定义、`:92` 用于清理残留），用它作暂存名**符合约定**；缺陷是**把"原子写的暂存名"当成了互斥机制，却未强制互斥**。

**影响面**：限于快照产物本身，不损坏 `tracker.csv`（源是只读遍历）。也无任何备份并发测试（`grep -rln backup tests/` 为空）。

**处置**：加锁，或暂存名追加时间戳/随机后缀。

---

### 🟡 P2-2 · 两个复杂度热点

| 文件 | 规模 | 性质 |
|---|---|---|
| `tools/tracker.py` | 2515 行 / 97 函数 / **8+ 领域** | 单文件多职责。无超长函数（最长 150 行），但 `cmd_*`/`read_*`/`write_*` 七套近乎复制的家族。改一个新表要在同文件散落 10+ 处 |
| `web/backend/routers/progress.py` | 840 行 / **7 组资源** | 单文件多域聚合。单函数都短（最长 50 行），但 interviews/talks/mails/questions/contacts/offers 挤在一个 router 下 |

对比参照：`applications.py`（568 行/单域）、`jobs.py`（499 行/单域）分层合理——说明拆分方向已有先例。

**附带**：`web/backend/routers/resume.py` 把 `import re/urllib.error/resume_guard` 塞在 `:518-523`（文件中段），函数定义顺序断裂。**非运行时 bug**（Python 惰性全局查找），但易在重构时误删。

---

### 🟢 P3 · 文档表述缺陷（低）

**位置**：`CHANGELOG.md:6-11`

**问题**：头部声明「版本号用时间戳体系…**CHANGELOG 段名与该发布号同名**」，但现有段落全是旧的 `[0.3.0]`/`[0.3.2]`，tag 也是 `v0.3.2`。约定读起来像在描述现状，实际只对未来生效。

**判定**：这是**有意的历史保留**（不能改写已发布的 tag），约定本身没错，**缺的是"从哪个版本开始生效"的边界说明**。

**处置**：在版本号说明处补一句「本体系自 `v26.09.15.1` 起适用；`v0.3.2` 及以前的段名为历史编号，保留不改」。

---

## 五、审计中**未发现**问题的领域

如实记录（这些是项目的强项，不应为了凑数而制造问题）：

| 维度 | 结论 | 关键证据 |
|---|---|---|
| **路径穿越** | 干净。`safe_join`（`deps.py:147`）覆盖全部用户可控拼接点，实测 8 种穿越形态全部 BLOCK | `resume.py`/`library.py`/`jobs.py` 逐处核对；`progress.py:586-597` 还有一处**主动修复记录** |
| **workspace 参数** | 无漏传。后端全部 `tools/` 调用显式传 `ws`；`deps.py:98-104` 显式拒绝近名错拼参数（防静默回退 `personal`） | 含 `dashboard.py:214` 的并发注释 |
| **出网 TLS** | 严格。默认校验链+主机名；降级仅在显式 `JOBWS_IMAP_TLS=insecure`；内置 CA 回退**仍严格校验**；全不可用则**默认拒绝** | 全仓扫 `verify=False`/`CERT_NONE` 仅命中降级分支本体 |
| **错误处理** | 契约一致。**零裸 `HTTPException`**；95 个 `ApiError` 调用点全带 code；全局兜底把漏网异常转结构化响应 | `apierror.py` / `main.py:97-117` |
| **凭证** | 无硬编码。IMAP 凭证全部参数传入；`redact.py` 覆盖 provider key 与 imap password | `imap_fetch.py:9` 明确「不读写任何配置文件」 |
| **依赖** | 前后端 + Electron **0 漏洞**；无未声明的运行时依赖 | 见 §2.2 |
| **文档链接** | 门禁通过（`test_doc_links.py` 7 项） | 项目自带校验 |

---

## 六、按优先级排序的改进建议

| # | 优先级 | 动作 | 改动量 | 理由 |
|---|---|---|---|---|
| 1 | **P0** | 改掉 `jobs.py:158` 的真实公司名 | 1 行 | 唯一一处隐私泄漏，已推到公开仓库；开源项目零容忍 |
| 2 | **P1** | 归位 `[Unreleased]` 的 18 项到实际发布版本 | 文档 | 对外可信度；使用者无法判断升级目标 |
| 3 | **P1** | 给 `file_lock` 补并发测试 + 修 Unix `timeout` + 订正 docstring | 中 | 写安全的基石零覆盖；Unix 缺陷影响非 Windows 用户 |
| 4 | **P2** | 备份端点加锁（或暂存名加后缀） | 小 | 并发下产出损坏快照 |
| 5 | **P2** | 拆 `tracker.py`（保 facade 兼容既有 import） | 大 | 2515 行/8 域，已在拖累改动成本 |
| 6 | **P2** | 拆 `progress.py` 为按域 router | 中 | 7 组资源同构重复 |
| 7 | **P3** | 补版本号体系的生效边界说明 | 1 句 | 消除歧义 |

**建议执行顺序**：#1 立即做（一行，可单独提交）；#3 与 #4 同批（同属写安全，可共用并发测试脚手架）；#2 单独一批（纯文档）；#5/#6 属重构，需先与「当前批次计划」对表。

**不建议动**：依赖升级（已 0 漏洞）、CI/治理（配置扎实）、`resume.py` 的 import 位置（重构时顺手改即可，单独动收益低）。

---

## 七、未核实项

- **`[Unreleased]` 各项的实际发布版本**：需读 tag 历史与 Release notes 逐个回溯，本次只核实了「功能已实现」，未坐实「随哪个版本交付」。
- **`tools/report.py:303` `build_report`（181 行）**：全仓最长业务函数，本次未细读其内部复杂度。
- **备份并发问题**：未写复现脚本验证，结论基于代码静态推断（无锁 + 固定暂存名）。
