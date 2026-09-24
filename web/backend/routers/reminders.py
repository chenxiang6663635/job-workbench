# -*- coding: utf-8 -*-
"""到点提醒的轻端点（首发前收口批 笔 5）。

桌面壳在窗口就绪后、以及运行期内每几小时问一次"今天有什么到点的事"，然后发一条系统通知。
它要的是一份小、快、只读的答复，而不是把整个看板（漏斗 / 健康度 / 最近动作）拉一遍——
所以单开一个模块，而不是往 `dashboard.py`（275/300，只许变小）里塞。

**判定复用看板那三个 helper**：`_upcoming_todos` / `_upcoming_talks` / `_overdue_pending`。
"什么算到点"只能有一处定义——两处各写一套的话，通知说今天到期、看板说没有，用户只能信一个。
跨模块读带下划线的名字是这个仓库里既有做法（`routers/progress/_shared.py` 同款），
理由同上：宁可读私有名，也不要两份判据。
"""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends

from jobws_core import tracker
from deps import workspace_dir

router = APIRouter(prefix="/api/reminders")

# 通知里列不了太多行：系统通知在 Windows 上大约三行可见，多给只会被折叠掉。
# 计数是完整的（`counts`），列表只给前几条，正文里说清"等 N 项"。
LIMIT = 5


@router.get("/due")
def reminders_due(ws: str = Depends(workspace_dir)):
    """今天到点的事：近 7 天待办 / 近 7 天宣讲会 / 已过截止仍待投。"""
    from routers.dashboard import _overdue_pending, _upcoming_talks, _upcoming_todos

    today = date.today()
    rows = tracker.read_rows(ws)
    todos = _upcoming_todos(rows, today)
    talks = _upcoming_talks(ws, today)
    overdue = _overdue_pending(rows, today)

    return {
        "date": today.isoformat(),
        # 通知正文里带上工作区名：桌面壳发的是**默认工作区**之外的查询时，用户一眼能看出
        "workspace": os.path.basename(os.path.normpath(ws)) or "workspace",
        "counts": {"todos": len(todos), "talks": len(talks), "overdue": len(overdue)},
        "todos": todos[:LIMIT],
        "talks": talks[:LIMIT],
        "overdue": overdue[:LIMIT],
    }
