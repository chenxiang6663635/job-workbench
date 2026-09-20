# -*- coding: utf-8 -*-
"""`jobws bank` 的子命令层：解析参数、打印预览、交接令牌。

（2026-09-18 从 `question_bank.py` 拆出：领域层不 import argparse——后端与
将来进包的版本都只需要读写函数，命令行是仓库侧的事。命令名与参数逐字未变。）

写操作全部走两段式：这里只**签发预览**（不落盘），落盘统一走
`python tools/jobws.py apply <令牌>`。
退出码：0 成功 / 1 业务失败（校验不过、无可导入）/ 2 用法错误。
"""

from __future__ import print_function

import argparse
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from jobws_core.question_bank import (MODULE_DIR, export_csv, preview_add_fields,  # noqa: E402
                           preview_import, preview_import_csv,
                           preview_update_fields, read_questions)
from jobws_core.question_review import (due_questions,  # noqa: E402
                                        preview_mark_wrong, wrong_questions)
from jobws_core.question_delete import preview_delete_fields  # noqa: E402

import _cli_bank_drill  # noqa: E402  （drill 命令层：只读抽题；拆出去守规模预算）


def _print_questions(rows):
    if not rows:
        print("（题库为空——用 `jobws bank add` 加题，或 `jobws bank import` 从 03_面试准备 导入）")
        return
    print("| 题目id | 题目 | 领域 | 状态 | 来源 |")
    print("|---|---|---|---|---|")
    for row in rows:
        print("| %s | %s | %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            row.get("领域") or "—", row.get("状态") or "未看", row.get("来源") or ""))
    print("")
    print("共 %d 道" % len(rows))


def _run_due(workspace):
    """今日待复习：只读列表（间隔阶梯与保守规则都在 question_review 里）。"""
    items = due_questions(workspace)
    if not items:
        print("今日没有待复习的题。")
        return 0
    print("| 题目 | 领域 | 状态 | 最近复习 | 原因 |")
    print("|---|---|---|---|---|")
    for row, reason in items:
        print("| %s | %s | %s | %s | %s |" % (
            row.get("题目") or "", row.get("领域") or "—",
            row.get("状态") or "未看", row.get("最近复习") or "—", reason))
    print("")
    print("共 %d 道待复习。" % len(items))
    return 0


def _run_wrong(args, workspace):
    """错题本：无参数列出；--add/--remove 走既有 update 的两段式预览。"""
    if args.add and args.remove:
        print("--add 与 --remove 一次只能给一个")
        return 2
    if args.add or args.remove:
        # 标记 = 重算标签串 → 既有 update 通道（不新增写操作）
        errors, plan = preview_mark_wrong(args.add or args.remove,
                                          bool(args.add), workspace)
        return _run_preview(errors, plan, "question.update", workspace)
    rows = wrong_questions(workspace)
    if not rows:
        print("错题本为空。标记：`jobws bank wrong --add <题目id>`（加「错题」标签）")
        return 0
    print("| 题目id | 题目 | 领域 | 状态 | 最近复习 |")
    print("|---|---|---|---|---|")
    for row in rows:
        print("| %s | %s | %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            row.get("领域") or "—", row.get("状态") or "未看",
            row.get("最近复习") or "—"))
    print("")
    print("共 %d 道错题。" % len(rows))
    return 0


def _run_preview(errors, plan, op_name, workspace):
    """add / import / update / delete 四处同构的「校验 → 两段式预览」尾部。"""
    for error in errors:
        print("错误：%s" % error)
    if plan is None:
        return 1
    # 函数内 import：jobws 的 lint 分支要求被分发模块不得顶层引入三方库
    from jobws_core import approval
    result = approval.preview(op_name, workspace, plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    print("预览：%s" % result["summary"])
    for line in plan["diff"]:
        print(line)
    print("")
    print("确认后落盘：python tools/jobws.py apply %s" % result["token"])
    return 0


def _bank_changes(args):
    """add / update 共用的字段字典（同一套参数名）。"""
    return {
        "题目": args.title or "", "领域": args.domain or "", "科目": args.subject or "",
        "标签": args.tags or "", "难度": args.difficulty or "",
        "答案要点": args.answer or "", "来源": args.origin or "",
        "关联公司": args.company or "", "关联岗位": args.role or "",
        "状态": args.status or "", "备注": args.note or "",
    }


def cmd_bank(args):
    """题库：list 查、add 加（两段式）、update 改（两段式）、import 导入（两段式）。"""
    workspace = getattr(args, "workspace", None)

    if args.action == "list":
        rows = read_questions(workspace, domain=args.domain, subject=args.subject,
                              status=args.status, keyword=args.keyword)
        _print_questions(rows)
        return 0

    if args.action == "drill":
        return _cli_bank_drill.run(args, workspace)

    if args.action == "due":
        return _run_due(workspace)

    if args.action == "wrong":
        return _run_wrong(args, workspace)

    if args.action == "add":
        errors, plan = preview_add_fields(_bank_changes(args), workspace)
        return _run_preview(errors, plan, "question.add", workspace)

    if args.action == "delete":
        # 单题与批量互斥：两条路都先出预览，看过"将删哪几行"才准落盘
        if args.id and (args.domain or args.subject or args.keyword or args.origin
                        or args.company or args.today):
            print("错误：--id 与筛选条件一次只能给一个（单题用 --id；"
                  "误导入想整批撤回用 --origin 导入 --today）")
            return 2
        # 留空的值由 preview_delete_fields 过滤掉，这里不必判空
        filters = {"领域": args.domain or "", "科目": args.subject or "",
                   "关键词": args.keyword or "", "来源": args.origin or "",
                   "关联公司": args.company or ""}
        if args.today:
            filters["今天创建"] = "1"
        errors, plan = preview_delete_fields(args.id, filters, workspace)
        return _run_preview(errors, plan, "question.delete", workspace)

    if args.action == "import":
        # 目录可以换，但**不能越出工作区**：绝对路径会被 os.path.join 当成新根、
        # `..` 能翻出去，两者都先拒（后端端点不收这个参数——见 progress/questions.py）。
        module_dir = args.module_dir or MODULE_DIR
        if os.path.isabs(module_dir) or ".." in module_dir.replace("\\", "/").split("/"):
            print("错误：--module-dir 必须是工作区内的相对目录（不能是绝对路径或含 ..）")
            return 2
        errors, plan = preview_import(workspace, module_dir)
        return _run_preview(errors, plan, "question.import", workspace)

    if args.action == "export":
        # 导出只读工作区、写外部文件：不走两段式（没有要确认的写入面）
        try:
            count = export_csv(workspace, args.csv)
        except (OSError, ValueError) as exc:
            print("导出失败：%s" % exc)
            return 1
        print("已导出 %d 道题 → %s" % (count, args.csv))
        return 0

    if args.action == "import-csv":
        # 与 Markdown 导入共用同一条落盘通道（question.import）：载荷形状一致
        # （都是待写入的题目列表），差异只在预览期的来源解析与校验。
        errors, plan = preview_import_csv(args.file, workspace)
        return _run_preview(errors, plan, "question.import", workspace)

    if args.action == "update":
        errors, plan = preview_update_fields(args.id, _bank_changes(args), workspace)
        return _run_preview(errors, plan, "question.update", workspace)

    print("未知子命令：%s" % args.action)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws bank",
        description="题库：list / due / wrong / add / update / delete / drill / "
                    "import / import-csv / export（写操作走两段式）")
    subs = parser.add_subparsers(dest="action")

    p_list = subs.add_parser("list", help="列出题目（可按领域/科目/状态/关键词筛选）")
    p_list.add_argument("--domain", help="领域（如 技术面）")
    p_list.add_argument("--subject", help="科目")
    p_list.add_argument("--status", help="状态（未看/看过/会了）")
    p_list.add_argument("--keyword", "-k", help="关键词（题目/要点/标签等）")
    p_list.add_argument("--workspace", default=None)

    p_due = subs.add_parser("due", help="今日待复习（只读：未看恒在；看过 3 天 / 会了 14 天）")
    p_due.add_argument("--workspace", default=None)

    p_wrong = subs.add_parser("wrong", help="错题本（列表；--add/--remove 标记，走两段式）")
    p_wrong.add_argument("--add", metavar="题目id", help="把该题标进错题本（加「错题」标签）")
    p_wrong.add_argument("--remove", metavar="题目id", help="从错题本移除（去掉「错题」标签）")
    p_wrong.add_argument("--workspace", default=None)

    p_add = subs.add_parser("add", help="新增一道题（预览后凭令牌落盘）")
    p_add.add_argument("--title", required=True, help="题目")
    p_add.add_argument("--domain", help="领域")
    p_add.add_argument("--subject", help="科目")
    p_add.add_argument("--tags", help="标签（逗号分隔）")
    p_add.add_argument("--difficulty", default="", help="难度（易/中/难，可留空）")
    p_add.add_argument("--answer", help="答案要点")
    p_add.add_argument("--origin", default="", help="来源（自拟/笔试回忆/面试记录/导入）")
    p_add.add_argument("--company", help="关联公司")
    p_add.add_argument("--role", help="关联岗位")
    p_add.add_argument("--status", help="状态（默认 未看）")
    p_add.add_argument("--note", help="备注")
    p_add.add_argument("--workspace", default=None)

    p_update = subs.add_parser("update", help="修改一道题（改答案要点 / 标状态 / 改难度）")
    p_update.add_argument("--id", required=True, help="题目id（如 Q001，用 list 查）")
    p_update.add_argument("--title", help="题目")
    p_update.add_argument("--domain", help="领域")
    p_update.add_argument("--subject", help="科目")
    p_update.add_argument("--tags", help="标签")
    p_update.add_argument("--difficulty", help="难度（易 / 中 / 难）")
    p_update.add_argument("--answer", help="答案要点")
    p_update.add_argument("--origin", help="来源")
    p_update.add_argument("--company", help="关联公司")
    p_update.add_argument("--role", help="关联岗位")
    p_update.add_argument("--status", help="状态（未看 / 看过 / 会了）")
    p_update.add_argument("--note", help="备注")
    p_update.add_argument("--workspace", default=None)

    _cli_bank_drill.add_parser(subs)
    p_delete = subs.add_parser("delete", help="删除题目（预览后凭令牌落盘）")
    p_delete.add_argument("--id", metavar="题目id", help="精确删一题（用 list 查）")
    p_delete.add_argument("--domain", help="领域")
    p_delete.add_argument("--subject", help="科目")
    p_delete.add_argument("--keyword", "-k", help="关键词（题目 / 要点 / 标签等）")
    p_delete.add_argument("--origin", help="来源（如 导入）")
    p_delete.add_argument("--company", help="关联公司")
    p_delete.add_argument("--today", action="store_true",
                          help="只看今天创建（配 --origin 导入 可撤回今天导入的一批）")
    p_delete.add_argument("--workspace", default=None)

    p_import = subs.add_parser("import", help="从 03_面试准备/**/*.md 导入（只读解析 + 预览）")
    p_import.add_argument("--module-dir", default=MODULE_DIR, help="模块目录名")
    p_import.add_argument("--workspace", default=None)

    p_export = subs.add_parser("export", help="导出整个题库为 CSV（不覆盖已存在文件）")
    p_export.add_argument("--csv", required=True, help="导出到的 CSV 文件路径")
    p_export.add_argument("--workspace", default=None)

    p_import_csv = subs.add_parser("import-csv", help="从 CSV 导入题目（预览后凭令牌落盘）")
    p_import_csv.add_argument("file", help="要导入的 CSV（表头需含「题目」列）")
    p_import_csv.add_argument("--workspace", default=None)

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 2
    return cmd_bank(args)


if __name__ == "__main__":
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py bank ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
