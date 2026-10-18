# CodeQL 债务姿态与收口路径（2026-10-17）

> 回答两个问题：**这 194 条告警是什么**、**怎么收**。
> 文中的"机制结论"都是实测或查证过的，不是推测——每条附判据，避免下次重复试错。

## 一、这 194 条是什么

不是"发现了 194 个新问题"，而是 **2026-10-12 接入 CodeQL（#294）时首扫把历史存量一次倒出**：
178 条在接入当天创建，10-16 的批次又 +16。**0 条曾 dismissed**——S4 门禁只拦"新增"，
所以存量既不阻断、也从未分诊。

| 规则 | 条数 | 说明 |
|---|---:|---|
| `py/path-injection` | 182 | 见 §二 |
| `py/stack-trace-exposure` | 5 | 错误消息把异常/路径原文回给前端（medium） |
| `py/polynomial-redos` | 3 | 正则跑用户长文本 |
| `py/command-line-injection` | 1 | **#194**（critical）→ 已在 #325 结构性修复，告警未消 |
| `py/full-ssrf` | 1 | **#2**（critical）→ 已在 #326 修复，告警未消 |
| `py/incomplete-url-substring-sanitization` / `js/…` | 1 + 1 | `startswith("https://")` 当校验 |

集中度（不是"到处都是"）：`routers/resume.py` 34、`routers/system.py` 17、`routers/jobs.py` 15、
`dataroot_migrate.py` 14、`jd_gap.py` 13、`workspace_io.py` 12。

## 二、为什么 94% 是 `path-injection`

这是**架构与静态分析的错位**，不是"代码烂"：

1. 本产品是**本地优先工具**：工作区路径、`--out` 输出目录、快照/迁移/导出目录，**本来就是
   用户给的路径**——读写它们就是功能本身。
2. CodeQL 把 argparse / 环境变量 / HTTP 参数一律当 tainted source，于是任何
   `open()` / `os.path.join` / `shutil.*` / `os.makedirs` 都命中。
3. 项目**有自己的防护原语**（`containment.escape_reason`、`deps.safe_join`、
   `workspace_read` 的有界读 + realpath 归属判定、`outbound.assert_public_url`），
   但 **CodeQL 不认识它们**——所以"其实防住了"的代码照样被报。

## 三、三条收口机制的实测结论（重要，别再试错）

| 机制 | 结论 | 判据 |
|---|---|---|
| **data extension / model pack 声明 sanitizer** | ❌ **Python 不支持** | `github/codeql` 的 `python/ql/lib/ext/` 只有一个 `default-threat-models-fixup.model.yml`——没有 Java 那种 MaD（source/sink/summary/barrier）扩展面 |
| **行内抑制 `# codeql[py/…]`** | ❌ **对 Python 无效** | #325 实测（2026-10-17）：把注释写在被标记的 4 行**同一行**上并推送，CodeQL 仍报同样的 4 条（`tools/pdf_print.py:100/104/125/126`） |
| **自定义 QL 查询包（覆写 `PathInjectionCustomizations.qll`）** | ✅ 技术上可行，但**本机无法验证** | Python 确实有 `PathInjectionCustomizations.qll` / `ServerSideRequestForgeryCustomizations.qll` 钩子；但本机无 CodeQL CLI，需下载约 500MB bundle 才能编译与迭代，否则只能靠 CI 反复试 |
| **dismiss（PR 上的新告警）** | ❌ **机制上做不到** | #325 实测（2026-10-18）：那 4 条**不在仓库告警列表里**（`?ref=refs/pull/325/head` 与 `refs/heads/fix/command-line-injection` 均返回 0 条，全仓搜 `pdf_print` 也没有）——PR 分析结果没有告警编号，**没有可 dismiss 的对象**。dismiss 只对已落在分支/默认分支上的告警有效 |
| **`query-filters` 按路径排除** | ❌ **不支持** | `query-filters` 只匹配**查询元数据**（id / tags / severity / precision），`paths` 不是元数据；官方文档的替代方案只有 `paths-ignore`（作用于**全部**查询） |

> 另注：`py/path-injection` 的 sink 只要"写/读用户选的路径"就存在，**无法靠重构归零**。
> 例如 PDF 渲染里"把 PDF 写到 `--out`"就是功能定义，最多把 4 个 sink 压到 1~2 个，仍然会被判"新增"。
>
> **Python 的扩展点也不是 `Sanitizer` 类**：`PathInjectionCustomizations.qll` 的注释明写
> *"we do not expose a Sanitizer class, and instead you should extend `Path::PathNormalization::Range`
> and `Path::SafeAccessCheck::Range` from `semmle.python.Concepts`"* —— 那是带状态机的概念建模，
> 不是"加一个类名"就能收的活。

## 四、剩下的路径（都带代价，需要决策）

| 路径 | 做法 | 成本 | 风险 | 可逆 |
|---|---|---|---|---|
| **B. 自定义 QL 包（扩展 `Path::SafeAccessCheck::Range`）** | 下载 CodeQL bundle（实测 **666 MB**、可下载，D 盘余量充足）→ 写 concept 扩展包 → 接进 `codeql.yml` → 本地 `database create/analyze` 验证 | 数小时 | QL 状态机写对不易；但**只影响该 PR**，可反复试 | ✅ 删包即回退 |
| **C′. `paths-ignore: tools/pdf_print.py`** | 在 codeql 配置里把**该文件**排除出分析 | 分钟级 | **会把这一个文件的全部规则一起关掉**——包括刚修好的命令行注入规则。而它正是曾出过 #194 的那个文件 | ✅ 删一行即回退 |
| ~~A. dismiss~~ | —— | —— | —— | **机制不允许（见 §三）** |

**建议**：#194 的代码修复已经**验证有效**（PR 分析里命令行注入 0 条），而它当前**不可利用**
（argv 只剩常量）——所以**不值得为了"合并"去关掉一个文件的全部扫描**（C′）。
本 PR 保持打开、绿色但被门禁拦，等 B 落地后自然解锁；**C′ 不建议**。

## 五、当前状态

| 项 | 状态 |
|---|---|
| #194 命令行注入 | 代码已结构性修复（`tools/pdf_print.py`，argv 只剩常量），**PR 分析里该规则已 0 条**；但 #325 因 4 条新 path-injection 被门禁拦，**未合并** |
| #2 SSRF | 已修复并合并（#326）；**告警 open**（CodeQL 不认 `assert_public_url` 为 sanitizer） |
| 其余 182 + 10 条 | 未分诊；其中至少 `routers/system.py` 的 `open_folder` 已核实为**安全范式**（预设键白名单 + 字面量可执行文件），属"静态分析看不到白名单"的典型 |
| 门禁影响 | S4 只拦新增：**碰这些文件的 PR 会被拦**（#325 已两次撞上：一次是新文件、一次是断言漂移） |

## 六、下一步（待决策）

1. **B 或 C′**（见 §四）——A 已被机制否掉；
2. 若选 B，先做一件事：**逐类核对 182 条里哪些真的防住了**（按 §二 的四条原语分类），
   否则 concept 扩展会连真缺口一起掩盖；
3. `stack-trace-exposure` 的 5 条（medium）与 redos 3 条可以走正常修复路径，不需要决策
   ——它们是"改代码就行"的那一类，可另开一批 20 分钟收掉。
