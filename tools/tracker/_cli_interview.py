# -*- coding: utf-8 -*-
"""面试命令：cmd_interview 与新增 helper。

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
from ._schema import (INTERVIEW_FIELDS)
from .interviews import (find_interview, read_interviews)
# 两段式的载荷构造与落盘收在 preview_interview：CLI 与 MCP 走同一份，
# 避免"命令行说 X、模型看到 Y"（批 4.7 四端一致）。
from .preview_interview import (apply_approved_interview_add,
                                apply_approved_interview_update,
                                preview_interview_add_fields,
                                preview_interview_update_fields)



def _print_preview(operation, plan):
    """两段式第一步的公共输出：登记令牌并打印差异与下一步。"""
    from jobws_core import approval  # 延迟导入：approval 会 import 本模块，顶层互相引用会转圈
    result = approval.preview(operation, _core.WORKSPACE, plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    print("## 预览（未写入）\n")
    print(result["summary"])
    print("")
    for line in plan["diff"]:
        print(line)
    print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
    print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
    return 0


def _print_errors(errors):
    print("## 校验失败\n")
    for item in errors:
        print("- %s" % item)
    print("\n未写入 CSV。")
    return 1


def _interview_add(args):
    """面试新增：走两段式领域层（外键/公司兜底与校验都在那里，与 MCP 同源）。

    默认仍是**直接落盘**（与改动前行为一致）；`--preview` 才只登记令牌。
    """
    errors, plan = preview_interview_add_fields({
        "关联记录": args.app or "",
        "公司": args.company or "",
        "岗位": args.role or "",
        "轮次": args.round or "一面",
        "面试时间": args.when or "",
        "形式": args.form or "",
        "链接": args.link or "",
        "面试官": args.interviewer or "",
        "问题记录": args.questions or "",
        "我的回答要点": args.answers or "",
        "复盘与改进": args.retro or "",
        "结果": args.result or "待定",
    })
    if errors:
        return _print_errors(errors)

    if getattr(args, "preview", False):
        return _print_preview("interview.add", plan)

    result = apply_approved_interview_add(plan["payload"])
    print(result["summary"])
    return 0



def cmd_interview(args):
    """面试记录：投递之后的每一次交流都记下来，复盘是唯一能复利的部分。"""
    action = args.action

    if action == "add":
        return _interview_add(args)

    if action == "list":
        rows = read_interviews(app_id=args.app)
        if args.result:
            rows = [r for r in rows if (r.get("结果") or "").strip() == args.result]
        if not rows:
            print("（暂无面试记录）")
            return 0
        # 按面试时间倒序（最近的在前），空时间排最后
        rows.sort(key=lambda r: (r.get("面试时间") or ""), reverse=True)
        print("## 面试记录（共 %d 条）\n" % len(rows))
        print("| id | 公司 | 岗位 | 轮次 | 时间 | 形式 | 结果 |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("面试id", ""), r.get("公司", ""), r.get("岗位", ""),
                r.get("轮次", ""), r.get("面试时间", "") or "待定",
                r.get("形式", "") or "—", r.get("结果", "")))
        return 0

    if action == "show":
        rows = read_interviews()
        row = find_interview(rows, args.id)
        if not row:
            print("错误：找不到面试 `%s`" % args.id)
            return 1
        print("## %s %s · %s（%s）\n" % (
            row.get("公司", ""), row.get("岗位", ""), row.get("轮次", ""), args.id))
        for field in INTERVIEW_FIELDS:
            print("**%s**：%s\n" % (field, row.get(field, "") or "（空）"))
        return 0

    if action == "update":
        changes = {}
        for arg_name, field in (
            ("when", "面试时间"), ("round", "轮次"), ("form", "形式"),
            ("link", "链接"), ("interviewer", "面试官"), ("questions", "问题记录"),
            ("answers", "我的回答要点"), ("retro", "复盘与改进"),
            ("result", "结果"),
        ):
            value = getattr(args, arg_name, None)
            if value is not None:
                changes[field] = value

        errors, plan = preview_interview_update_fields(
            {"id": args.id, "changes": changes})
        if errors:
            return _print_errors(errors)

        if getattr(args, "preview", False):
            return _print_preview("interview.update", plan)

        result = apply_approved_interview_update(plan["payload"])
        print(result["summary"])
        return 0

    print("错误：未知动作 %s" % action)
    return 1
