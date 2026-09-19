# -*- coding: utf-8 -*-
"""面试：CRUD（含枚举校验与排序）与 .ics 导出。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
import tracker
import icsutil
from apierror import ApiError
from deps import workspace_dir
from jobws_core.filelock import file_lock

router = APIRouter()

from ._shared import (_lock_path)


VALID_ROUNDS = tracker.INTERVIEW_ROUNDS

VALID_FORMS = tracker.INTERVIEW_FORMS

VALID_RESULTS = tracker.INTERVIEW_RESULTS



class NewInterview(BaseModel):
    关联记录: str = ""
    公司: str = ""
    岗位: str = ""
    轮次: str = "一面"
    面试时间: str = ""
    形式: str = ""
    链接: str = ""
    面试官: str = ""
    问题记录: str = ""
    我的回答要点: str = ""
    复盘与改进: str = ""
    结果: str = "待定"



class PatchInterview(BaseModel):
    轮次: str = None
    面试时间: str = None
    形式: str = None
    链接: str = None
    面试官: str = None
    问题记录: str = None
    我的回答要点: str = None
    复盘与改进: str = None
    结果: str = None



def _validate_enum(轮次=None, 形式=None, 结果=None):
    """枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 轮次 is not None and 轮次 not in VALID_ROUNDS:
        raise ApiError(422, "progress.roundInvalid",
                       "轮次必须是 %s 之一" % "/".join(VALID_ROUNDS),
                       values="/".join(VALID_ROUNDS))
    if 形式 is not None and 形式 and 形式 not in VALID_FORMS:
        raise ApiError(422, "progress.formInvalid",
                       "形式必须是 %s 之一" % "/".join(VALID_FORMS),
                       values="/".join(VALID_FORMS))
    if 结果 is not None and 结果 not in VALID_RESULTS:
        raise ApiError(422, "progress.resultInvalid",
                       "结果必须是 %s 之一" % "/".join(VALID_RESULTS),
                       values="/".join(VALID_RESULTS))



def _sort_rows(rows):
    """时间倒序，空时间排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("面试时间") or ""), reverse=True)



@router.get("/interviews")
def list_interviews(
    ws: str = Depends(workspace_dir),
    app: str = None,
    result: str = None,
):
    rows = tracker.read_interviews(ws, app_id=(app or "").strip() or None)
    if result:
        rows = [r for r in rows if (r.get("结果") or "").strip() == result]
    return {"rows": _sort_rows(rows), "total": len(rows)}



@router.post("/interviews", status_code=201)
def create_interview(item: NewInterview, ws: str = Depends(workspace_dir)):
    _validate_enum(item.轮次, item.形式, item.结果)

    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()
    role = (item.岗位 or "").strip()

    with file_lock(_lock_path(ws)):
        main_rows = tracker.read_rows(ws)
        if link:
            src = next(
                (r for r in main_rows if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            # 未指定公司/岗位时从主表带出，保证列表可读
            company = company or src.get("公司", "")
            role = role or src.get("岗位", "")
        elif not company:
            raise ApiError(422, "progress.companyRequired", "未关联记录时必须提供公司")

        rows = tracker.read_interviews(ws)
        row = {field: "" for field in tracker.INTERVIEW_FIELDS}
        row["面试id"] = tracker.next_interview_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = role
        row["轮次"] = item.轮次
        row["面试时间"] = (item.面试时间 or "").strip()
        row["形式"] = item.形式
        row["链接"] = (item.链接 or "").strip()
        row["面试官"] = (item.面试官 or "").strip()
        row["问题记录"] = (item.问题记录 or "").strip()
        row["我的回答要点"] = (item.我的回答要点 or "").strip()
        row["复盘与改进"] = (item.复盘与改进 or "").strip()
        row["结果"] = item.结果

        rows.append(row)
        tracker.write_interviews(rows, ws)

        # 面试入账主表时间线：岗位推进历史要能回溯到每一次面试
        if link:
            tracker.append_history([{
                "id": link,
                "字段": "面试",
                "原值": "",
                "新值": "%s %s（%s）" % (row["轮次"], row["面试时间"] or "时间待定",
                                     row["面试id"]),
            }], ws)

    return row



@router.patch("/interviews/{interview_id}")
def update_interview(
    interview_id: str, item: PatchInterview, ws: str = Depends(workspace_dir)
):
    _validate_enum(item.轮次, item.形式, item.结果)

    updates = {k: v for k, v in item.dict().items() if v is not None}
    # 「链接」与新增路径同一口径：落盘前 strip（否则变更比较也会被空白搅乱）
    if "链接" in updates:
        updates["链接"] = (updates["链接"] or "").strip()
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_interviews(ws)
        row = tracker.find_interview(rows, interview_id)
        if row is None:
            raise ApiError(404, "progress.interviewNotFound",
                           "找不到面试 %s" % interview_id, id=interview_id)

        changed = []
        for field, value in updates.items():
            if field in tracker.INTERVIEW_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row

        tracker.write_interviews(rows, ws)

    return dict(row, _changed=changed)



@router.get("/interviews.ics")
def export_ics(ws: str = Depends(workspace_dir), app: str = None):
    """导出面试日程为 .ics（RFC 5545），可直接导入日历应用。"""
    rows = tracker.read_interviews(ws, app_id=(app or "").strip() or None)
    events = icsutil.events_from_interviews(rows)
    if not events:
        raise ApiError(404, "progress.icsEmpty",
                       "没有可导出的面试日程（面试时间均为空）")

    ics_text = icsutil.build_ics(events)
    return Response(
        content=ics_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="interviews.ics"',
        },
    )
