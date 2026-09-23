# -*- coding: utf-8 -*-
"""联系人命令：cmd_contact 与新增 helper。

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
from ._schema import (CONTACT_FIELDS)
from .applications import (read_rows)
from .contacts import (find_contact, next_contact_id, read_contacts, write_contacts)



def _contact_date_errors(last, next_follow):
    """联系人两个日期字段的校验错误（纯日期：`YYYY-MM-DD`）。"""
    errors = []
    for value, label in ((last, "最近联系"), (next_follow, "下次跟进")):
        if value:
            errors.extend(_core.check_date(value, label) or [])
    return errors


def _contact_add(args):
    """联系人新增：持锁执行（读最新 → 校验 → 写回同一临界区，见 `_core.tracking_lock`）。"""
    with _core.tracking_lock():
        return _contact_add_locked(args)


def _contact_add_locked(args):
    """外键与必填校验 → 组装行 → 落盘。"""
    rows = read_contacts()

    link = (args.app or "").strip()
    if link:
        main_rows = read_rows()
        if not any((r.get("id") or "").strip() == link for r in main_rows):
            print("错误：找不到记录 `%s`" % link)
            return 1

    if not (args.name or "").strip():
        print("错误：--name 必填")
        return 1

    # 日期闸门（2026-09-23 二轮审计）：CLI 与 Web 用同一套判定（`tracker.check_date`），
    # 否则命令行能写进 `2026-02-31`，而看板的「近 7 天待跟进」会静默跳过这一行
    date_errors = _contact_date_errors(args.last, args.next_follow)
    if date_errors:
        for error in date_errors:
            print("错误：%s" % error)
        return 1

    row = {field: "" for field in CONTACT_FIELDS}
    row["联系人id"] = next_contact_id(rows)
    row["关联记录"] = link
    row["姓名"] = args.name.strip()
    row["角色"] = args.role or ""
    row["公司"] = args.company or ""
    row["联系方式"] = args.contact or ""
    row["来源"] = args.source or ""
    row["最近联系"] = args.last or ""
    row["下次跟进"] = args.next_follow or ""
    row["备注"] = args.note or ""
    rows.append(row)
    write_contacts(rows)
    print("已记录联系人 %s：%s" % (row["联系人id"], row["姓名"]))
    return 0



def _contact_update(args):
    """联系人逐字段更新：持锁执行（见 `_core.tracking_lock`）。"""
    with _core.tracking_lock():
        return _contact_update_locked(args)


def _contact_update_locked(args):
    rows = read_contacts()
    row = find_contact(rows, args.id)
    if not row:
        print("错误：找不到联系人 `%s`" % args.id)
        return 1
    changed = []
    given = {}
    for arg_name, field in (
        ("role", "角色"), ("contact", "联系方式"), ("source", "来源"),
        ("last", "最近联系"), ("next_follow", "下次跟进"), ("note", "备注"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            changed.append(field)
            given[field] = value
            row[field] = value
    # 只校验本次真正改动的字段：存量里的坏日期不该挡住一次无关的更新
    date_errors = _contact_date_errors(given.get("最近联系"), given.get("下次跟进"))
    if date_errors:
        for error in date_errors:
            print("错误：%s" % error)
        return 1
    if not changed:
        print("没有字段变化，未写入")
        return 0
    write_contacts(rows)
    print("已更新联系人 %s：%s" % (args.id, "、".join(changed)))
    return 0



def _contact_delete(args):
    """联系人删除：预览（不落盘）→ 凭令牌落盘；删除类永远两段式。"""
    return run_delete_preview("contacts", args.id, "contact.delete")


def cmd_contact(args):
    """招聘方联系人：跟进有节奏的招聘流程靠它维系。"""
    if args.action == "add":
        return _contact_add(args)

    if args.action == "list":
        rows = read_contacts(app_id=args.app)
        if not rows:
            print("（暂无联系人）")
            return 0
        # 有下次跟进日期的置顶（按日期升序，最该跟进的在前），其余按姓名
        rows.sort(key=lambda r: (
            (r.get("下次跟进") or "9999-99-99"),
            r.get("姓名", "")))
        print("## 联系人（共 %d 条）\n" % len(rows))
        print("| id | 姓名 | 角色 | 公司 | 下次跟进 | 备注 |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s |" % (
                r.get("联系人id", ""), r.get("姓名", ""), r.get("角色", "") or "—",
                r.get("公司", "") or "—", r.get("下次跟进", "") or "—",
                r.get("备注", "") or ""))
        return 0

    if args.action == "show":
        rows = read_contacts()
        row = find_contact(rows, args.id)
        if not row:
            print("错误：找不到联系人 `%s`" % args.id)
            return 1
        for field in CONTACT_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        return _contact_update(args)

    if args.action == "delete":
        return _contact_delete(args)

    return 1
