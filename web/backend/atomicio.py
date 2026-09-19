# -*- coding: utf-8 -*-
"""原子写（薄转发）——实现已收敛到 tools/workspace_io.py（批 8，四端共享）。

历史：本模块曾内联一份实现（先写临时文件 → fsync → os.replace）。批 8 把
CLI（tools/）、MCP（mcp/jobws_mcp/）与桌面端后端三处同款实现收敛到
`tools/workspace_io.py`，并给 os.replace 补了 Windows 共享冲突重试
（目标被 Excel 打开 / 杀软扫描时抛 PermissionError 的标准解法）。

这里保留同名导出：既有 `import atomicio` 的调用方（routers/system、resume、
provider、jobs、imap）零改动。

依赖：tools/ 需在 sys.path —— web/backend/main.py 启动时已注入（与 CLI、MCP 同法）。
"""

from __future__ import annotations

from jobws_core.workspace_io import (
    TMP_PREFIX,
    atomic_write_bytes,
    atomic_write_csv,
    atomic_write_text,
    cleanup_tmp,
)

__all__ = [
    "TMP_PREFIX",
    "atomic_write_text",
    "atomic_write_bytes",
    "atomic_write_csv",
    "cleanup_tmp",
]
