# -*- coding: utf-8 -*-
"""到点提醒的轻端点（首发前收口批 笔 5；2026-09-24 扩「提前 N 天 + 已过期」）。

桌面壳在窗口就绪后、以及运行期内每几小时问一次"今天有什么到点的事"，然后发一条系统通知。
它要的是一份小、快、只读的答复，而不是把整个看板（漏斗 / 健康度 / 最近动作）拉一遍——
所以单开一个模块，而不是往 `dashboard.py`（水位文件，只许变小）里塞。

**判定复用看板那三个 helper**：`_upcoming_todos` / `_upcoming_talks` / `_overdue_pending`。
"什么算到点"只能有一处定义——两处各写一套的话，通知说今天到期、看板说没有，用户只能信一个。
跨模块读带下划线的名字是这个仓库里既有做法（`routers/progress/_shared.py` 同款）。

**两处是通知侧独有的**（都写在明面上，不是漏的）：

1. `days` = **提前几天开始提醒**（设置页 3/5/7，默认 3）：看板给的是 7 天窗口，这里
   按 `daysLeft` 再收一道——"提前 3 天"是通知的节奏，不是看板的；
2. **「下次动作日期」已过**这一类过期（"该做没做"）：看板 `_overdue_pending` 只认
   「待投 + 截止日期」；把这类合并进看板要动那个文件的结构，留待它下次真正改版时统一。

每条都带 `daysLeft`（负数 = 已过期几天）：主进程据此分档显示（已过期 N 天 / 今天到期 /
还剩 N 天），不再自己算日期。
"""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends

from jobws_core import tracker
from jobws_core.report import parse_date
from deps import workspace_dir

router = APIRouter(prefix="/api/reminders")

# 通知里列不了太多行：系统通知在 Windows 上大约三行可见，多给只会被折叠掉。
# 计数是完整的（`counts`），列表只给前几条，正文里说清"等 N 项"。
LIMIT = 5

# 「提前几天」的默认值与上限：设置页给 3 / 5 / 7 三档，越界一律夹回来——
# 这是个可独立调用的公开接口，不能因为一个查询参数把窗口撑到十年后。
DEFAULT_DAYS = 3
MAX_DAYS = 30


def _with_days_left(items, field, today, also_date=False):
    """给每条补 `daysLeft`（"还剩几天"，负数 = 已过期）。

    `also_date=True` 用于来源只有「截止日期」的条目：统一出一个 `date` 字段，
    主进程就不必按来源猜字段名（猜错只会静默少显示一行）。
    """
    out = []
    for item in items:
        when = parse_date(item.get(field))
        extra = {"date": when.isoformat()} if (also_date and when) else {}
        out.append(dict(item, **extra,
                        daysLeft=(when - today).days if when else 0))
    return out


def _overdue_todos(rows, today, seen):
    """非终态记录里「下次动作日期」已过的（"该做没做"）——通知侧比看板多的一类。"""
    items = []
    for row in rows:
        if row.get("当前阶段") in tracker.TERMINAL_STAGES:
            continue
        if row.get("id", "") in seen:
            continue
        when = parse_date(row.get("下次动作日期"))
        if when and when < today:
            items.append({
                "id": row.get("id", ""), "公司": row.get("公司", ""),
                "岗位": row.get("岗位", ""), "date": when.isoformat(),
                "reason": "下次动作", "说明": row.get("下次动作", "") or "",
            })
    return items


@router.get("/due")
def reminders_due(days: int = DEFAULT_DAYS, ws: str = Depends(workspace_dir)):
    """今天到点的事：提前 N 天内的待办 / 近 7 天宣讲会 / 已过期。

    `days` 只收"待办"这一类（宣讲会按自然临近、已过期无条件报）；越界夹到 1–MAX_DAYS。
    """
    from routers.dashboard import _overdue_pending, _upcoming_talks, _upcoming_todos

    today = date.today()
    window = max(1, min(days, MAX_DAYS))
    rows = tracker.read_rows(ws)

    todos = [t for t in _with_days_left(_upcoming_todos(rows, today), "date", today)
             if t["daysLeft"] <= window]
    talks = _with_days_left(_upcoming_talks(ws, today), "date", today)
    overdue = _with_days_left(_overdue_pending(rows, today), "截止日期", today,
                              also_date=True)
    overdue.extend(_with_days_left(
        _overdue_todos(rows, today, {x["id"] for x in overdue}), "date", today))
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
