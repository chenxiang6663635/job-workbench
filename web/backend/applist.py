# -*- coding: utf-8 -*-
"""投递列表的「取出之后」加工：健康度附加、排序、到期窗口筛选。

这几个函数都是**纯数据变换**——入参是已经读出来的 rows，不碰文件、不知道 HTTP，
与 `apierror.py` / `deps.py` 同级放着，是为了让 `routers/applications.py` 只留下
协议编排。拆出的直接原因是那里登记了 572 行的存量豁免水位，**只许变小**：到期
窗口筛选（P1 审计修复新增）若就地写在那儿，等于给一个已经超线的文件继续加码。
"""

from datetime import date, timedelta

from jobws_core import tracker

# 排序键。default 与 CLI 的 list 一致（终态沉底、按下次动作日期升序）
SORTS = ["default", "next", "score", "stale", "health"]

# 健康度排序优先级：越靠前越该先处理；None（终态）与 ok 沉底
HEALTH_ORDER = {"urgent": 0, "overdue": 1, "stale": 2, "ok": 3}


def _score(row):
    """评分在 CSV 里是字符串，转 int 失败按 0 处理（比让排序崩溃好）。"""
    try:
        return int(str(row.get("评分") or "").strip())
    except (TypeError, ValueError):
        return 0


def with_stage_days(rows, ws):
    """给每行附加 stageDays（当前阶段停留天数）与 health（健康度）。

    构造新 dict 返回，不写到行对象上——rows 会原样传回 write_rows，
    附加字段混进去虽会被 extrasaction 忽略，但让它根本不出现更安全。
    """
    entries = tracker.read_history(ws)
    # 索引一次：stale_days / health_score 都以「该 id 的条目」为输入，逐行传子集
    # 把 O(行数 × 条目数) 的全量扫描降为 O(条目数)（P 批治理，2026-09-21）
    by_id = tracker.history_by_id(entries)
    out = []
    for row in rows:
        item = dict(row)
        own = by_id.get((row.get("id") or "").strip(), [])
        days = tracker.stale_days(row, own)
        item["stageDays"] = days if days is not None else ""
        # 健康度与健康度理由：给理由不给黑箱分数，前端逐条照抄展示
        item["health"] = tracker.health_score(row, own)
        out.append(item)
    return out


def sort_items(items, sort):
    if sort == "health":
        # 严重度优先，同级里停留久的在前（越拖越该处理）
        items.sort(key=lambda r: (
            HEALTH_ORDER.get((r.get("health") or {}).get("level"), 3),
            -(r["stageDays"] if isinstance(r.get("stageDays"), int) else -1),
            r.get("id", "")))
        return items
    if sort == "score":
        items.sort(key=lambda r: (-_score(r), r.get("id", "")))
    elif sort == "stale":
        # 无基准日（空串）排在最后
        items.sort(key=lambda r: (-(r["stageDays"] if isinstance(r.get("stageDays"), int) else -1),
                                  r.get("id", "")))
    elif sort == "next":
        items.sort(key=lambda r: (0 if (r.get("下次动作日期") or "").strip() else 1,
                                  (r.get("下次动作日期") or ""), r.get("id", "")))
    else:
        items.sort(key=tracker.sort_key)
    return items


def due_within_rows(rows, days, today=None):
    """未来 N 天内到期（下次动作日期或截止日期落在 [今天, 今天+N]）。

    看板下钻用：与 dashboard 的统计口径保持一致。`today` 可注入是为了让
    「跨零点跑批处理」这类场景能被确定性地测到。
    """
    today = today or date.today()
    limit = today + timedelta(days=days)
    kept = []
    for row in rows:
        for field in ("下次动作日期", "截止日期"):
            when = tracker.parse_iso_date(row.get(field))
            if when and today <= when <= limit:
                kept.append(row)
                break
    return kept
