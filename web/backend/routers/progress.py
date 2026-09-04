# -*- coding: utf-8 -*-
"""投递后的进展：面试 CRUD + ICS 导出、联系人、Offer 事实、版本谱系。

复用 tools/tracker.py 的读写函数（read_interviews/read_contacts/
read_offers/next_*_id/append_history），Web 层只做 HTTP 编排。
写操作与主表共用 tracker.lock——面试与 offer 的 add 会向 history.csv
追加时间线，与主表写并发时必须互斥。

Offer 端点的伦理边界：只透出用户录入的已知事实，不做任何加权、
排名或推荐——多目标决策由用户自己做。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import tracker
import icsutil
from deps import DIR_TRACKING, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/progress")

VALID_ROUNDS = tracker.INTERVIEW_ROUNDS
VALID_FORMS = tracker.INTERVIEW_FORMS
VALID_RESULTS = tracker.INTERVIEW_RESULTS


def _lock_path(ws: str) -> str:
    path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


class NewInterview(BaseModel):
    关联记录: str = ""
    公司: str = ""
    岗位: str = ""
    轮次: str = "一面"
    面试时间: str = ""
    形式: str = ""
    面试官: str = ""
    问题记录: str = ""
    我的回答要点: str = ""
    复盘与改进: str = ""
    结果: str = "待定"


class PatchInterview(BaseModel):
    轮次: str = None
    面试时间: str = None
    形式: str = None
    面试官: str = None
    问题记录: str = None
    我的回答要点: str = None
    复盘与改进: str = None
    结果: str = None


def _validate_enum(轮次=None, 形式=None, 结果=None):
    """枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 轮次 is not None and 轮次 not in VALID_ROUNDS:
        raise HTTPException(status_code=422, detail="轮次必须是 %s 之一" % "/".join(VALID_ROUNDS))
    if 形式 is not None and 形式 and 形式 not in VALID_FORMS:
        raise HTTPException(status_code=422, detail="形式必须是 %s 之一" % "/".join(VALID_FORMS))
    if 结果 is not None and 结果 not in VALID_RESULTS:
        raise HTTPException(status_code=422, detail="结果必须是 %s 之一" % "/".join(VALID_RESULTS))


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
                raise HTTPException(status_code=404, detail="找不到关联记录 %s" % link)
            # 未指定公司/岗位时从主表带出，保证列表可读
            company = company or src.get("公司", "")
            role = role or src.get("岗位", "")
        elif not company:
            raise HTTPException(status_code=422, detail="未关联记录时必须提供公司")

        rows = tracker.read_interviews(ws)
        row = {field: "" for field in tracker.INTERVIEW_FIELDS}
        row["面试id"] = tracker.next_interview_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = role
        row["轮次"] = item.轮次
        row["面试时间"] = (item.面试时间 or "").strip()
        row["形式"] = item.形式
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
    if not updates:
        raise HTTPException(status_code=422, detail="没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_interviews(ws)
        row = tracker.find_interview(rows, interview_id)
        if row is None:
            raise HTTPException(status_code=404, detail="找不到面试 %s" % interview_id)

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
        raise HTTPException(
            status_code=404, detail="没有可导出的面试日程（面试时间均为空）")

    ics_text = icsutil.build_ics(events)
    return Response(
        content=ics_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="interviews.ics"',
        },
    )


# ---------------------------------------------------------------------------
# 联系人
# ---------------------------------------------------------------------------

class NewContact(BaseModel):
    关联记录: str = ""
    姓名: str
    角色: str = ""
    公司: str = ""
    联系方式: str = ""
    来源: str = ""
    最近联系: str = ""
    下次跟进: str = ""
    备注: str = ""


class PatchContact(BaseModel):
    角色: str = None
    联系方式: str = None
    来源: str = None
    最近联系: str = None
    下次跟进: str = None
    备注: str = None


@router.get("/contacts")
def list_contacts(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_contacts(ws, app_id=(app or "").strip() or None)
    # 有下次跟进的置顶（最该跟进的在前），与 CLI 一致
    rows.sort(key=lambda r: ((r.get("下次跟进") or "9999-99-99"),
                             r.get("姓名", "")))
    return {"rows": rows, "total": len(rows)}


@router.post("/contacts", status_code=201)
def create_contact(item: NewContact, ws: str = Depends(workspace_dir)):
    link = (item.关联记录 or "").strip()
    if not item.姓名.strip():
        raise HTTPException(status_code=422, detail="姓名必填")

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                raise HTTPException(status_code=404, detail="找不到关联记录 %s" % link)

        rows = tracker.read_contacts(ws)
        row = {field: "" for field in tracker.CONTACT_FIELDS}
        row["联系人id"] = tracker.next_contact_id(rows)
        row["关联记录"] = link
        row["姓名"] = item.姓名.strip()
        row["角色"] = (item.角色 or "").strip()
        row["公司"] = (item.公司 or "").strip()
        row["联系方式"] = (item.联系方式 or "").strip()
        row["来源"] = (item.来源 or "").strip()
        row["最近联系"] = (item.最近联系 or "").strip()
        row["下次跟进"] = (item.下次跟进 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_contacts(rows, ws)

    return row


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: str, item: PatchContact,
                   ws: str = Depends(workspace_dir)):
    updates = {k: v for k, v in item.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_contacts(ws)
        row = tracker.find_contact(rows, contact_id)
        if row is None:
            raise HTTPException(status_code=404, detail="找不到联系人 %s" % contact_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.CONTACT_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_contacts(rows, ws)

    return dict(row, _changed=changed)


# ---------------------------------------------------------------------------
# Offer 事实（只并排展示，不推荐）
# ---------------------------------------------------------------------------

class NewOffer(BaseModel):
    关联记录: str = ""
    公司: str = ""
    岗位: str = ""
    薪资构成: str = ""
    月薪: str = ""
    年终: str = ""
    签字费: str = ""
    股票期权: str = ""
    工作地点: str = ""
    答复截止日: str = ""
    其他条件: str = ""
    备注: str = ""


class PatchOffer(BaseModel):
    薪资构成: str = None
    月薪: str = None
    年终: str = None
    签字费: str = None
    股票期权: str = None
    工作地点: str = None
    答复截止日: str = None
    其他条件: str = None
    备注: str = None


@router.get("/offers")
def list_offers(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_offers(ws, app_id=(app or "").strip() or None)
    # 按答复截止日升序：越先要答复的越靠前。不做任何其他排序或评分
    rows.sort(key=lambda r: (r.get("答复截止日") or "9999-99-99"))
    return {"rows": rows, "total": len(rows)}


@router.post("/offers", status_code=201)
def create_offer(item: NewOffer, ws: str = Depends(workspace_dir)):
    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            src = next((r for r in main_rows
                        if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise HTTPException(status_code=404, detail="找不到关联记录 %s" % link)
            company = company or src.get("公司", "")
        elif not company:
            raise HTTPException(status_code=422, detail="未关联记录时必须提供公司")

        rows = tracker.read_offers(ws)
        row = {field: "" for field in tracker.OFFER_FIELDS}
        row["offer_id"] = tracker.next_offer_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = (item.岗位 or "").strip()
        row["薪资构成"] = (item.薪资构成 or "").strip()
        row["月薪"] = (item.月薪 or "").strip()
        row["年终"] = (item.年终 or "").strip()
        row["签字费"] = (item.签字费 or "").strip()
        row["股票期权"] = (item.股票期权 or "").strip()
        row["工作地点"] = (item.工作地点 or "").strip()
        row["答复截止日"] = (item.答复截止日 or "").strip()
        row["其他条件"] = (item.其他条件 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_offers(rows, ws)

        # 拿到 offer 是关键里程碑，入账时间线
        if link:
            tracker.append_history([{
                "id": link,
                "字段": "offer",
                "原值": "",
                "新值": "%s（%s）" % (row["offer_id"],
                                     row["答复截止日"] or "答复截止待定"),
            }], ws)

    return row


@router.patch("/offers/{offer_id}")
def update_offer(offer_id: str, item: PatchOffer,
                 ws: str = Depends(workspace_dir)):
    updates = {k: v for k, v in item.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_offers(ws)
        row = tracker.find_offer(rows, offer_id)
        if row is None:
            raise HTTPException(status_code=404, detail="找不到 offer %s" % offer_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.OFFER_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_offers(rows, ws)

    return dict(row, _changed=changed)


# ---------------------------------------------------------------------------
# 版本谱系：每个简历版本投了哪些岗位、各处于什么阶段（只读展示层）
# ---------------------------------------------------------------------------

@router.get("/lineage")
def version_lineage(ws: str = Depends(workspace_dir)):
    """按简历版本聚合投递记录：母版 → 按岗派生 → 哪版投了哪家。

    数据源就是 tracker.csv 的「简历版本」列，纯只读聚合，无新数据文件。
    """
    rows = tracker.read_rows(ws)
    groups = {}
    for row in rows:
        version = (row.get("简历版本") or "").strip() or "（未填版本）"
        groups.setdefault(version, []).append({
            "id": row.get("id", ""),
            "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""),
            "当前阶段": row.get("当前阶段", ""),
            "投递日期": row.get("投递日期", ""),
        })

    items = [
        {"version": v, "applications": apps, "total": len(apps)}
        for v, apps in sorted(groups.items())
    ]
    return {"items": items, "total": len(items)}
