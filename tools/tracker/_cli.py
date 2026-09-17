# -*- coding: utf-8 -*-
"""主表 CLI：add/update/list/show/history + check + 表格格式化。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import logging
import os
import re
import sys

from datetime import date, datetime

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core
from ._check import (run_check)
from ._core import (DATE_RE, TERMINAL_STAGES, check_direction)
from ._schema import (FIELDS)
from .applications import (read_history, read_rows)
from .preview_app import (apply_approved_add, preview_add)
from .preview_update import (apply_approved_update, preview_update_fields)



def cmd_add(args):
    """新增投递记录；--preview 只登记令牌（两段式的第一步），不改工作区。"""
    errors, plan = preview_add(args)
    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    if getattr(args, "preview", False):
        # 延迟导入：真的走两段式时才依赖协议层（approval 会 import 本模块，
        # 顶层互相引用会转圈）。
        import approval
        result = approval.preview(
            "track.add", _core.WORKSPACE, plan["payload"], plan["summary"],
            plan["diff"], plan["targets"])
        print("## 预览（未写入）\n")
        print(result["summary"])
        print("")
        for line in plan["diff"]:
            print(line)
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0

    apply_approved_add(plan["payload"], _core.WORKSPACE)
    fields = plan["payload"]["fields"]
    print("## 已写入\n")
    print("| 字段 | 值 |")
    print("|---|---|")
    for field in FIELDS:
        if fields.get(field):
            print("| %s | %s |" % (field, fields[field]))
    print("\n归档目录建议：`05_投递追踪/applications/%s_%s`"
          % (fields["公司"], fields["岗位"]))
    return 0



def cmd_update(args):
    """更新记录；--preview 只登记令牌（两段式的第一步），不改工作区。"""
    changes = {}
    for field, value in (("当前阶段", args.stage), ("状态原因", args.reason),
                         ("下次动作", args.next), ("下次动作日期", args.next_date),
                         ("备注", args.note), ("投递日期", args.applied),
                         ("截止日期", args.deadline), ("链接", args.link)):
        if value is not None:
            changes[field] = value
    if args.score is not None:
        changes["评分"] = str(args.score)

    errors, plan = preview_update_fields({"id": args.id, "changes": changes}, _core.WORKSPACE)
    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    if getattr(args, "preview", False):
        import approval
        result = approval.preview("track.update", _core.WORKSPACE, plan["payload"],
                                  plan["summary"], plan["diff"], plan["targets"])
        print("## 预览（未写入）\n")
        print(result["summary"])
        for line in plan["diff"]:
            print(line)
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0

    result = apply_approved_update(plan["payload"], _core.WORKSPACE)
    print("## %s\n" % result["summary"])
    for line in result.get("diff") or plan["diff"]:
        print(line)
    return 0



def format_table(rows):
    if not rows:
        return "（无匹配记录）"
    lines = []
    header = ["id", "公司", "岗位", "方向", "批次", "当前阶段", "截止日期", "下次动作", "下次动作日期", "评分"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        lines.append("| " + " | ".join(
            (row.get(h) or "") for h in header
        ) + " |")
    return "\n".join(lines)



def filter_rows(rows, args):
    result = rows
    if getattr(args, "stage", None):
        result = [r for r in result if r.get("当前阶段") == args.stage]
    if getattr(args, "direction", None):
        result = [r for r in result if r.get("方向") == args.direction]
    if getattr(args, "batch", None):
        result = [r for r in result if r.get("批次") == args.batch]
    if getattr(args, "company", None):
        result = [r for r in result if args.company in (r.get("公司") or "")]
    return result



def sort_key(row):
    """活跃记录在前、终态在后；按下次动作日期升序，空日期排最后。

    提升为模块级函数，供 CLI 与 Web 共用同一排序规则——
    两处各写一份迟早会不一致。
    """
    terminal = 1 if row.get("当前阶段") in TERMINAL_STAGES else 0
    nd = (row.get("下次动作日期") or "").strip()
    return (terminal, "9999" if not nd else nd, row.get("id", ""))



def cmd_list(args):
    if getattr(args, "direction", None):
        errs = check_direction(args.direction)
        if errs:
            print("## 校验失败\n")
            for e in errs:
                print("- %s" % e)
            return 1

    rows = read_rows()
    if not rows:
        print("追踪表为空。用 `python tools/jobws.py track add` 添加第一条记录。")
        return 0

    result = filter_rows(rows, args)

    due_within = getattr(args, "due_within", None)
    if due_within is not None:
        from datetime import date, timedelta
        today = date.today()
        limit = today + timedelta(days=due_within)
        kept = []
        for r in result:
            for field in ("下次动作日期", "截止日期"):
                raw = (r.get(field) or "").strip()
                if DATE_RE.match(raw):
                    y, m, d = (int(x) for x in raw.split("-"))
                    if today <= date(y, m, d) <= limit:
                        kept.append(r)
                        break
        result = kept

    result.sort(key=sort_key)

    print("## 共 %d 条（总记录 %d 条）\n" % (len(result), len(rows)))
    print(format_table(result))
    return 0



def cmd_show(args):
    rows = read_rows()
    for row in rows:
        if (row.get("id") or "").strip() == args.id:
            print("## %s %s（%s）\n" % (row.get("公司", ""), row.get("岗位", ""), args.id))
            print("| 字段 | 值 |")
            print("|---|---|")
            for field in FIELDS:
                print("| %s | %s |" % (field, row.get(field, "") or "（空）"))
            return 0
    print("错误：找不到 id 为 `%s` 的记录" % args.id)
    return 1



def cmd_history(args):
    entries = read_history(app_id=args.id)
    if not entries:
        print("（暂无变更记录%s）" % ("：%s" % args.id if args.id else ""))
        return 0

    # 倒序展示：最近的变更在最上面
    entries = list(reversed(entries))
    if args.limit and args.limit > 0:
        entries = entries[:args.limit]

    print("## 变更时间线（共 %d 条）\n" % len(entries))
    print("| 时间 | id | 字段 | 原值 | 新值 |")
    print("|---|---|---|---|---|")
    for e in entries:
        print("| %s | %s | %s | %s | %s |" % (
            e.get("时间", ""), e.get("id", ""), e.get("字段", ""),
            e.get("原值", "") or "（空）", e.get("新值", "") or "（空）"))
    return 0



def cmd_check(args):
    """schema 自检：只读扫描，坏文件隔离，问题清单可直接照着修。"""
    result = run_check()

    print("## schema 自检（v%d）\n" % result["version"])
    if result["versionNote"]:
        print("> %s\n" % result["versionNote"])

    for f in result["files"]:
        status = "通过" if f["ok"] else "异常"
        note = f.get("note") or ""
        print("- **%s**：%s%s" % (f["file"], status,
                                  ("（%s）" % note) if note else ""))
        for issue in f["issues"]:
            print("  - %s" % issue)
    print("")

    if result["quarantined"]:
        print("## 已隔离文件\n")
        for q in result["quarantined"]:
            print("- %s → `%s`（原因：%s）" % (
                q["file"], q["moved_to"], q["error"]))
        print("")
        print("隔离的文件不会参与任何读写。修复后可改名放回，"
              "或从快照备份恢复。")
        return 1
    if not result["ok"]:
        print("存在问题行，按上面清单修正。")
        return 1
    print("全部通过。")
    return 0
