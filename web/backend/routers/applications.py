# -*- coding: utf-8 -*-
"""投递追踪表增删改查。

复用 tools/tracker.py 的读写与校验函数（read_rows/write_rows/check_date/
check_direction/next_id/sort_key），Web 层只做 HTTP 编排与文件锁。
写操作全部持锁——write_rows 是全量重读重写，并发会互相覆盖。
"""

from __future__ import annotations

import os

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
    ws: str = Depends(workspace_dir),
):
    rows = tracker.read_rows(ws)
    if stage:
        rows = [r for r in rows if r.get("当前阶段") == stage]
    if direction:
        rows = [r for r in rows if r.get("方向") == direction]
    if batch:
        rows = [r for r in rows if r.get("批次") == batch]
    # 终态沉底，其余按下次动作日期升序（与 CLI list 一致）
    rows.sort(key=tracker.sort_key)
    return {"items": rows, "total": len(rows)}


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

        for k, v in updates.items():
            target[k] = str(v)
        tracker.write_rows(rows, ws)

    return {"item": target}
