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

> 另注：`py/path-injection` 的 sink 只要"写/读用户选的路径"就存在，**无法靠重构归零**。
> 例如 PDF 渲染里"把 PDF 写到 `--out`"就是功能定义，最多把 4 个 sink 压到 1~2 个，仍然会被判"新增"。

## 四、三条可选路径（需要决策）

| 路径 | 做法 | 成本 | 风险 | 可逆 |
|---|---|---|---|---|
| **A. 带理由 dismiss**（推荐用于 #325 的 4 条 + #2） | `PATCH /code-scanning/alerts/{n}`，reason=`won't fix` + 评论文本写明威胁模型 | 分钟级 | 首次 dismissal 立政策先例；**记录可见可审** | ✅ 可 reopen |
| **B. 自定义 QL 包** | 下载 CodeQL bundle → 写 override pack → `--additional-packs` 接进 `codeql.yml` → 本地验证后推 CI | 数小时 + 500MB | 若 hook 路径/类名不符会反复红 CI（只影响该 PR，不污染 main） | ✅ 删包即回退 |
| **C. 按文件排除规则**（`query-filters` exclude） | 在 codeql 配置里排除指定文件 | 分钟级 | **最差**：会连带隐藏该文件未来真正的漏洞 | ✅ 但错误会被静默吞掉 |

**建议**：先 A（把 #325 与 #2 的 2+4 条显式接受、留痕、解锁），把 B 作为独立课题
（它能一次性收掉"确实防住了"的一大批，并让未来的 PR 不再因为碰这几个文件被拦）；
C 不建议。

## 五、当前状态

| 项 | 状态 |
|---|---|
| #194 命令行注入 | 代码已结构性修复（`tools/pdf_print.py`，argv 只剩常量）；**告警 open**，卡在 #325（4 条新 path-injection） |
| #2 SSRF | 已修复并合并（#326）；**告警 open**（CodeQL 不认 `assert_public_url` 为 sanitizer） |
| 其余 182 + 10 条 | 未分诊；其中至少 `routers/system.py` 的 `open_folder` 已核实为**安全范式**（预设键白名单 + 字面量可执行文件），属"静态分析看不到白名单"的典型 |
| 门禁影响 | S4 只拦新增：**碰这些文件的 PR 会被拦**（#325 已两次撞上） |

## 六、下一步（待决策）

1. **A 或 B**（见 §四）——需要明确选择；
2. 若选 B，先做一件事：**逐类核对 182 条里哪些真的防住了**（按 §二 的四条原语分类），
   否则 QL 包的 sanitizer 声明会连真缺口一起掩盖；
3. `stack-trace-exposure` 的 5 条（medium）与 redos 3 条可以走正常修复路径，不需要决策
   ——它们是"改代码就行"的那一类，可另开一批 20 分钟收掉。
