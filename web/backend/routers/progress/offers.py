# -*- coding: utf-8 -*-
"""Offer 事实：CRUD（只透出已知事实，不做排名/推荐）。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import tracker
from apierror import ApiError
from deps import workspace_dir
from jobws_core.filelock import file_lock

router = APIRouter()

from ._shared import (_lock_path)



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
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            company = company or src.get("公司", "")
        elif not company:
            raise ApiError(422, "progress.companyRequired", "未关联记录时必须提供公司")

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
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_offers(ws)
        row = tracker.find_offer(rows, offer_id)
        if row is None:
            raise ApiError(404, "progress.offerNotFound",
                           "找不到 offer %s" % offer_id, id=offer_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.OFFER_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_offers(rows, ws)

    return dict(row, _changed=changed)
