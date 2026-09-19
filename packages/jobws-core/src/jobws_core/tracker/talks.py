# -*- coding: utf-8 -*-
"""宣讲会 / 招聘会表：读写、校验与两段式。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import logging
import os
import re


from jobws_core.filelock import file_lock  # noqa: E402

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (ConflictError, _atomic_write_csv, _lock_path, resolve_ws)
from ._schema import (TALK_ATTEND, TALK_FIELDS, TALK_FILE, TALK_FORMS)
from .applications import (read_rows)



def talk_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", TALK_FILE)



def read_talks(workspace=None, app_id=None):
    """读取宣讲会记录。app_id 非空时只返回关联该岗位记录的活动。"""
    path = talk_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows



def write_talks(rows, workspace=None):
    """全量重写宣讲会表（原子写）。"""
    _atomic_write_csv(talk_path(workspace), rows, TALK_FIELDS, "utf-8-sig")



def next_talk_id(rows):
    """生成下一个宣讲会 ID（T001 起）。"""
    max_num = 0
    for row in rows:
        m = re.match(r"^T(\d+)$", (row.get("宣讲会id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "T%03d" % (max_num + 1)



def find_talk(rows, talk_id):
    for row in rows:
        if (row.get("宣讲会id") or "").strip() == talk_id:
            return row
    return None



def _validate_talk_fields(fields, workspace=None):
    """宣讲会字段校验（预览与落盘两段共用），返回错误列表。

    关联记录非空时必须存在；未关联时公司必填——与面试记录同一条纪律：
    指到不存在的岗位或没有主语的记录，都会让列表变成读不懂的碎片。
    """
    errors = []
    link = (fields.get("关联记录") or "").strip()
    company = (fields.get("公司") or "").strip()
    if link:
        rows = read_rows(workspace)
        if not any((r.get("id") or "").strip() == link for r in rows):
            errors.append("关联记录 `%s` 不存在（先在 track 里添加这条投递）" % link)
    elif not company:
        errors.append("未关联记录时必须给 `--company`")
    form = fields.get("形式") or ""
    if form and form not in TALK_FORMS:
        errors.append("`--form` 必须是 %s 之一，实际为 `%s`" % ("/".join(TALK_FORMS), form))
    attend = fields.get("是否参加") or ""
    if attend and attend not in TALK_ATTEND:
        errors.append("`--attend` 必须是 %s 之一，实际为 `%s`" % ("/".join(TALK_ATTEND), attend))
    return errors



def preview_talk_fields(fields, workspace=None):
    """按中文字段预览一次宣讲会新增（**不落盘**）：返回 (errors, plan)。"""
    fields = {field: (fields.get(field) or "") for field in TALK_FIELDS}
    for field in ("公司", "时间", "地点或链接", "收获", "备注"):
        fields[field] = fields[field].strip()
    # 关联记录存在且未填公司时从主表带出（与面试记录同款：让列表可读——
    # 否则「T001 / 空 / 关联 A001」每条都要用户自己去主表对照公司名）
    link = fields["关联记录"]
    if link and not fields["公司"]:
        src = next((r for r in read_rows(workspace)
                    if (r.get("id") or "").strip() == link), None)
        if src is not None:
            fields["公司"] = (src.get("公司") or "").strip()
    errors = _validate_talk_fields(fields, workspace)
    if errors:
        return errors, None
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in TALK_FIELDS:
        if fields.get(field):
            diff.append("| %s | %s |" % (field, fields[field]))
    plan = {
        "payload": {"fields": fields},
        "summary": "新增宣讲会：%s（%s）" % (
            fields["公司"], fields["时间"] or "时间待定"),
        "diff": diff,
        "targets": _talk_targets(workspace),
    }
    return [], plan



def apply_approved_talk(payload, workspace=None):
    """两段式的第二步：按已确认的载荷新增一条宣讲会记录。

    与面试/联系人不同，宣讲会**不入主表时间线**——它不是投递流程的推进节点，
    只是活动笔记；时间线上多出这些噪音反而看不清岗位真实进展。
    """
    ws = resolve_ws(workspace)
    fields = dict(payload.get("fields") or {})
    with file_lock(_lock_path(ws)):
        errors = _validate_talk_fields(fields, ws)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))
        rows = read_talks(ws)
        record = {field: "" for field in TALK_FIELDS}
        record.update(fields)
        record["宣讲会id"] = next_talk_id(rows)
        rows.append(record)
        write_talks(rows, ws)
        return {"id": record["宣讲会id"], "written": 1,
                "summary": "已新增 %s（%s）" % (record["公司"], record["宣讲会id"])}



def _talk_targets(workspace=None):
    """宣讲会写入会落到的文件（供令牌绑定与预览展示）。"""
    ws = resolve_ws(workspace)
    return [os.path.join(ws, "05_投递追踪", TALK_FILE)]
