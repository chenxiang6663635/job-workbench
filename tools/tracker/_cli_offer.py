# -*- coding: utf-8 -*-
"""Offer 命令：cmd_offer 与新增 helper。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import logging
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core
from ._cli_delete import run_delete_preview
from ._schema import (OFFER_FIELDS)
from .applications import (append_history, read_rows)
from .offers import (find_offer, next_offer_id, read_offers, write_offers)



def _offer_deadline_errors(value):
    """答复截止日的校验错误（纯日期 `YYYY-MM-DD`；空值放行）。"""
    if not value:
        return []
    return _core.check_date(value, "答复截止日") or []


def _offer_add(args):
    """Offer 新增：持锁执行（读最新 → 校验 → 写回同一临界区，见 `_core.tracking_lock`）。"""
    with _core.tracking_lock():
        return _offer_add_locked(args)


def _offer_add_locked(args):
    """外键/公司兜底 → 组装行 → 落盘 + 时间线入账。"""
    rows = read_offers()

    link = (args.app or "").strip()
    company = (args.company or "").strip()
    if link:
        main_rows = read_rows()
        src = next((r for r in main_rows
                    if (r.get("id") or "").strip() == link), None)
        if src is None:
            print("错误：找不到记录 `%s`" % link)
            return 1
        company = company or src.get("公司", "")
    elif not company:
        print("错误：未关联记录时必须给 --company")
        return 1

    # 日期闸门（2026-09-23 二轮审计）：与 Web 侧同一判定；假日期落库后
    # 「3 天内要答复」的提醒与 .ics 导出都会静默跳过这一条
    deadline_errors = _offer_deadline_errors(args.deadline)
    if deadline_errors:
        for error in deadline_errors:
            print("错误：%s" % error)
        return 1

    row = {field: "" for field in OFFER_FIELDS}
    row["offer_id"] = next_offer_id(rows)
    row["关联记录"] = link
    row["公司"] = company
    row["岗位"] = args.role or ""
    row["薪资构成"] = args.salary or ""
    row["月薪"] = args.monthly or ""
    row["年终"] = args.bonus or ""
    row["签字费"] = args.signon or ""
    row["股票期权"] = args.equity or ""
    row["工作地点"] = args.location or ""
    row["答复截止日"] = args.deadline or ""
    row["其他条件"] = args.conditions or ""
    row["备注"] = args.note or ""
    rows.append(row)
    write_offers(rows)

    # 拿到 offer 是岗位推进的关键里程碑，入账时间线
    if link:
        append_history([{
            "id": link,
            "字段": "offer",
            "原值": "",
            "新值": "%s（%s）" % (row["offer_id"], row["答复截止日"] or "答复截止待定"),
        }])

    print("已记录 offer %s：%s" % (row["offer_id"], company))
    return 0



def _offer_update(args):
    """Offer 逐字段更新：持锁执行（见 `_core.tracking_lock`）。"""
    with _core.tracking_lock():
        return _offer_update_locked(args)


def _offer_update_locked(args):
    rows = read_offers()
    row = find_offer(rows, args.id)
    if not row:
        print("错误：找不到 offer `%s`" % args.id)
        return 1
    changed = []
    given = {}
    for arg_name, field in (
        ("salary", "薪资构成"), ("monthly", "月薪"), ("bonus", "年终"),
        ("signon", "签字费"), ("equity", "股票期权"), ("location", "工作地点"),
        ("deadline", "答复截止日"), ("conditions", "其他条件"), ("note", "备注"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            changed.append(field)
            given[field] = value
            row[field] = value
    # 只校验本次改动的字段（存量坏日期不该挡住一次无关的更新）
    deadline_errors = _offer_deadline_errors(given.get("答复截止日"))
    if deadline_errors:
        for error in deadline_errors:
            print("错误：%s" % error)
        return 1
    if not changed:
        print("没有字段变化，未写入")
        return 0
    write_offers(rows)
    print("已更新 offer %s：%s" % (args.id, "、".join(changed)))
    return 0



def _offer_delete(args):
    """Offer 删除：预览（不落盘）→ 凭令牌落盘；删除类永远两段式。"""
    return run_delete_preview("offers", args.id, "offer.delete")


def cmd_offer(args):
    """Offer 已知事实：只记录，不判断——选择是多目标决策，由用户自己做。"""
    if args.action == "add":
        return _offer_add(args)

    if args.action == "list":
        rows = read_offers(app_id=args.app)
        if not rows:
            print("（暂无 offer 记录）")
            return 0
        # 按答复截止日升序：越先要答复的越靠前
        rows.sort(key=lambda r: (r.get("答复截止日") or "9999-99-99"))
        print("## Offer（共 %d 条）\n" % len(rows))
        print("| id | 公司 | 岗位 | 月薪 | 答复截止 |")
        print("|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s |" % (
                r.get("offer_id", ""), r.get("公司", ""), r.get("岗位", "") or "—",
                r.get("月薪", "") or "—", r.get("答复截止日", "") or "—"))
        return 0

    if args.action == "show":
        rows = read_offers()
        row = find_offer(rows, args.id)
        if not row:
            print("错误：找不到 offer `%s`" % args.id)
            return 1
        for field in OFFER_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        return _offer_update(args)

    if args.action == "delete":
        return _offer_delete(args)

    return 1
