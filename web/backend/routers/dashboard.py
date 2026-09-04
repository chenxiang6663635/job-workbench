# -*- coding: utf-8 -*-
"""看板统计。

复用 tools/report.py 的 count_by / parse_date（纯统计函数，无副作用）。
upcoming/overdue 的判定逻辑此处直接实现——report.build_report 里它与
Markdown 拼装耦合，本期不做提取重构（留作后续改进）。
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends

import tracker
from deps import workspace_dir
from report import count_by, parse_date, retrospective  # noqa: E402 - report 与 tracker 同目录

router = APIRouter(prefix="/api/dashboard")

# 阶段枚举以 tracker.py 为单一事实源，此处不复制第二份
STAGES = tracker.STAGES
TERMINAL = tracker.TERMINAL_STAGES


@router.get("")
def dashboard(ws: str = Depends(workspace_dir), stale_days: int = tracker.STALE_DAYS):
    rows = tracker.read_rows(ws)
    history = tracker.read_history(ws)
    total = len(rows)
    today = date.today()

    funnel = [{"stage": k, "count": v} for k, v in count_by(rows, "当前阶段", STAGES + TERMINAL)]
    by_direction = [{"key": k, "count": v} for k, v in count_by(rows, "方向")]
    by_batch = [{"key": k, "count": v} for k, v in count_by(rows, "批次")]

    active = sum(1 for r in rows if r.get("当前阶段") not in TERMINAL)

    # 近 7 天待办：活跃记录中，下次动作日期或截止日期落在 [today, today+7]
    limit = today + timedelta(days=7)
    upcoming = []
    for row in rows:
        if row.get("当前阶段") in TERMINAL:
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

    # 已过截止日仍待投
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

    # 静默提醒（已读不回）：非终态记录里，距最后一次推进超过阈值的
    # 基准日由 tracker.stage_base_date 决定（阶段变更 → 任意变更 → 投递日期），
    # 取不到基准日的记录不参与判定——没有依据就不该报警。
    stale = []
    for row in rows:
        if row.get("当前阶段") in TERMINAL:
            continue
        days = tracker.stale_days(row, history, today)
        if days is None or days < stale_days:
            continue
        base = tracker.stage_base_date(row, history)
        stale.append({
            "id": row.get("id", ""), "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""), "当前阶段": row.get("当前阶段", ""),
            "days": days, "since": base.isoformat() if base else "",
            "说明": row.get("下次动作", "") or "",
        })
    stale.sort(key=lambda x: -x["days"])

    return {
        "total": total,
        "active": active,
        "funnel": funnel,
        "byDirection": by_direction,
        "byBatch": by_batch,
        "upcoming": upcoming,
        "overdue": overdue,
        "stale": stale,
        "staleDays": stale_days,
        # 周期复盘：真实转化率（从时间线重建）、停留分布、失败归因。
        # 「我拒绝的 offer」单独统计，不算失败
        "retrospective": retrospective(rows, history, today),
    }
