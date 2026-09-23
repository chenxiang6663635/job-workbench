# -*- coding: utf-8 -*-
"""宣讲会命令：cmd_talk 与新增 helper。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import logging
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core
# （WORKSPACE 经 `from . import _core` 动态引用，不再有值快照导入）
from ._cli_delete import run_delete_preview
from ._schema import (TALK_FIELDS)
from .applications import (read_rows)
from .talks import (apply_approved_talk, find_talk, preview_talk_fields, read_talks, write_talks)



def _talk_add(args):
    """宣讲会新增：字段组装 → 预览校验 → （--preview 走令牌）落盘。"""
    fields = {
        "公司": args.company or "", "时间": args.when or "",
        "形式": args.form or "", "地点或链接": args.place or "",
        "关联记录": args.app or "", "是否参加": args.attend or "待定",
        "收获": args.gain or "", "备注": args.note or "",
    }
    errors, plan = preview_talk_fields(fields, _core.WORKSPACE)
    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    if getattr(args, "preview", False):
        from jobws_core import approval
        result = approval.preview("talk.add", _core.WORKSPACE, plan["payload"],
                                  plan["summary"], plan["diff"], plan["targets"])
        print("## 预览（未写入）\n")
        print(result["summary"])
        print("")
        for line in plan["diff"]:
            print(line)
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0

    result = apply_approved_talk(plan["payload"], _core.WORKSPACE)
    print("## %s\n" % result["summary"])
    for line in plan["diff"]:
        print(line)
    return 0



def _talk_update(args):
    """宣讲会逐字段更新：持锁执行（见 `_core.tracking_lock`）。"""
    with _core.tracking_lock():
        return _talk_update_locked(args)


def _talk_update_locked(args):
    rows = read_talks()
    row = find_talk(rows, args.id)
    if not row:
        print("错误：找不到宣讲会 `%s`" % args.id)
        return 1
    changed = []
    for arg_name, field in (
        ("when", "时间"), ("form", "形式"), ("place", "地点或链接"),
        ("attend", "是否参加"), ("gain", "收获"), ("note", "备注"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            changed.append(field)
            row[field] = value
    # 时间闸门（2026-09-23 二轮审计）：新增走领域层 `_validate_talk_fields`，
    # 更新这条直写路径要自己接上同一判定（带时刻用 check_when）
    if getattr(args, "when", None) is not None:
        when_error = _core.check_when(args.when, "时间")
        if when_error:
            for error in when_error:
                print("错误：%s" % error)
            return 1
    # 关联记录单独处理：给出时必须指向存在的投递记录
    if getattr(args, "app", None) is not None:
        link = args.app.strip()
        if link and not any((r.get("id") or "").strip() == link for r in read_rows()):
            print("错误：找不到记录 `%s`" % link)
            return 1
        changed.append("关联记录")
        row["关联记录"] = link
    if not changed:
        print("没有字段变化，未写入")
        return 0
    write_talks(rows)
    print("已更新宣讲会 %s：%s" % (args.id, "、".join(changed)))
    return 0



def _talk_delete(args):
    """宣讲会删除：预览（不落盘）→ 凭令牌落盘；删除类永远两段式。"""
    return run_delete_preview("talks", args.id, "talk.delete")


def cmd_talk(args):
    """宣讲会 / 招聘会：与投递记录用「关联记录」相连，时间、地点、收获都留下。"""
    if args.action == "add":
        return _talk_add(args)

    if args.action == "list":
        rows = read_talks(app_id=args.app)
        if not rows:
            print("（暂无宣讲会记录）")
            return 0
        # 按时间倒序（最近的活动在前），空时间排最后
        rows.sort(key=lambda r: (r.get("时间") or ""), reverse=True)
        print("## 宣讲会 / 招聘会（共 %d 场）\n" % len(rows))
        print("| id | 公司 | 时间 | 形式 | 地点或链接 | 是否参加 |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s |" % (
                r.get("宣讲会id", ""), r.get("公司", ""),
                r.get("时间", "") or "待定", r.get("形式", "") or "—",
                r.get("地点或链接", "") or "—", r.get("是否参加", "")))
        return 0

    if args.action == "show":
        rows = read_talks()
        row = find_talk(rows, args.id)
        if not row:
            print("错误：找不到宣讲会 `%s`" % args.id)
            return 1
        for field in TALK_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        return _talk_update(args)

    if args.action == "delete":
        return _talk_delete(args)

    print("错误：未知动作 %s" % args.action)
    return 1
