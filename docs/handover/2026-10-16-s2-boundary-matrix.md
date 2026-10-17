# S2 边界矩阵（2026-10-16 闭环）

> 交接包 §四 G1 门内第 2 项「S2 边界矩阵 — 待做」的交付。原措辞是"补 UNC、绝对路径、
> 混合分隔符、URL 编码路径、junction/reparse point 的判据，以及 TOCTOU 的如实说明"。
> 实测结论：**五类里四类早已有用例**（被 #300/#308 等批顺带覆盖），真正缺的只有
> **UNC 一类**；TOCTOU 按要求写成"如实说明"而不是测试。

## 一、覆盖矩阵（扫描法，精确到测试函数）

扫描方式：对 `tests/` 与 `mcp/tests/` 按测试函数聚合各类边界的出现位置（脚本
`.codebuddy/tmp/s2_scan.py`，一次性工具不入库）。

| 边界类 | 判据层（`containment.escape_reason`） | 用例覆盖 | 代表用例 |
|---|---|---|---|
| **UNC**（`\\server\share\x`） | ✅ 拒（Windows 上判"是绝对路径"） | ❌ **零覆盖 → 本轮补** | `tests/test_dedup_parity.py::test_safe_join_rejects_unc_on_windows`、`mcp/tests/test_paths_escape.py::test_resolve_within_workspace_rejects_unc_on_windows` |
| **绝对路径**（`/etc/passwd` 等） | ✅ 拒 | ✅ 14 条用例 | `test_containment.py::test_escape_reason_windows_absolute_is_flagged`、`test_library_api.py::test_content_rejects_traversal` |
| **混合分隔符**（`a\..\b` 等） | ✅ 拒（先归一化再判 `..` 段） | ✅ 11 条用例 | `test_dedup_parity.py::test_safe_join_and_escape_reason_agree_on_the_shared_classes` |
| **URL 编码**（`%2e%2e/`） | ✅ 拒（不解码即按字面判，`%2e` 不是 `..`；解码由上层不做，故不产生越界） | ✅ 1 条用例 | `test_prep_api.py::test_content_rejects_traversal`（L139-140）、`test_library_api.py::test_content_rejects_traversal` |
| **junction / reparse / symlink** | ✅ 拒（realpath 归属判定） | ✅ 39 条用例 | `mcp/tests/test_resources_prompts.py::test_job_text_rejects_file_symlink_escape`、`test_containment.py::test_symlink_inside_is_accepted` |
| **TOCTOU**（判定与使用之间的窗口） | 见 §三 | **不假装有覆盖** | — |

平台口径：UNC 与盘符相对的用例都是 `skipif(os.name != "nt")`——posix 上它们不是
绝对路径（`C:foo` 甚至是合法文件名），这是**有意的平台差异**，由
`test_safe_join_accepts_drive_like_name_on_posix` 显式钉住。

## 二、本轮新增（覆盖缺口，不是缺陷）

UNC 一类判据层**早就拒**（`escape_reason` 返回"是绝对路径"），缺的只是钉子。补了两颗：

- Web 侧：`tests/test_dedup_parity.py` 加 `test_safe_join_rejects_unc_on_windows`
  （断言 `safe_join` 抛 `path.illegalSegment`，与判据层同源）；
- MCP 侧：`mcp/tests/test_paths_escape.py` 加 `test_resolve_within_workspace_rejects_unc_on_windows`
  （断言文案含"绝对路径"——措辞是宿主能看懂的关键词，被既有网钉住）。

两处均 Windows-only；本机实测 Web 12 passed / MCP 5 passed。

## 三、TOCTOU 的如实说明（不写成测试，因为不能）

**窗口真实存在**：路径先经判据（realpath 归属 + 段规则）再被打开/读取，两步之间
本地进程可以把"已验证的目录"换成一个指向外部的链接。本仓**不声称消除**这个窗口。

**为什么不修**：本仓的威胁模型是「本地单用户 + 材料不可信」（用户导入/拖进来的
工作区可能带恶意链接），不是「并发的本地攻击者」。彻底消除需要"打开后校验"
（`O_NOFOLLOW` / 句柄级归属复核），要改读写原语的签名与全部调用点，收益与当前
威胁模型不匹配，且会动发行冻结前的主链路。

**现有缓解**（降低而非消除）：
- 判据层 realpath 解析：换链发生在**判定前**会被抓到，只有判定后的窗口有效；
- 写路径走 `workspace_io` 原子写 + `filelock` 锁（锁路径单源，`test_lock_literals.py` 守着）；
- 两段式写入（`approval`）：预览与落盘之间令牌绑定目标目录。

**列为已知限制**：若威胁模型升级（多人共用一台机器、或工作区来自不受共享方），
再评估句柄级校验；在那之前不接受"已消除 TOCTOU"的表述。

## 四、结论

**S2 边界矩阵项关闭**：五类边界全部有判据 + 用例（UNC 由本轮补齐），TOCTOU 按
"如实说明 + 已知限制"成文。G1 门内该项的退出判据（"UNC、绝对路径、混合分隔符、
URL 编码、junction/reparse 的判据 + TOCTOU 说明"）已满足。
