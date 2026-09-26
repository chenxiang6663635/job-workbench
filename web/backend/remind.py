# -*- coding: utf-8 -*-
"""到点提醒与看板共用的判定（"什么算到点"只能有一处定义）。

`routers/dashboard.py`（看板）与 `routers/reminders.py`（系统通知）都从这里取，
**两边不许各写一套**——通知说今天到期、看板说没有，用户只能信一个。

搬出的动机：这几个函数原本住在 `routers/dashboard.py` 里，而提醒端点要跨模块读
带下划线的私有名（能用，但"判据属于看板"这个前提不成立——它是两边共用的事实）。
中立模块让依赖方向变直：dashboard → remind ← reminders。

两类成员各有用处（看板不用的两个是通知侧要的，理由写在明面上，不是漏的）：

1. `with_days_left`：给每条补 `daysLeft`（负数 = 已过期几天）。主进程据此分档显示
   「已过期 N 天 / 今天到期 / 还剩 N 天」，不必在桌面壳里再算一遍日期；
2. `overdue_todos`：非终态里「下次动作日期」已过的（"该做没做"）。看板的
   `overdue_pending` 只认「待投 + 截止日期」——把这类并进看板要动它的输出结构，
   留待看板下次真正改版时统一（此处显式列出，避免被当成遗漏）。

窗口口径（近 7 天）以本模块为准；`days`（提前几天提醒）是**通知的节奏**，
在 `routers/reminders.py` 里收口。
"""

from __future__ import annotations

from datetime import timedelta

from jobws_core import tracker
from jobws_core.report import parse_date

# 近 7 天窗口：看板原口径；提醒端点在它之内再按用户设置的 days 收窄
WINDOW_DAYS = 7


def upcoming_todos(rows, today):
    """近 7 天待办：活跃记录中，下次动作日期或截止日期落在 [today, today+7]。"""
    limit = today + timedelta(days=WINDOW_DAYS)
    upcoming = []
    for row in rows:
        if row.get("当前阶段") in tracker.TERMINAL_STAGES:
            continue
        for field, reason in (("下次动作日期", "下次动作"), ("截止日期", "截止")):
            when = parse_date(row.get(field))
            if when and today <= when <= limit:
                upcoming.append({
                    "id": row.get("id", ""), "公司": row.get("公司", ""),
                    "岗位": row.get("岗位", ""), "date": when.isoformat(),
                    "reason": reason, "说明": row.get("下次动作", "") or "",
                })
                break
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def upcoming_talks(ws, today):
    """近 7 天宣讲会：`[today, today+7]` 内的活动，按时间升序。

    与 `upcoming_todos` 有两处不同：① 数据源是 `talks.csv`（活动笔记——它
    不入主表时间线，但在近 7 天里有它的位置）；② 「时间」列**带时刻**
    （`YYYY-MM-DD HH:MM`），而 `parse_date` 只认纯日期——先取日期前缀再解析，
    否则整条会被静默丢掉（这类"少给数据"比报错危险）。
    空时间的活动直接跳过：没有日期就无从谈「近 7 天」（与 `_sort_talks`
    把空时间排最后同一口径）。
    """
    limit = today + timedelta(days=WINDOW_DAYS)
    upcoming = []
    for row in tracker.read_talks(ws):
        raw = (row.get("时间") or "").strip()
        when = parse_date(raw[:10]) if raw else None
        if not when or not (today <= when <= limit):
            continue
        upcoming.append({
            "id": row.get("宣讲会id", ""), "公司": row.get("公司", ""),
            "时间": raw, "形式": row.get("形式", ""),
            "地点或链接": row.get("地点或链接", ""),
            "是否参加": row.get("是否参加", ""),
            "date": when.isoformat(),
        })
    upcoming.sort(key=lambda x: x["时间"])
    return upcoming


def overdue_pending(rows, today):
    """已过截止日仍待投。"""
    overdue = []
    for row in rows:
        if row.get("当前阶段") != "待投":
            continue
        dl = parse_date(row.get("截止日期"))
        if dl and dl < today:
            overdue.append({
                "id": row.get("id", ""), "公司": row.get("公司", ""),
                "岗位": row.get("岗位", ""), "截止日期": dl.isoformat(),
            })
    overdue.sort(key=lambda x: x["截止日期"])
    return overdue


def overdue_todos(rows, today, seen):
    """非终态记录里「下次动作日期」已过的（"该做没做"）——通知侧比看板多的一类。

    `seen` 是 id 集合（已由 `overdue_pending` 收走的），同一条记录不出现两次。
    """
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


def with_days_left(items, field, today, also_date=False):
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
