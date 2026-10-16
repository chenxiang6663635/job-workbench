# -*- coding: utf-8 -*-
"""看板摘要（2026-10-09 / 2026-10-16 两次从 `tools_readonly` 搬出）。

为什么独立成模块：`tools_readonly.py` 是登记过的水位文件（只许变小），而
`dashboard_summary()` 曾是 109 行的「编排 + 组装」（登记注释已点名拆分）。
筛选搬出来之后，编排函数只剩读数据与拼装，四段也各自可读、可单测。

口径：与 `web/backend/remind.py` 同源（upcoming / overdue 的中立判据），
静默用 `tracker.stale_days`、待推进用 `tracker.health_score`——**只搬不改行为**；
四个函数都是「行集 + 日期进、条目列表出」的纯函数（不读全局、不碰 IO）。

2026-10-16 #307：编排函数也整体搬过来（读点转译占位 + 水位只许变小），
`tools_readonly` 留一行 re-export——调用方（tool_registry / resources / 测试）
零改动。读主表与时间线经 `paths.read_tracker_rows` / `read_tracker_history`
（归属判据 + 转译，见 paths.py）。
"""

from datetime import date, timedelta

from jobws_core import report, tracker

from . import paths


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
    # 同档文序与 CLI `tracker.sort_key` 同口径（id 升序）：只按档位 sort 时，
    # 同档多条的次序取决于 sort 稳定性 + 读表原序——三端各给一个「谁排前面」。
    items.sort(key=lambda x: (tracker.HEALTH_LEVELS.index(x["level"]), x["id"]))
    return items


def dashboard_summary(workspace, today=None, stale_days=None):
    """看板摘要（只读）：漏斗、近 7 天待办、已过截止、静默提醒、待推进与转化率。

    口径照抄 `web/backend/remind.py`（upcoming/overdue 的中立判据，2026-09-26 自
    `routers/dashboard.py` 搬出）与 `report.retrospective`：待办取「下次动作日期」优先于
    「截止日期」且只取一条；逾期只看「待投」；静默用 `tracker.stale_days`；健康度用
    `tracker.health_score`；转化率用「到达过」而非当前存量（否则早期阶段被高估）。

    `05_投递追踪` / `tracker.csv` / `history.csv` 经符号链接指向工作区外时返回
    ok=false + 可读理由（#307）——显式拒绝，不返回空摘要（那会把「读不到」误判成
    「没投过」）。与 `tools_readonly.list_applications` 同一条转译链。
    """
    rows, error = paths.read_tracker_rows(workspace)
    if error:
        return {"ok": False, "errors": [error]}
    history, error = paths.read_tracker_history(workspace)
    if error:
        return {"ok": False, "errors": [error]}
    # 索引一次：stale_days / health_score 逐行只收「该 id 的条目」——P 批治理，
    # 与后端 applications / dashboard 同款（此前每行各自全量遍历时间线）
    by_id = tracker.history_by_id(history)
    today = today or date.today()
    if stale_days is None:
        stale_days = tracker.STALE_DAYS
    terminal = tracker.TERMINAL_STAGES

    funnel = [{"stage": k, "count": v}
              for k, v in report.count_by(rows, "当前阶段", report.FUNNEL_ORDER)]
    by_direction = [{"key": k, "count": v} for k, v in report.count_by(rows, "方向")]
    active = sum(1 for r in rows if (r.get("当前阶段") or "").strip() not in terminal)

    retro = report.retrospective(rows, history, today, workspace)

    return {
        "workspace": workspace,
        "asOf": today.isoformat(),
        "initialized": paths.workspace_profile(workspace),
        "total": len(rows),
        "active": active,
        "funnel": funnel,
        "byDirection": by_direction,
        "upcoming": upcoming(rows, today),
        "overdue": overdue(rows, today),
        "stale": stale(rows, by_id, today, stale_days),
        "pending": pending(rows, by_id, today),
        "conversion": retro.get("conversion", []),
        "failure": retro.get("failure"),
        "declined": retro.get("declined"),
    }
