# -*- coding: utf-8 -*-
"""邮件命令：cmd_mail 与新增/更新 helper。

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
from ._schema import (MAIL_DIRECTIONS, MAIL_FIELDS, MAIL_TAGS)
from .applications import (read_rows)
from .mails import (apply_approved_mail, find_mail, preview_mail_fields, read_mails, write_mails)



def _mail_add(args):
    """邮件新增：字段组装 → 预览校验 → （--preview 走令牌）落盘。"""
    fields = {
        "消息id": getattr(args, "message_id", None) or "",
        "关联记录": args.app or "",
        "方向": args.direction or "收",
        "主题": args.subject or "",
        "发件人": getattr(args, "sender", None) or "",
        "日期": args.when or "",
        "webmail链接": args.url or "",
        "标签": args.tag or "其他",
        "会议链接": getattr(args, "meeting_link", None) or "",
    }
    errors, plan = preview_mail_fields(fields, _core.WORKSPACE)
    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    if getattr(args, "preview", False):
        from jobws_core import approval
        result = approval.preview("mail.add", _core.WORKSPACE, plan["payload"],
                                  plan["summary"], plan["diff"], plan["targets"])
        print("## 预览（未写入）\n")
        print(result["summary"])
        print("")
        for line in plan["diff"]:
            print(line)
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0

    result = apply_approved_mail(plan["payload"], _core.WORKSPACE)
    print("## %s\n" % result["summary"])
    for line in plan["diff"]:
        print(line)
    return 0



def _mail_update(args):
    """邮件更新：逐字段改 + 关联记录与外键校验 + 枚举复核（与新增同口径）。"""
    rows = read_mails()
    row = find_mail(rows, args.id)
    if not row:
        print("错误：找不到邮件 `%s`" % args.id)
        return 1
    changed = []
    for arg_name, field in (
        ("subject", "主题"), ("direction", "方向"), ("sender", "发件人"),
        ("when", "日期"), ("url", "webmail链接"), ("tag", "标签"),
        ("meeting_link", "会议链接"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            changed.append(field)
            row[field] = value
    # 关联记录单独处理：给出时必须指向存在的投递记录
    if getattr(args, "app", None) is not None:
        link = args.app.strip()
        if link and not any((r.get("id") or "").strip() == link for r in read_rows()):
            print("错误：找不到记录 `%s`" % link)
            return 1
        changed.append("关联记录")
        row["关联记录"] = link
    # 枚举与新增同口径（手滑打错不该静默落盘）
    direction = row.get("方向") or ""
    if direction and direction not in MAIL_DIRECTIONS:
        print("错误：方向必须是 %s 之一" % "/".join(MAIL_DIRECTIONS))
        return 1
    tag = row.get("标签") or ""
    if tag and tag not in MAIL_TAGS:
        print("错误：标签必须是 %s 之一" % "/".join(MAIL_TAGS))
        return 1
    if not changed:
        print("没有字段变化，未写入")
        return 0
    write_mails(rows)
    print("已更新邮件 %s：%s" % (args.id, "、".join(changed)))
    return 0



def _mail_delete(args):
    """邮件删除：预览（不落盘）→ 凭令牌落盘；删除类永远两段式。"""
    return run_delete_preview("mails", args.id, "mail.delete")


def cmd_mail(args):
    """邮件记录：独立表沉淀往来邮件，与投递记录用「关联记录」相连。

    只入账与查询——邮件**不自动**推进任何阶段；改阶段请走人工确认的
    链路（track update / 邮件解析建议），这是与诚实红线同源的纪律。
    """
    if args.action == "add":
        return _mail_add(args)

    if args.action == "list":
        rows = read_mails(app_id=args.app)
        if not rows:
            print("（暂无邮件记录）")
            return 0
        # 按日期倒序（最近的在先），空日期排最后
        rows.sort(key=lambda r: (r.get("日期") or ""), reverse=True)
        print("## 邮件（共 %d 封）\n" % len(rows))
        print("| id | 日期 | 方向 | 标签 | 主题 | 发件人 | 关联 |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("邮件id", ""), r.get("日期", "") or "—",
                r.get("方向", "") or "—", r.get("标签", "") or "—",
                r.get("主题", ""), r.get("发件人", "") or "—",
                r.get("关联记录", "") or "—"))
        return 0

    if args.action == "show":
        rows = read_mails()
        row = find_mail(rows, args.id)
        if not row:
            print("错误：找不到邮件 `%s`" % args.id)
            return 1
        for field in MAIL_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        return _mail_update(args)

    if args.action == "delete":
        return _mail_delete(args)

    print("错误：未知动作 %s" % args.action)
    return 1
