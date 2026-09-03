# -*- coding: utf-8 -*-
"""投递追踪表增删改查。

复用 tools/tracker.py 的读写与校验函数（read_rows/write_rows/check_date/
check_direction/next_id/sort_key），Web 层只做 HTTP 编排与文件锁。
写操作全部持锁——write_rows 是全量重读重写，并发会互相覆盖。

变更时间线：写操作在锁内调用 tracker.append_history 落 history.csv，
时间线的读写与停留天数计算全部由 tracker.py 提供，此处不重复实现。
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import tracker
from deps import DIR_TRACKING, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/applications")

# PATCH 允许更新的字段，与 CLI 的 UPDATABLE 保持单一事实源；公司与岗位不可改
UPDATABLE = tracker.UPDATABLE

STAGES = ["待投", "已投", "笔试", "一面", "二面", "三面", "HR面", "offer", "签约"]
TERMINAL = tracker.TERMINAL_STAGES

# 排序键。default 与 CLI 的 list 一致（终态沉底、按下次动作日期升序）
SORTS = ["default", "next", "score", "stale"]


class NewApplication(BaseModel):
    公司: str
    岗位: str
    方向: str
    批次: str
    来源: str = ""
    截止日期: str = ""
    投递日期: str = ""
    当前阶段: str = "待投"
    状态原因: str = ""
    下次动作: str = ""
    下次动作日期: str = ""
    简历版本: str = ""
    评分: int = 0
    备注: str = ""


class PatchApplication(BaseModel):
    当前阶段: str = None
    状态原因: str = None
    下次动作: str = None
    下次动作日期: str = None
    备注: str = None
    评分: int = None
    投递日期: str = None
    截止日期: str = None


def _find(rows, app_id):
    for row in rows:
        if (row.get("id") or "").strip() == app_id:
            return row
    return None


def _score(row):
    """评分在 CSV 里是字符串，转 int 失败按 0 处理（比让排序崩溃好）。"""
    try:
        return int(str(row.get("评分") or "").strip())
    except (TypeError, ValueError):
        return 0


def _match_keyword(row, keyword):
    if not keyword:
        return True
    k = keyword.strip().lower()
    if not k:
        return True
    for field in ("公司", "岗位", "备注"):
        if k in (row.get(field) or "").lower():
            return True
    return False


def _with_stage_days(rows, ws):
    """给每行附加 stageDays（当前阶段停留天数）。

    构造新 dict 返回，不写到行对象上——rows 会原样传回 write_rows，
    附加字段混进去虽会被 extrasaction 忽略，但让它根本不出现更安全。
    """
    entries = tracker.read_history(ws)
    out = []
    for row in rows:
        item = dict(row)
        days = tracker.stale_days(row, entries)
        item["stageDays"] = days if days is not None else ""
        out.append(item)
    return out


def _sort_items(items, sort):
    if sort == "score":
        items.sort(key=lambda r: (-_score(r), r.get("id", "")))
    elif sort == "stale":
        # 无基准日（空串）排在最后
        items.sort(key=lambda r: (-(r["stageDays"] if isinstance(r["stageDays"], int) else -1),
                                  r.get("id", "")))
    elif sort == "next":
        items.sort(key=lambda r: (0 if (r.get("下次动作日期") or "").strip() else 1,
                                  (r.get("下次动作日期") or ""), r.get("id", "")))
    else:
        items.sort(key=tracker.sort_key)
    return items


def _validate_dates(app: NewApplication):
    for value, label in ((app.截止日期, "截止日期"), (app.投递日期, "投递日期"),
                         (app.下次动作日期, "下次动作日期")):
        errs = tracker.check_date(value or "", label)
        if errs:
            raise HTTPException(status_code=422, detail=errs[0])
    if not (0 <= app.评分 <= 100):
        raise HTTPException(status_code=422, detail="评分必须在 0–100 之间")
    if app.当前阶段 not in STAGES + TERMINAL:
        raise HTTPException(status_code=422,
                            detail="当前阶段必须是 %s 之一" % "/".join(STAGES + TERMINAL))
    errs = tracker.check_reason_required(app.当前阶段, app.状态原因)
    if errs:
        raise HTTPException(status_code=422, detail=errs[0])


@router.get("")
def list_applications(
    stage: str = None,
    direction: str = None,
    batch: str = None,
    q: str = None,
    sort: str = "default",
    active: str = None,
    due_within: int = None,
    overdue: str = None,
    ws: str = Depends(workspace_dir),
):
    rows = tracker.read_rows(ws)
    if stage:
        rows = [r for r in rows if r.get("当前阶段") == stage]
    if direction:
        rows = [r for r in rows if r.get("方向") == direction]
    if batch:
        rows = [r for r in rows if r.get("批次") == batch]
    if q and q.strip():
        rows = [r for r in rows if _match_keyword(r, q)]

    # 看板下钻用的三种筛选。与 dashboard 的统计口径保持一致：
    # active = 非终态；overdue = 待投且已过截止日；due_within = 未来 N 天内到期
    if active and active.lower() in ("1", "true"):
        rows = [r for r in rows if r.get("当前阶段") not in TERMINAL]
    if overdue and overdue.lower() in ("1", "true"):
        today = date.today()
        rows = [r for r in rows
                if r.get("当前阶段") == "待投"
                and tracker.parse_iso_date(r.get("截止日期"))
                and tracker.parse_iso_date(r.get("截止日期")) < today]
    if due_within is not None and due_within >= 0:
        today = date.today()
        limit = today + timedelta(days=due_within)
        kept = []
        for r in rows:
            for field in ("下次动作日期", "截止日期"):
                when = tracker.parse_iso_date(r.get(field))
                if when and today <= when <= limit:
                    kept.append(r)
                    break
        rows = kept

    items = _with_stage_days(rows, ws)
    # 未知排序键回退默认，不报错——前端传参可能来自 URL，容错比严格更好
    items = _sort_items(items, sort if sort in SORTS else "default")
    return {"items": items, "total": len(items)}


@router.get("/{app_id}/history")
def application_history(app_id: str, limit: int = 50,
                        ws: str = Depends(workspace_dir)):
    """某条记录的变更时间线，倒序返回（最新在前）。"""
    rows = tracker.read_rows(ws)
    if _find(rows, app_id) is None:
        raise HTTPException(status_code=404, detail="找不到 id 为 %s 的记录" % app_id)

    entries = tracker.read_history(ws, app_id=app_id)
    entries = list(reversed(entries))
    if limit and limit > 0:
        entries = entries[:limit]
    return {"id": app_id, "items": entries, "total": len(entries)}


@router.post("")
def add_application(app: NewApplication, ws: str = Depends(workspace_dir)):
    _validate_dates(app)

    errs = tracker.check_direction(app.方向, ws)
    if errs:
        raise HTTPException(status_code=422, detail=errs[0])

    lock_path = os.path.join(ws, DIR_TRACKING)
    os.makedirs(lock_path, exist_ok=True)
    lock_path = os.path.join(lock_path, "tracker.lock")

    with file_lock(lock_path):
        rows = tracker.read_rows(ws)

        # canonical 去重：同公司+岗位且既有记录非终态则拒绝（409 并回传既有 id）
        dup, dup_terminal = tracker.find_duplicate(rows, app.公司, app.岗位)
        if dup and not dup_terminal:
            raise HTTPException(
                status_code=409,
                detail="已存在相同公司+岗位的记录 `%s`（当前阶段：%s），请勿重复录入"
                       % (dup.get("id", ""), dup.get("当前阶段", "")))

        row = {f: "" for f in tracker.FIELDS}
        row.update({
            "id": tracker.next_id(rows),
            "公司": app.公司.strip(),
            "岗位": app.岗位.strip(),
            "方向": app.方向,
            "批次": app.批次,
            "来源": app.来源,
            "截止日期": app.截止日期,
            "投递日期": app.投递日期,
            "当前阶段": app.当前阶段,
            "状态原因": app.状态原因,
            "下次动作": app.下次动作,
            "下次动作日期": app.下次动作日期,
            "简历版本": app.简历版本,
            "评分": str(app.评分),
            "备注": app.备注,
        })
        rows.append(row)
        tracker.write_rows(rows, ws)
        # 与 CLI 的 add 保持一致：新建也入账，作为停留天数与首次活动的基准
        tracker.append_history([{
            "id": row["id"], "字段": "创建", "原值": "",
            "新值": "%s %s（%s）" % (row["公司"], row["岗位"], row["当前阶段"]),
        }], ws)

    return {"id": row["id"], "item": row}


@router.patch("/{app_id}")
def update_application(app_id: str, patch: PatchApplication, ws: str = Depends(workspace_dir)):
    if patch.评分 is not None and not (0 <= patch.评分 <= 100):
        raise HTTPException(status_code=422, detail="评分必须在 0–100 之间")
    if patch.当前阶段 and patch.当前阶段 not in STAGES + TERMINAL:
        raise HTTPException(status_code=422,
                            detail="当前阶段必须是 %s 之一" % "/".join(STAGES + TERMINAL))
    for field, label in ((patch.下次动作日期, "下次动作日期"),
                         (patch.投递日期, "投递日期"), (patch.截止日期, "截止日期")):
        if field is not None and field:
            errs = tracker.check_date(field, label)
            if errs:
                raise HTTPException(status_code=422, detail=errs[0])

    updates = {k: v for k, v in patch.model_dump().items() if v is not None and k in UPDATABLE}
    if not updates:
        raise HTTPException(status_code=422, detail="没有提供任何要更新的字段")

    lock_path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    with file_lock(lock_path):
        rows = tracker.read_rows(ws)
        target = _find(rows, app_id)
        if target is None:
            raise HTTPException(status_code=404, detail="找不到 id 为 %s 的记录" % app_id)

        # 终态不回退：原阶段已是终态时禁止改阶段（基于锁内最新阶段判定）
        new_stage = updates.get("当前阶段")
        if new_stage is not None:
            errs = tracker.check_terminal_transition(target.get("当前阶段", ""), str(new_stage))
            if errs:
                raise HTTPException(status_code=422, detail=errs[0])

        # 终态必填原因：按更新后的最终阶段与最终原因判定
        final_stage = str(new_stage) if new_stage is not None else target.get("当前阶段", "")
        final_reason = updates.get("状态原因")
        if final_reason is None:
            final_reason = target.get("状态原因", "")
        errs = tracker.check_reason_required(final_stage, str(final_reason))
        if errs:
            raise HTTPException(status_code=422, detail=errs[0])

        before = dict(target)
        for k, v in updates.items():
            target[k] = str(v)
        tracker.write_rows(rows, ws)
        tracker.append_history(tracker.diff_entries(app_id, before, target), ws)

    return {"item": target}
