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


from ._schema import (INTERVIEW_FIELDS)
from .applications import (append_history, read_rows)
from .interviews import (find_interview, next_interview_id, read_interviews, write_interviews)



def _interview_add(args):
    """面试新增：外键/公司兜底 → 组装行 → 落盘 + 时间线入账。"""
    rows = read_interviews()
    main_rows = read_rows()

    # 关联记录非空时必须存在，避免指到不存在的岗位
    link = (args.app or "").strip()
    if link:
        if not any((r.get("id") or "").strip() == link for r in main_rows):
            print("错误：找不到记录 `%s`，先 python tools/jobws.py track add 或省略 --app" % link)
            return 1
        # 未指定公司/岗位时，从主表带出，保证列表可读
        src = next(r for r in main_rows if (r.get("id") or "").strip() == link)
        company = args.company or src.get("公司", "")
        role = args.role or src.get("岗位", "")
    else:
        if not args.company:
            print("错误：未关联记录时必须给 --company")
            return 1
        company = args.company
        role = args.role or ""

    row = {field: "" for field in INTERVIEW_FIELDS}
    row["面试id"] = next_interview_id(rows)
    row["关联记录"] = link
    row["公司"] = company
    row["岗位"] = role
    row["轮次"] = args.round
    row["面试时间"] = args.when or ""
    row["形式"] = args.form or ""
    row["链接"] = args.link or ""
    row["面试官"] = args.interviewer or ""
    row["问题记录"] = args.questions or ""
    row["我的回答要点"] = args.answers or ""
    row["复盘与改进"] = args.retro or ""
    row["结果"] = args.result

    rows.append(row)
    write_interviews(rows)

    # 面试也入账时间线：它是岗位推进的一部分，事后要能回溯
    if link:
        append_history([{
            "id": link,
            "字段": "面试",
            "原值": "",
            "新值": "%s %s（%s）" % (row["轮次"], row["面试时间"] or "时间待定",
                                 row["面试id"]),
        }])

    print("已记录面试 %s：%s %s %s" % (row["面试id"], company, role, args.round))
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
        rows = read_interviews()
        row = find_interview(rows, args.id)
        if not row:
            print("错误：找不到面试 `%s`" % args.id)
            return 1
        changed = []
        for arg_name, field in (
            ("when", "面试时间"), ("round", "轮次"), ("form", "形式"),
            ("link", "链接"), ("interviewer", "面试官"), ("questions", "问题记录"),
            ("answers", "我的回答要点"), ("retro", "复盘与改进"),
            ("result", "结果"),
        ):
            value = getattr(args, arg_name, None)
            if value is None:
                continue
            if row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            print("没有字段变化，未写入")
            return 0
        write_interviews(rows)
        print("已更新面试 %s：%s" % (args.id, "、".join(changed)))
        return 0

    print("错误：未知动作 %s" % action)
    return 1
