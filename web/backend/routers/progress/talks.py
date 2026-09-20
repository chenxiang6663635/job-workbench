# -*- coding: utf-8 -*-
"""宣讲会 / 招聘会：CRUD 与 .ics 导出。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from jobws_core import tracker
import icsutil
from apierror import ApiError
from deps import workspace_dir
from jobws_core.filelock import file_lock

router = APIRouter()

from ._shared import (_lock_path)

VALID_TALK_FORMS = tracker.TALK_FORMS

VALID_TALK_ATTEND = tracker.TALK_ATTEND



class NewTalk(BaseModel):
    公司: str = ""
    时间: str = ""
    形式: str = ""
    地点或链接: str = ""
    关联记录: str = ""
    是否参加: str = "待定"
    收获: str = ""
    备注: str = ""



class PatchTalk(BaseModel):
    时间: str = None
    形式: str = None
    地点或链接: str = None
    关联记录: str = None
    是否参加: str = None
    收获: str = None
    备注: str = None



# ---------------------------------------------------------------------------
# 宣讲会 / 招聘会（v0.4.0-A）：独立表 talks.csv，与投递记录用「关联记录」相连。
# 读写在 tracker 的 read_talks / write_talks；本层只做 HTTP 编排与枚举校验。
# 写操作与主表共用 tracker.lock——虽然不入主表时间线（宣讲会不是投递推进节点），
# 但同一把锁保证「读最新 → 校验 → 写」整段互斥，避免与主表写并发时丢更新。
# ---------------------------------------------------------------------------


def _validate_talk(形式=None, 是否参加=None):
    """宣讲会枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 形式 is not None and 形式 and 形式 not in VALID_TALK_FORMS:
        raise ApiError(422, "progress.talkFormInvalid",
                       "形式必须是 %s 之一" % "/".join(VALID_TALK_FORMS),
                       values="/".join(VALID_TALK_FORMS))
    if 是否参加 is not None and 是否参加 not in VALID_TALK_ATTEND:
        raise ApiError(422, "progress.talkAttendInvalid",
                       "是否参加必须是 %s 之一" % "/".join(VALID_TALK_ATTEND),
                       values="/".join(VALID_TALK_ATTEND))



def _sort_talks(rows):
    """时间倒序，空时间排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("时间") or ""), reverse=True)



@router.get("/talks")
def list_talks(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_talks(ws, app_id=(app or "").strip() or None)
    return {"rows": _sort_talks(rows), "total": len(rows)}



@router.post("/talks", status_code=201)
def create_talk(item: NewTalk, ws: str = Depends(workspace_dir)):
    _validate_talk(item.形式, item.是否参加)

    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            src = next(
                (r for r in main_rows if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise ApiError(404, "progress.talkLinkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            # 未指定公司时从主表带出，保证列表可读（与面试记录同一条纪律）
            company = company or src.get("公司", "")
        elif not company:
            raise ApiError(422, "progress.talkCompanyRequired",
                           "未关联记录时必须提供公司")

        rows = tracker.read_talks(ws)
        row = {field: "" for field in tracker.TALK_FIELDS}
        row["宣讲会id"] = tracker.next_talk_id(rows)
        row["公司"] = company
        row["时间"] = (item.时间 or "").strip()
        row["形式"] = item.形式
        row["地点或链接"] = (item.地点或链接 or "").strip()
        row["关联记录"] = link
        row["是否参加"] = item.是否参加
        row["收获"] = (item.收获 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_talks(rows, ws)
    return row



@router.patch("/talks/{talk_id}")
def update_talk(talk_id: str, item: PatchTalk, ws: str = Depends(workspace_dir)):
    _validate_talk(item.形式, item.是否参加)

    updates = {k: v for k, v in item.model_dump().items() if v is not None}
    # 「地点或链接」与链接列的同一口径：落盘前 strip
    if "地点或链接" in updates:
        updates["地点或链接"] = (updates["地点或链接"] or "").strip()
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_talks(ws)
        row = tracker.find_talk(rows, talk_id)
        if row is None:
            raise ApiError(404, "progress.talkNotFound",
                           "找不到宣讲会 %s" % talk_id, id=talk_id)

        # 关联记录给出时必须指向存在的投递记录（空串表示解除关联）
        if "关联记录" in updates:
            link = (updates["关联记录"] or "").strip()
            if link:
                main_rows = tracker.read_rows(ws)
                if not any((r.get("id") or "").strip() == link for r in main_rows):
                    raise ApiError(404, "progress.talkLinkNotFound",
                                   "找不到关联记录 %s" % link, id=link)
            updates["关联记录"] = link

        changed = []
        for field, value in updates.items():
            if field in tracker.TALK_FIELDS and (row.get(field, "") or "") != (value or ""):
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_talks(rows, ws)

    return dict(row, _changed=changed)



@router.get("/talks.ics")
def export_talks_ics(ws: str = Depends(workspace_dir), app: str = None):
    """导出宣讲会日程为 .ics（RFC 5545），可直接导入日历应用。"""
    rows = tracker.read_talks(ws, app_id=(app or "").strip() or None)
    events = icsutil.events_from_talks(rows)
    if not events:
        raise ApiError(404, "progress.talksIcsEmpty",
                       "没有可导出的宣讲会日程（时间均为空）")

    ics_text = icsutil.build_ics(events, calendar_name="宣讲会 / 招聘会日程")
    return Response(
        content=ics_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="talks.ics"',
        },
    )
