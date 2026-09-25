# -*- coding: utf-8 -*-
"""路径边界判定：realpath 归一 + 包含关系检查的**唯一实现**。

为什么独立成模块（2026-09-25 独立审计 P1-B）：
- Web 后端（`web/backend/deps.py`）与 MCP（`mcp/jobws_mcp/paths.py`）各自实现了
  一遍「工作区必须落在允许根内」：Web 侧是 `normpath + startswith`，MCP 侧后来
  自觉加严到了 `realpath`（其 docstring 写着「两处比后端更严」）——**双实现漂移**
  就此产生：数据根内的符号链接 / junction 在 Web 侧可以读穿到允许根之外。
- 本模块把「包含关系」收成一份：两边都 import 它，漂移点从「两处实现」变成
  「一处实现 + 两处调用」。

两个关键口径（一个来自 MCP 既有实现、一个来自审计）：
1. **两边都 realpath**：只归一化一侧，会在合法链接（例如被重定向的 `%APPDATA%`、
   用户把工作区做成 junction）上全量误判——所以比较的两边都走 `real()`；
2. **不允许「恰好等于根」**：把根当作目标等于放开「枚举根的直属子项」，
   Web 与 MCP 既有实现都显式排除根自身（`deps.py` 的 `_inside_allowed_roots`
   与 `paths.py` 的 `resolve_workspace`）。

比较用 `commonpath` 而不是 `startswith`：字符串前缀的经典误判是
`C:\\a\\bc` 以 `C:\\a\\b` 为前缀却不在其内部——commonpath 一次解决。
"""

from __future__ import annotations

import os


def real(path):
    """realpath + normpath：展开符号链接 / junction 后的稳定比较形态。

    对**不存在**的路径同样可用（Python 的 realpath 不要求路径存在；中间段的
    链接会被展开，末段不存在时按字面返回）——建新目录前的判定因此不会误拒。
    """
    return os.path.normpath(os.path.realpath(path))


def _same(a, b):
    """同一路径判定：realpath 后按文件系统的大小写口径比较。"""
    return os.path.normcase(real(a)) == os.path.normcase(real(b))


def is_within(child, root):
    """`child` 是否落在 `root` **内部**（不含 root 自身、展开链接后判定）。

    fail-closed：跨盘符（commonpath 抛 ValueError）一律 False。
    """
    if _same(child, root):
        return False
    try:
        common = os.path.commonpath([real(child), real(root)])
    except ValueError:
        return False          # 不同盘符 / 绝对与相对混用
    return os.path.normcase(common) == os.path.normcase(real(root))


def is_within_or_equal(child, root):
    """`child` 是 `root` 自身、或落在其内部（展开链接后判定）。

    与 `is_within` 的唯一区别：**允许等于根**。浏览与拼接类场景的既有语义
    就是如此——`ro_files.inside` 要看素材库根自身（`_section_base` 拿工作区根
    做锚点）、`deps.safe_join(ws)` 无片段拼接时返回的就是工作区本身；收编时
    保持最小行为变化，语义差异用一个显式函数名承载，而不是散在各调用点。
    """
    return _same(child, root) or is_within(child, root)


def within_any(child, roots):
    """`child` 是否落在任一允许根内部。"""
    return any(is_within(child, r) for r in roots)


def strictly_within_any(child, roots):
    """`child` 落在任一根内部、**且不等于任何一个根**（工作区解析的双重条件）。

    为什么单独一个函数：「等于根自身」要按**全体**根排除。数据根 ⊆ 应用根时
    （`JOBWS_DATA_DIR` 指向仓库内目录），数据根本身满足「在应用根内部」——
    只按单根判定会 200 服务「所有工作区的父目录」（独立审查 MINOR-1 的形态）。
    `is_within` 只排除「等于同一个根」，跨根相等（等于根 A、又恰在根 B 内）
    要靠这里兜住（test_containment 有该拓扑的锁死用例）。
    """
    if any(_same(child, r) for r in roots):
        return False
    return any(is_within(child, r) for r in roots)


def escape_reason(name):
    """`name` 作为「根下相对路径」是否含越界写法；返回原因短语或 None。

    三类拒绝（`mcp/jobws_mcp/paths.py` 已总结，这里升级为共享实现）：
    ① 绝对路径（`os.path.join` 会把它当成新根）；
    ② `..` 段（翻出允许根）；
    ③ 盘符相对路径（`C:foo`：`isabs()` 为 False、不含分隔符，join 时却重置根——
       2026-09-23 实测 `join(ws, "C:foo")` 直接得到 `C:foo`，会去扫盘根）。

    只回**原因短语**，完整错误文案由调用方拼（两侧既有文案不同，各自保留）。
    """
    raw = (name or "").strip()
    if not raw:
        return "为空"
    normalized = raw.replace("\\", "/")
    if os.path.isabs(raw) or os.path.isabs(normalized):
        return "是绝对路径"
    segments = [seg for seg in normalized.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in segments):
        return "含 .. 段"
    if any(":" in seg for seg in segments):
        return "含盘符"
    return None
