# -*- coding: utf-8 -*-
"""共享件：各写端点共用的 tracker.lock 路径。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

import os


from apierror import ApiError
from deps import DIR_TRACKING




def _lock_path(ws: str) -> str:
    """tracker.lock 路径——批 8 起走共享原语（锁名只在 workspace_io 定义一处）；
    建目录仍由本函数负责（原语是纯计算，不碰文件系统）。"""
    from jobws_core import workspace_io

    path = workspace_io.lock_path(ws, "tracking")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def delete_preview_response(operation, errors, plan, error_code, error_message, ws):
    """删除类预览端点的统一出口：错误 → 400 结构化；成功 → 令牌 + 差异表。

    2026-09-21 批 D：六个删除预览端点（五张从表 + 投递主表）共用——响应形状
    与错误投影只在这一处定义，各端点只负责调各自的领域预览函数与给错误文案
    （与领域层"同一份实现"的纪律同源：没有第二份就会有失配的机会）。
    """
    if plan is None:
        raise ApiError(400, error_code, error_message, reason="；".join(errors))
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到
    result = approval.preview(operation, ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}
