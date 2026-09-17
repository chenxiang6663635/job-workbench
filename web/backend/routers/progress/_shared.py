# -*- coding: utf-8 -*-
"""共享件：各写端点共用的 tracker.lock 路径。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

import os


from deps import DIR_TRACKING




def _lock_path(ws: str) -> str:
    path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
