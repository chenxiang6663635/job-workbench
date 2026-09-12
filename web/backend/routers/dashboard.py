# -*- coding: utf-8 -*-
"""看板统计。

复用 tools/report.py 的 count_by / parse_date（纯统计函数，无副作用）。
upcoming/overdue 的判定逻辑此处直接实现——report.build_report 里它与
Markdown 拼装耦合，本期不做提取重构（留作后续改进）。
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends

import jd_score
import tracker
from deps import DIR_JOBS, safe_join, workspace_dir
from report import count_by, parse_date, retrospective  # noqa: E402 - report 与 tracker 同目录
from routers import jobs as jobs_router  # noqa: E402 - 关联口径复用，不写第二份

router = APIRouter(prefix="/api/dashboard")

# 阶段枚举以 tracker.py 为单一事实源，此处不复制第二份
STAGES = tracker.STAGES
TERMINAL = tracker.TERMINAL_STAGES

# 「高分」的档位下界**派生自** jd_score.THRESHOLDS，不是这里新发明的数字：
# 取「建议投」这一档的下界（含）以上。改档位只需改 jd_score 一处，这里跟着变。
#
# 兜底不是防御性编程：档位名一旦被改，`_HIGH_BOUNDS` 就是空序列，min() 抛
# ValueError，而看板的 import 在 main 的 router 列表里靠前——整个后端起不来。
# 宁可退化成「第二档下界」这种错得不离谱的值，也不要让全站打不开。
_HIGH_TIERS = ("强烈建议投", "建议投")
_HIGH_BOUNDS = [lo for lo, _hi, tier, _a in jd_score.THRESHOLDS
                if tier in _HIGH_TIERS]
if _HIGH_BOUNDS:
    HIGH_SCORE_FLOOR = min(_HIGH_BOUNDS)
elif len(jd_score.THRESHOLDS) > 1:
    HIGH_SCORE_FLOOR = jd_score.THRESHOLDS[1][0]
else:
    HIGH_SCORE_FLOOR = jd_score.THRESHOLDS[0][0]

# 投递状态 → 输出键（前端图表用）
_STATE_KEY = {"未投递": "unapplied", "流程中": "active", "已终态": "terminal"}


def tier_of(score):
    """评分 → 档位名。直接复用 `jd_score.verdict`：边界与越界回退都只有一处定义。"""
    return jd_score.verdict(score)[0]


def job_pool_overview(ws):
    """岗位池视角的两组统计：高分未投清单 + 评分档位 × 投递状态分布。

    匹配键（目录名）与终态口径全部复用 jobs_router——看板与岗位池对同一个岗位
    必须给出同一个结论，各写一套判据迟早会互相矛盾。

    未评分的岗位**不参与**分布图：「还没评」不等于最低档，塞进「不投」那一档
    是在替用户下结论。
    """
    base = safe_join(ws, DIR_JOBS)
    names = []
    if os.path.isdir(base):
        names = [n for n in sorted(os.listdir(base))
                 if n and not n.startswith("_")
                 and os.path.isdir(os.path.join(base, n))]

    index = jobs_router._applications_by_key(ws) if names else {}
    dist = {tier: {"unapplied": 0, "active": 0, "terminal": 0}
            for _lo, _hi, tier, _a in jd_score.THRESHOLDS}
    unapplied_high = []

    for name in names:
        card = jobs_router._parse_card(ws, os.path.join(DIR_JOBS, name))
        if not (card and card.get("consistent") and card.get("total") is not None):
            continue
        company, role = jobs_router._split_dir(name)
        state = jobs_router._apply_state(index.get(tracker.dedup_key(company, role)))
        tier = tier_of(card["total"])
        dist[tier][_STATE_KEY[state]] += 1
        if state == "未投递" and card["total"] >= HIGH_SCORE_FLOOR:
            display_company, display_role = jobs_router._job_company_role(ws, name)
            unapplied_high.append({
                "dir": name,
                "company": display_company,
                "role": display_role,
                "score": card["total"],
                "level": card.get("level"),
            })

    unapplied_high.sort(key=lambda x: -x["score"])
    score_by_state = [dict({"tier": tier}, **dist[tier])
                      for _lo, _hi, tier, _a in jd_score.THRESHOLDS]
    return unapplied_high, score_by_state


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

    # 待推进（第二批）：健康度非 ok 且非终态的记录，按严重度排序。
    # 与追踪表 health 排序同源（tracker.health_score），看板只做搬运——
    # 两处各写一套判据迟早会给出互相矛盾的结论。
    pending = []
    for row in rows:
        health = tracker.health_score(row, history, today)
        if health["level"] in (None, "ok"):
            continue
        pending.append({
            "id": row.get("id", ""), "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""), "当前阶段": row.get("当前阶段", ""),
            "level": health["level"], "reasons": health["reasons"],
        })
    pending.sort(key=lambda x: tracker.HEALTH_LEVELS.index(x["level"]))

    unapplied_high, score_by_state = job_pool_overview(ws)

    return {
        "total": total,
        "active": active,
        "funnel": funnel,
        "byDirection": by_direction,
        "byBatch": by_batch,
        "upcoming": upcoming,
        "overdue": overdue,
        "stale": stale,
        "pending": pending,
        "staleDays": stale_days,
        # 周期复盘：真实转化率（从时间线重建）、停留分布、失败归因。
        # 「我拒绝的 offer」单独统计，不算失败
        # 显式传 workspace：关键词表按工作区读取，并发下不能依赖全局
        "retrospective": retrospective(rows, history, today, ws),
        # 岗位池视角（B3）：这两项与「有没有投递记录」无关，岗位池有内容就有值
        "unappliedHigh": unapplied_high,
        "scoreByState": score_by_state,
    }
