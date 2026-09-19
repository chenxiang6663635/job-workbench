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

from jobws_core.question_bank import (MODULE_DIR, preview_add_fields, preview_import,  # noqa: E402
                           preview_update_fields, read_questions)


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


def _run_preview(errors, plan, op_name, workspace):
    """add / import / update 三处同构的「校验 → 两段式预览」尾部。"""
    for error in errors:
        print("错误：%s" % error)
    if plan is None:
        return 1
    # 函数内 import：jobws 的 lint 分支要求被分发模块不得顶层引入三方库
    import approval
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

    if args.action == "add":
        errors, plan = preview_add_fields(_bank_changes(args), workspace)
        return _run_preview(errors, plan, "question.add", workspace)

    if args.action == "import":
        # 目录可以换，但**不能越出工作区**：绝对路径会被 os.path.join 当成新根、
        # `..` 能翻出去，两者都先拒（后端端点不收这个参数——见 progress/questions.py）。
        module_dir = args.module_dir or MODULE_DIR
        if os.path.isabs(module_dir) or ".." in module_dir.replace("\\", "/").split("/"):
            print("错误：--module-dir 必须是工作区内的相对目录（不能是绝对路径或含 ..）")
            return 2
        errors, plan = preview_import(workspace, module_dir)
        return _run_preview(errors, plan, "question.import", workspace)

    if args.action == "update":
        errors, plan = preview_update_fields(args.id, _bank_changes(args), workspace)
        return _run_preview(errors, plan, "question.update", workspace)

    print("未知子命令：%s" % args.action)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws bank", description="题库：list / add / update / import（写操作走两段式）")
    subs = parser.add_subparsers(dest="action")

    p_list = subs.add_parser("list", help="列出题目（可按领域/科目/状态/关键词筛选）")
    p_list.add_argument("--domain", help="领域（如 技术面）")
    p_list.add_argument("--subject", help="科目")
    p_list.add_argument("--status", help="状态（未看/看过/会了）")
    p_list.add_argument("--keyword", "-k", help="关键词（题目/要点/标签等）")
    p_list.add_argument("--workspace", default=None)

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

    p_import = subs.add_parser("import", help="从 03_面试准备/**/*.md 导入（只读解析 + 预览）")
    p_import.add_argument("--module-dir", default=MODULE_DIR, help="模块目录名")
    p_import.add_argument("--workspace", default=None)

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 2
    return cmd_bank(args)


if __name__ == "__main__":
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py bank ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
