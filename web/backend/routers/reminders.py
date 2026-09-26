# -*- coding: utf-8 -*-
"""到点提醒的轻端点（首发前收口批 笔 5；2026-09-24 扩「提前 N 天 + 已过期」）。

桌面壳在窗口就绪后、以及运行期内每几小时问一次"今天有什么到点的事"，然后发一条系统通知。
它要的是一份小、快、只读的答复，而不是把整个看板（漏斗 / 健康度 / 最近动作）拉一遍——
所以单开一个模块，而不是往 `dashboard.py`（水位文件，只许变小）里塞。

**判定全部来自 `remind.py`**（中立模块，看板与通知共用）：
`upcoming_todos` / `upcoming_talks` / `overdue_pending` / `overdue_todos` / `with_days_left`。
"什么算到点"只有那一处定义——两处各写一套的话，通知说今天到期、看板说没有，
用户只能信一个。（这几个函数原住在 `dashboard.py`，跨模块读下划线私有名；本批搬到
中立模块，依赖方向改为 dashboard → remind ← reminders，两端的 import 都从那里取。

**这里是通知侧独有的一条**（写在明面上，不是漏的）：`days` = **提前几天开始提醒**
（设置页 3/5/7，默认 3）——看板给的是 7 天窗口，这里按 `daysLeft` 再收一道；
"提前 3 天"是通知的节奏，不是看板的。

每条都带 `daysLeft`（负数 = 已过期几天）：主进程据此分档显示（已过期 N 天 / 今天到期 /
还剩 N 天），不再自己算日期。
"""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends

from jobws_core import tracker
from deps import workspace_dir
from remind import (
    overdue_pending, overdue_todos, upcoming_talks, upcoming_todos, with_days_left,
)

router = APIRouter(prefix="/api/reminders")

# 通知里列不了太多行：系统通知在 Windows 上大约三行可见，多给只会被折叠掉。
# 计数是完整的（`counts`），列表只给前几条，正文里说清"等 N 项"。
LIMIT = 5

# 「提前几天」的默认值与上限：设置页给 3 / 5 / 7 三档，越界一律夹回来——
# 这是个可独立调用的公开接口，不能因为一个查询参数把窗口撑到十年后。
DEFAULT_DAYS = 3
MAX_DAYS = 30


@router.get("/due")
def reminders_due(days: int = DEFAULT_DAYS, ws: str = Depends(workspace_dir)):
    """今天到点的事：提前 N 天内的待办 / 近 7 天宣讲会 / 已过期。

    `days` 只收"待办"这一类（宣讲会按自然临近、已过期无条件报）；越界夹到 1–MAX_DAYS。
    """
    today = date.today()
    window = max(1, min(days, MAX_DAYS))
    rows = tracker.read_rows(ws)

    todos = [t for t in with_days_left(upcoming_todos(rows, today), "date", today)
             if t["daysLeft"] <= window]
    talks = with_days_left(upcoming_talks(ws, today), "date", today)
    overdue = with_days_left(overdue_pending(rows, today), "截止日期", today,
                             also_date=True)
    overdue.extend(with_days_left(
        overdue_todos(rows, today, {x["id"] for x in overdue}), "date", today))
    overdue.sort(key=lambda x: x["daysLeft"])

    return {
        "date": today.isoformat(),
        # 通知正文里带上工作区名：桌面壳发的是**默认工作区**之外的查询时，用户一眼能看出
        "workspace": os.path.basename(os.path.normpath(ws)) or "workspace",
        "window": window,
        "counts": {"todos": len(todos), "talks": len(talks), "overdue": len(overdue)},
        "todos": todos[:LIMIT],
        "talks": talks[:LIMIT],
        "overdue": overdue[:LIMIT],
    }
