# -*- coding: utf-8 -*-
"""联系人：CRUD。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from jobws_core import tracker
from apierror import ApiError
from deps import workspace_dir
from lockctx import locked

router = APIRouter()

from ._shared import (_lock_path, delete_preview_response)



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
        raise ApiError(422, "progress.nameRequired", "姓名必填")

    with locked(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)

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
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with locked(_lock_path(ws)):
        rows = tracker.read_contacts(ws)
        row = tracker.find_contact(rows, contact_id)
        if row is None:
            raise ApiError(404, "progress.contactNotFound",
                           "找不到联系人 %s" % contact_id, id=contact_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.CONTACT_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_contacts(rows, ws)

    return dict(row, _changed=changed)


@router.get("/contacts/preview-delete")
def preview_contact_delete(id: str = "", ws: str = Depends(workspace_dir)):
    """预览删除一条联系人记录（**不落盘**），返回令牌与将删的整行。

    2026-09-21 批 D：与其余记录删除同纪律——领域层校验（存在性 / 重复 id）→
    确认 → 凭令牌走 `/api/approvals/apply` 落盘；落盘前整表快照写到工作区之外。
    """
    from jobws_core.tracker import deletes
    errors, plan = deletes.preview_delete_contact(id, ws)
    return delete_preview_response("contact.delete", errors, plan,
                                   "progress.contactDeleteFailed",
                                   "联系人删除预览失败", ws)
