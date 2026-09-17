# -*- coding: utf-8 -*-
"""主表（投递记录）：读写、变更时间线派生、健康度与静默天数。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import logging
import os
import sys

from datetime import date, datetime

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (TERMINAL_STAGES, _atomic_write_csv, csv_path, parse_iso_date, resolve_ws)
from ._schema import (FIELDS, HEALTH_LEVELS, HISTORY_FIELDS, HISTORY_FILE, HISTORY_TRACKED, STALE_DAYS, URGENT_DAYS)



def history_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", HISTORY_FILE)



def read_history(workspace=None, app_id=None):
    """读取时间线。按写入顺序（时间升序）返回，app_id 非空时只返回该记录。"""
    path = history_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("id") or "").strip() == app_id]
    return rows



def append_history(entries, workspace=None):
    """追加变更条目。entries 为字典列表，键为 id / 字段 / 原值 / 新值。

    新建文件用 utf-8-sig 补 BOM（与主表一致，Excel 中文不乱码）；
    已有文件改用 utf-8 追加——utf-8-sig 每次 open 都会写 BOM，
    在追加场景下会把 BOM 插进文件中间。

    追加无法原子化（必须打开已有文件续写），故只保证 fsync 落盘：
    时间线是审计日志，丢一条尚可追溯，主表损坏才是灾难——原子性预算
    花在 write_rows 上。若需原子追加，正解是改批量重写，但时间线写入频繁，
    全量重写代价过高，不划算。
    """
    if not entries:
        return 0
    path = history_path(workspace)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)

    is_new = not os.path.isfile(path) or os.path.getsize(path) == 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with io.open(path, "w" if is_new else "a",
                 encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS,
                                extrasaction="ignore", restval="")
        if is_new:
            writer.writeheader()
        for entry in entries:
            row = {"时间": now, "id": entry.get("id", ""), "字段": entry.get("字段", ""),
                   "原值": entry.get("原值", ""), "新值": entry.get("新值", "")}
            writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())
    return len(entries)



def diff_entries(app_id, old_row, new_row, fields=None):
    """对比两行，返回有变化的字段条目列表（空列表表示无变化）。"""
    out = []
    for field in (fields or HISTORY_TRACKED):
        before = ((old_row or {}).get(field) or "").strip()
        after = ((new_row or {}).get(field) or "").strip()
        if before != after:
            out.append({"id": app_id, "字段": field, "原值": before, "新值": after})
    return out



def _history_date(entries, app_id, field=None):
    """取某记录最后一次变更（或最后一次指定字段变更）的日期。"""
    best = None
    for entry in entries:
        if (entry.get("id") or "").strip() != app_id:
            continue
        if field and (entry.get("字段") or "").strip() != field:
            continue
        when = parse_iso_date((entry.get("时间") or "")[:10])
        if when and (best is None or when > best):
            best = when
    return best



def last_stage_change_date(app_id, entries):
    """最后一次「当前阶段」变更日期，无则 None。"""
    return _history_date(entries, app_id, "当前阶段")



def last_activity_date(app_id, entries):
    """最后一次任意变更日期（含创建），无则 None。"""
    return _history_date(entries, app_id)



def stage_base_date(row, entries, app_id=None):
    """停留天数的基准日，按优先级回退。

    最后一次阶段变更 → 投递日期 → 最后一次任意变更 → None。

    投递日期排在「任意变更」之前：投递日期是用户声明的流程起点，
    而「任意变更」里包含记录录入时间——补录一条一个月前投的岗位时，
    若以录入时间为准就永远不会触发静默提醒，与语义相反。
    「任意变更」只在既无阶段变更、又没填投递日期时兜底。

    旧数据没有 history.csv 时自动退到投递日期，不需要迁移。
    """
    app_id = app_id or (row.get("id") or "").strip()
    when = last_stage_change_date(app_id, entries)
    if when:
        return when
    when = parse_iso_date(row.get("投递日期"))
    if when:
        return when
    return last_activity_date(app_id, entries)



def stale_days(row, entries, today=None):
    """当前阶段已停留天数。无基准日返回 None（不参与静默判定）。"""
    base = stage_base_date(row, entries)
    if base is None:
        return None
    today = today or date.today()
    return (today - base).days



def health_score(row, entries, today=None):
    """合成投递健康度：返回 {"level": ..., "reasons": [...]}。

    - urgent：非终态且距截止日 ≤3 天仍未投（含已过截止）
    - overdue：有下次动作日期且已过期
    - stale：当前阶段停留超过 STALE_DAYS
    - ok：以上皆无
    - 终态（已挂/已放弃/我拒绝的 offer）返回 level=None，不参与判定

    reasons 收集**所有命中**的理由（不止最高级那一条），level 取最严重的一级。

    hints 与 reasons **按下标一一对应**，是每条理由的结构化形态
    （{"code", "params"}）：CLI 与中文界面继续显示 reasons 原文，
    英文界面按 code 在前端拼句——「机器可读 + 人类可读」双出口。
    params 里的值是**原始数据**（stage 是枚举原值，action 是用户原文），
    翻译由显示层负责（枚举走 domainLabel，用户数据不翻）。
    """
    stage = (row.get("当前阶段") or "").strip()
    if stage in TERMINAL_STAGES:
        return {"level": None, "reasons": [], "hints": []}

    today = today or date.today()
    reasons = []
    hints = []
    levels = []

    deadline = parse_iso_date(row.get("截止日期"))
    if deadline and stage == "待投":
        left = (deadline - today).days
        if left <= URGENT_DAYS:
            levels.append("urgent")
            if left < 0:
                reasons.append("已过截止日 %d 天仍未投" % (-left))
                hints.append({"code": "deadline_passed",
                              "params": {"days": -left}})
            elif left == 0:
                reasons.append("今天就是截止日，仍未投")
                hints.append({"code": "deadline_today", "params": {}})
            else:
                reasons.append("距截止日 %d 天仍未投" % left)
                hints.append({"code": "deadline_left", "params": {"days": left}})

    next_date = parse_iso_date(row.get("下次动作日期"))
    if next_date and next_date < today:
        levels.append("overdue")
        action = (row.get("下次动作") or "").strip()
        reasons.append("下次动作已逾期 %d 天：%s"
                       % ((today - next_date).days, action or "（未写动作）"))
        hints.append({"code": "next_action_overdue",
                      "params": {"days": (today - next_date).days, "action": action}})

    days = stale_days(row, entries, today=today)
    if days is not None and days > STALE_DAYS:
        levels.append("stale")
        reasons.append("已在「%s」停留 %d 天" % (stage or "未填阶段", days))
        hints.append({"code": "stale_stage",
                      "params": {"stage": stage or "未填阶段", "days": days}})

    level = "ok"
    for candidate in HEALTH_LEVELS:
        if candidate in levels:
            level = candidate
            break
    return {"level": level, "reasons": reasons, "hints": hints}



def read_rows(workspace=None):
    path = csv_path(workspace)
    if not os.path.isfile(path):
        return []
    # utf-8-sig 读取时自动去掉 BOM
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]



def write_rows(rows, workspace=None):
    """全量重写主表。

    原子写（tmp + os.replace）：主表是用户唯一的数据源，写到一半被中断会
    留下半截 CSV。改名在同目录内是原子操作，故临时文件与目标同目录。
    """
    path = csv_path(workspace)
    _atomic_write_csv(path, rows, FIELDS, "utf-8-sig")
