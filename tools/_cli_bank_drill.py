# -*- coding: utf-8 -*-
"""`jobws bank drill` 的命令层：抽一轮题（**只读**，刻意不打印答案要点）。

为什么单独成模块：`_cli_bank.py` 在「删除」与「抽题」两条命令合流后顶破了规模预算
（文件 ≤300 行 / 函数 ≤80 行），而抽题是里面唯一「读 + 打印」的独立段落——按
`_cli_export_notes.py` 的先例拆出来。命令名、参数与输出逐字未变，只是换了住处。

为什么不带答案：抽题的目的是「先答一遍」，答案就在旁边等于没练——看一眼答案就算
复习过，是最常见也最没用的自欺。要看答案用 `bank list --keyword …`。
"""

from __future__ import print_function

from jobws_core.question_bank import read_questions  # noqa: E402
from jobws_core.question_drill import pick_drill  # noqa: E402


def add_parser(subs):
    """注册 `drill` 子命令（参数、帮助文案与拆分前逐字一致）。"""
    p_drill = subs.add_parser("drill", help="抽一轮题（只读；不打印答案要点）")
    p_drill.add_argument("--mode", default="due", choices=("due", "wrong", "random"),
                         help="due=重练队列（错题∪待复习）/ wrong=只错题 / random=随机")
    p_drill.add_argument("--n", type=int, default=5,
                         help="一轮几道（默认 5，上限 20）")
    p_drill.add_argument("--domain", help="领域")
    p_drill.add_argument("--subject", help="科目")
    p_drill.add_argument("--status", help="状态（未看 / 看过 / 会了）")
    p_drill.add_argument("--keyword", "-k", help="关键词（题目 / 要点 / 标签等）")
    p_drill.add_argument("--workspace", default=None)
    return p_drill


def run(args, workspace):
    """抽一轮题并打印问法（退出码：0 成功 / 2 参数不合法）。"""
    rows = read_questions(workspace, domain=args.domain, subject=args.subject,
                          status=args.status, keyword=args.keyword)
    try:
        picked = pick_drill(rows, mode=args.mode, n=args.n)
    except ValueError as exc:
        print("错误：%s" % exc)
        return 2
    if not picked:
        print("没有可抽的题：题库是空的，或当前筛选 / 模式下没有命中。")
        return 0
    print("| 题目id | 题目 | 领域 / 科目 | 状态 |")
    print("|---|---|---|---|")
    for row in picked:
        print("| %s | %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            "%s / %s" % (row.get("领域") or "—", row.get("科目") or "—"),
            row.get("状态") or "未看"))
    print("")
    print("共 %d 道（模式 = %s）。答案要点刻意不打印——先盲答，再对答案。" % (
        len(picked), args.mode))
    return 0
