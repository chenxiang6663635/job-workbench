# -*- coding: utf-8 -*-
"""Offer 表：读写与 ID。

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
from ._schema import (OFFER_FIELDS, OFFER_FILE)
from ..csv_cells import restore_row



def offer_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", OFFER_FILE)



def read_offers(workspace=None, app_id=None):
    """读取 Offer 事实。app_id 非空时只返回关联该岗位记录的 Offer。"""
    path = offer_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [restore_row(dict(row)) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows



def write_offers(rows, workspace=None):
    _atomic_write_csv(offer_path(workspace), rows, OFFER_FIELDS, "utf-8-sig")



def next_offer_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^O(\d+)$", (row.get("offer_id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "O%03d" % (max_num + 1)



def find_offer(rows, offer_id):
    for row in rows:
        if (row.get("offer_id") or "").strip() == offer_id:
            return row
    return None
