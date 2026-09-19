# -*- coding: utf-8 -*-
"""面试表：读写与 ID。

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
from ._schema import (INTERVIEW_FIELDS, INTERVIEW_FILE)



def interview_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", INTERVIEW_FILE)



def read_interviews(workspace=None, app_id=None):
    """读取面试记录。app_id 非空时只返回关联该岗位记录的面试。"""
    path = interview_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows



def write_interviews(rows, workspace=None):
    """全量重写面试表（原子写）。"""
    _atomic_write_csv(interview_path(workspace), rows, INTERVIEW_FIELDS, "utf-8-sig")



def next_interview_id(rows):
    """生成下一个面试 ID（I001 起）。"""
    max_num = 0
    for row in rows:
        m = re.match(r"^I(\d+)$", (row.get("面试id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "I%03d" % (max_num + 1)



def find_interview(rows, interview_id):
    for row in rows:
        if (row.get("面试id") or "").strip() == interview_id:
            return row
    return None
