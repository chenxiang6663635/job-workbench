# -*- coding: utf-8 -*-
"""邮件台账：CRUD、深链附加与排序。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import tracker
import mail_link
from apierror import ApiError
from deps import workspace_dir
from filelock import file_lock

router = APIRouter()

from ._shared import (_lock_path)

VALID_MAIL_DIRECTIONS = tracker.MAIL_DIRECTIONS

VALID_MAIL_TAGS = tracker.MAIL_TAGS



# ---------------------------------------------------------------------------
# 邮件（批 4.5）：独立表 mails.csv，与投递记录用「关联记录」相连。
# 与 talks 同一把锁、同一条纪律：邮件只驱动「记录产生」，**不自动改阶段**。
# 「打开原邮件」链接随行附带（_openLink 计算字段）：自粘链接优先，Gmail 由
# Message-ID 构造，其余邮箱 kind=none——前端诚实降级为「打开邮箱 + 复制主题
# 搜索」提示，不显示可能失效的假链接。
# ---------------------------------------------------------------------------


def _validate_mail(方向=None, 标签=None):
    """邮件枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 方向 is not None and 方向 and 方向 not in VALID_MAIL_DIRECTIONS:
        raise ApiError(422, "progress.mailDirectionInvalid",
                       "方向必须是 %s 之一" % "/".join(VALID_MAIL_DIRECTIONS),
                       values="/".join(VALID_MAIL_DIRECTIONS))
    if 标签 is not None and 标签 and 标签 not in VALID_MAIL_TAGS:
        raise ApiError(422, "progress.mailTagInvalid",
                       "标签必须是 %s 之一" % "/".join(VALID_MAIL_TAGS),
                       values="/".join(VALID_MAIL_TAGS))



def _sort_mails(rows):
    """日期倒序，空日期排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("日期") or ""), reverse=True)



def _with_open_link(row):
    """随行附带「打开原邮件」链接（计算字段；前缀下划线与 _changed 同规矩）。"""
    link = mail_link.build_open_link(row.get("消息id", ""),
                                     row.get("webmail链接", ""))
    return dict(row, _openLink=link)



class NewMail(BaseModel):
    消息id: str = ""
    关联记录: str = ""
    方向: str = "收"
    主题: str = ""
    发件人: str = ""
    日期: str = ""
    webmail链接: str = ""
    标签: str = "其他"



@router.get("/mails")
def list_mails(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_mails(ws, app_id=(app or "").strip() or None)
    rows = _sort_mails(rows)
    return {"rows": [_with_open_link(r) for r in rows], "total": len(rows)}



@router.post("/mails", status_code=201)
def create_mail(item: NewMail, ws: str = Depends(workspace_dir)):
    _validate_mail(item.方向, item.标签)

    link = (item.关联记录 or "").strip()
    subject = (item.主题 or "").strip()
    message_id = tracker.normalize_message_id(item.消息id)
    if not subject:
        raise ApiError(422, "progress.mailSubjectRequired", "邮件主题必填")

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                raise ApiError(404, "progress.mailLinkNotFound",
                               "找不到关联记录 %s" % link, id=link)
        rows = tracker.read_mails(ws)
        # 同一封邮件不许导两遍：列表会长出一模一样的行，且深链指向同一封
        if message_id and any(tracker.normalize_message_id(r.get("消息id")) == message_id
                              for r in rows):
            raise ApiError(422, "progress.mailDuplicate",
                           "这封邮件（消息id %s）已记录过" % message_id,
                           id=message_id)
        row = {field: "" for field in tracker.MAIL_FIELDS}
        row["邮件id"] = tracker.next_mail_id(rows)
        row["消息id"] = message_id
        row["关联记录"] = link
        row["方向"] = item.方向
        row["主题"] = subject
        row["发件人"] = (item.发件人 or "").strip()
        row["日期"] = (item.日期 or "").strip()
        row["webmail链接"] = (item.webmail链接 or "").strip()
        row["标签"] = item.标签
        rows.append(row)
        tracker.write_mails(rows, ws)
    return _with_open_link(row)



class PatchMail(BaseModel):
    关联记录: str = None
    方向: str = None
    主题: str = None
    发件人: str = None
    日期: str = None
    webmail链接: str = None
    标签: str = None



@router.patch("/mails/{mail_id}")
def update_mail(mail_id: str, item: PatchMail, ws: str = Depends(workspace_dir)):
    _validate_mail(item.方向, item.标签)

    updates = {k: v for k, v in item.model_dump().items() if v is not None}
    for field in ("主题", "发件人", "日期", "webmail链接"):
        if field in updates:
            updates[field] = (updates[field] or "").strip()
    if "主题" in updates and not updates["主题"]:
        raise ApiError(422, "progress.mailSubjectRequired", "邮件主题必填")
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_mails(ws)
        row = tracker.find_mail(rows, mail_id)
        if row is None:
            raise ApiError(404, "progress.mailNotFound",
                           "找不到邮件 %s" % mail_id, id=mail_id)

        # 关联记录给出时必须指向存在的投递记录（空串表示解除关联）
        if "关联记录" in updates:
            link = (updates["关联记录"] or "").strip()
            if link:
                main_rows = tracker.read_rows(ws)
                if not any((r.get("id") or "").strip() == link for r in main_rows):
                    raise ApiError(404, "progress.mailLinkNotFound",
                                   "找不到关联记录 %s" % link, id=link)
            updates["关联记录"] = link

        changed = []
        for field, value in updates.items():
            if field in tracker.MAIL_FIELDS and (row.get(field, "") or "") != (value or ""):
                changed.append(field)
                row[field] = value
        if not changed:
            return _with_open_link(row)
        tracker.write_mails(rows, ws)

    return _with_open_link(dict(row, _changed=changed))


@router.delete("/mails/{mail_id}")
def delete_mail(mail_id: str, ws: str = Depends(workspace_dir)):
    """删除一封邮件台账记录（**全站首个 DELETE**；契约与 PATCH 对齐）。

    - 持同一把 file_lock：与创建 / 更新 / 其它表的写入互斥；
    - 不存在 → 404（与 PATCH 同错误码 progress.mailNotFound）；
    - 整表重读 → 剔除该行 → 重写；不做软删除（台账是"记错了就删"的场景，
      数据文件保持可读可手改）。
    """
    with file_lock(_lock_path(ws)):
        rows = tracker.read_mails(ws)
        row = tracker.find_mail(rows, mail_id)
        if row is None:
            raise ApiError(404, "progress.mailNotFound",
                           "找不到邮件 %s" % mail_id, id=mail_id)
        rows.remove(row)
        tracker.write_mails(rows, ws)
    return {"邮件id": mail_id, "_deleted": True}
