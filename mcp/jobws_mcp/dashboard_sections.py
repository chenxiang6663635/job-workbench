# -*- coding: utf-8 -*-
"""看板摘要的四个「逐行筛选」段（2026-10-09 从 `tools_readonly` 搬出）。

为什么独立成模块：`tools_readonly.py` 是登记过的水位文件（只许变小），而
`dashboard_summary()` 曾是 109 行的「编排 + 组装」（登记注释已点名拆分）。
筛选搬出来之后，编排函数只剩读数据与拼装，四段也各自可读、可单测。

口径：与 `web/backend/remind.py` 同源（upcoming / overdue 的中立判据），
静默用 `tracker.stale_days`、待推进用 `tracker.health_score`——**只搬不改行为**；
四个函数都是「行集 + 日期进、条目列表出」的纯函数（不读全局、不碰 IO）。
"""
from datetime import timedelta

from jobws_core import tracker


def upcoming(rows, today):
    """近 7 天待办（非终态）：`下次动作日期` 优先于 `截止日期`，每条只取一条。"""
    limit = today + timedelta(days=7)
    items = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() in tracker.TERMINAL_STAGES:
            continue
        for field, reason in (("下次动作日期", "下次动作"), ("截止日期", "截止")):
            when = tracker.parse_iso_date(row.get(field))
            if when and today <= when <= limit:
                items.append({
                    "id": (row.get("id") or "").strip(),
                    "公司": (row.get("公司") or "").strip(),
                    "岗位": (row.get("岗位") or "").strip(),
                    "date": when.isoformat(), "reason": reason,
                    "说明": (row.get("下次动作") or "").strip(),
                })
                break
    items.sort(key=lambda x: x["date"])
    return items


def overdue(rows, today):
    """已过截止日仍「待投」的（逾期只看待投——与看板同口径）。"""
    items = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() != "待投":
            continue
        dl = tracker.parse_iso_date(row.get("截止日期"))
        if dl and dl < today:
            items.append({
                "id": (row.get("id") or "").strip(),
                "公司": (row.get("公司") or "").strip(),
                "岗位": (row.get("岗位") or "").strip(),
                "截止日期": dl.isoformat(),
            })
    items.sort(key=lambda x: x["截止日期"])
    return items


def stale(rows, by_id, today, stale_days):
    """静默提醒（已读不回）：距最后一次推进超过阈值；基准日取 `stage_base_date`。"""
    items = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() in tracker.TERMINAL_STAGES:
            continue
        own = by_id.get((row.get("id") or "").strip(), [])
        days = tracker.stale_days(row, own, today)
        if days is None or days < stale_days:
            continue
        base = tracker.stage_base_date(row, own)
        items.append({
            "id": (row.get("id") or "").strip(),
            "公司": (row.get("公司") or "").strip(),
            "岗位": (row.get("岗位") or "").strip(),
            "当前阶段": (row.get("当前阶段") or "").strip(),
            "days": days, "since": base.isoformat() if base else "",
            "说明": (row.get("下次动作") or "").strip(),
        })
    items.sort(key=lambda x: -x["days"])
    return items


def pending(rows, by_id, today):
    """待推进：健康度非 ok，按严重度排序（与追踪表 health 同行同源，只做搬运）。"""
    items = []
    for row in rows:
        own = by_id.get((row.get("id") or "").strip(), [])
        health = tracker.health_score(row, own, today)
        if health["level"] in (None, "ok"):
            continue
        items.append({
            "id": (row.get("id") or "").strip(),
            "公司": (row.get("公司") or "").strip(),
            "岗位": (row.get("岗位") or "").strip(),
            "当前阶段": (row.get("当前阶段") or "").strip(),
            "level": health["level"], "reasons": health["reasons"],
            # hints 与 reasons 一一对应，是英文宿主拼句用的结构化形态（后端同款）
            "hints": health.get("hints", []),
        })
    items.sort(key=lambda x: tracker.HEALTH_LEVELS.index(x["level"]))
    return items
