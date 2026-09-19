# -*- coding: utf-8 -*-
"""联系人表：读写与 ID。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import logging
import os
import re


# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (_atomic_write_csv, resolve_ws)
from ._schema import (CONTACT_FIELDS, CONTACT_FILE)



def contact_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", CONTACT_FILE)



def read_contacts(workspace=None, app_id=None):
    """读取联系人。app_id 非空时只返回关联该岗位记录的联系人。"""
    path = contact_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows



def write_contacts(rows, workspace=None):
    _atomic_write_csv(contact_path(workspace), rows, CONTACT_FIELDS, "utf-8-sig")



def next_contact_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^C(\d+)$", (row.get("联系人id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "C%03d" % (max_num + 1)



def find_contact(rows, contact_id):
    for row in rows:
        if (row.get("联系人id") or "").strip() == contact_id:
            return row
    return None
