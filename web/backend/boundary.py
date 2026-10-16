# -*- coding: utf-8 -*-
"""领域层归属异常 → HTTP 错误面的转译（#307 领域层读取与追加边界收口）。

领域层 tracker / jd_score 现在对「经符号链接 / junction 指向工作区外」的文件
显式拒绝（`workspace_read.WorkspaceBoundaryError`）——不返空列表、不写穿。
本模块把这一个异常类型映射成 400 + `path.escape`：与 `deps.safe_join` 的越界
分支**同一个错误码**，前端语言包不必新增键；文案由领域层给（面向用户、含路径）。

**不散进各 router**：tracker 读取被十来个端点共用（applications / dashboard /
reminders / progress/* / applist…），逐个 import 领域异常再 try/except 是第四份
漂移。注册在这里一次，且本文件只做转译、不 import 任何 router——无环。

退出码 / 错误码语义与另外两端对齐：CLI 退出码 2（`jobws.py` 主入口）、
MCP `ok=false` + `code=path.escape`（`tools_readonly` / `tools_writable`）。
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from jobws_core import workspace_read


def register(app):
    """把 WorkspaceBoundaryError 挂到 FastAPI 的异常处理器上（返回同形状 JSON）。"""

    @app.exception_handler(workspace_read.WorkspaceBoundaryError)
    async def _boundary_handler(request: Request, exc) -> JSONResponse:
        """链接读穿（symlink / junction 指向工作区外）：400 path.escape。

        与 `_api_error_handler` 同形状：detail 原样透出（前端按 error_code
        查语言包，查不到时直接显示它，不会退化成 err.xxx）。
        """
        return JSONResponse(status_code=400,
                            content={"detail": str(exc),
                                     "error_code": "path.escape"})
