# -*- coding: utf-8 -*-
"""邮件表：读写、校验、消息 id 规范化与两段式。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import logging
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from filelock import file_lock  # noqa: E402

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (ConflictError, _atomic_write_csv, _lock_path, resolve_ws)
from ._schema import (MAIL_DIRECTIONS, MAIL_FIELDS, MAIL_FILE, MAIL_TAGS)
from .applications import (read_rows)



def mail_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", MAIL_FILE)



def read_mails(workspace=None, app_id=None):
    """读取邮件记录。app_id 非空时只返回关联该岗位记录的邮件。"""
    path = mail_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows



def write_mails(rows, workspace=None):
    """全量重写邮件表（原子写）。"""
    _atomic_write_csv(mail_path(workspace), rows, MAIL_FIELDS, "utf-8-sig")



def next_mail_id(rows):
    """生成下一个邮件记录 ID（M001 起）。"""
    max_num = 0
    for row in rows:
        m = re.match(r"^M(\d+)$", (row.get("邮件id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "M%03d" % (max_num + 1)



def find_mail(rows, mail_id):
    for row in rows:
        if (row.get("邮件id") or "").strip() == mail_id:
            return row
    return None



def normalize_message_id(text):
    """Message-ID 规范化：去首尾空白与包裹的 `<>`。

    mails.csv 只存规范值——去重与 Gmail 深链（rfc822msgid）都按它比对/构造；
    Gmail「显示原始邮件」给的是 `<...>` 全文，任何入口带尖括号进来都会产出
    失效深链并绕过去重（批 4.5 独立审查 M-1）。
    """
    value = (text or "").strip()
    if len(value) >= 2 and value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value



def _validate_mail_fields(fields, workspace=None):
    """邮件字段校验（预览与落盘两段共用），返回错误列表。

    三条纪律：关联记录非空时必须存在（与 talks/questions 同款外键纪律）；
    主题必填（它是这条记录的主语）；消息id 非空时不允许重复——同一封邮件
    导两遍，列表里会长出一模一样的行，且深链指向同一封、无法自辨。
    """
    errors = []
    link = (fields.get("关联记录") or "").strip()
    if link:
        rows = read_rows(workspace)
        if not any((r.get("id") or "").strip() == link for r in rows):
            errors.append("关联记录 `%s` 不存在（先在 track 里添加这条投递）" % link)
    if not (fields.get("主题") or "").strip():
        errors.append("必须给 `--subject`（邮件主题是这条记录的主语）")
    direction = fields.get("方向") or ""
    if direction and direction not in MAIL_DIRECTIONS:
        errors.append("`--direction` 必须是 %s 之一，实际为 `%s`"
                      % ("/".join(MAIL_DIRECTIONS), direction))
    tag = fields.get("标签") or ""
    if tag and tag not in MAIL_TAGS:
        errors.append("`--tag` 必须是 %s 之一，实际为 `%s`" % ("/".join(MAIL_TAGS), tag))
    msg_id = normalize_message_id(fields.get("消息id"))
    if msg_id:
        rows = read_mails(workspace)
        if any(normalize_message_id(r.get("消息id")) == msg_id for r in rows):
            errors.append("这封邮件（消息id `%s`）已记录过，不要重复导入" % msg_id)
    return errors



def preview_mail_fields(fields, workspace=None):
    """按中文字段预览一次邮件新增（**不落盘**）：返回 (errors, plan)。"""
    fields = {field: (fields.get(field) or "") for field in MAIL_FIELDS}
    for field in ("关联记录", "主题", "发件人", "日期", "webmail链接"):
        fields[field] = fields[field].strip()
    fields["消息id"] = normalize_message_id(fields.get("消息id"))
    errors = _validate_mail_fields(fields, workspace)
    if errors:
        return errors, None
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in MAIL_FIELDS:
        if fields.get(field):
            diff.append("| %s | %s |" % (field, fields[field]))
    plan = {
        "payload": {"fields": fields},
        "summary": "新增邮件：%s（%s）" % (fields["主题"], fields["日期"] or "日期待定"),
        "diff": diff,
        "targets": _mail_targets(workspace),
    }
    return [], plan



def apply_approved_mail(payload, workspace=None):
    """两段式的第二步：按已确认的载荷新增一条邮件记录。

    与宣讲会一样，邮件**不推进任何阶段、也不入主表时间线**——它是投递过程
    的往来证据而非流程节点；阶段变更永远由用户经人工确认的链路完成。
    """
    ws = resolve_ws(workspace)
    fields = dict(payload.get("fields") or {})
    with file_lock(_lock_path(ws)):
        errors = _validate_mail_fields(fields, ws)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))
        rows = read_mails(ws)
        record = {field: "" for field in MAIL_FIELDS}
        record.update(fields)
        record["邮件id"] = next_mail_id(rows)
        rows.append(record)
        write_mails(rows, ws)
        return {"id": record["邮件id"], "written": 1,
                "summary": "已新增 %s（%s）" % (record["邮件id"], record["主题"])}



def _mail_targets(workspace=None):
    """邮件写入会落到的文件（供令牌绑定与预览展示）。"""
    ws = resolve_ws(workspace)
    return [os.path.join(ws, "05_投递追踪", MAIL_FILE)]
