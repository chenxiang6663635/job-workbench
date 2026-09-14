# -*- coding: utf-8 -*-
"""求职工作台的**唯一**命令行入口。

为什么合并：`tools/` 下曾有 8 个各自可执行的脚本，文档、CI、技能资产里散着
几十处 `python tools/xxx.py`；一个入口之后，用户只需记住 `jobws`，迁移对照表
见 CHANGELOG 与 Release 说明。

**刻意保留的一件事**：各脚本的 argparse 与 `main()` 都留在原处，jobws 只做
第一层分发——把剩余参数**原样转发**给对应模块。这样：

- 参数名、子命令、退出码（0 通过 / 1 业务失败 / 2 用法或配置错误）**一字不改**，
  `tests/test_cli_surface.py` 那张安全网可以平移过来继续钉；
- 后端 `web/backend/` 与 MCP 包照旧 import 这些模块，领域层没动；
- 本批不把 argparse 搬进 jobws——那是「抽领域层」的下一刀，混进这次破坏性
  变更会让 diff 大到没人审得动。

用法：

    python tools/jobws.py --help            列出全部命令
    python tools/jobws.py track --help      看 track 的 10 个子命令
    python tools/jobws.py track list --stage 一面
    python tools/jobws.py init --demo
    python tools/jobws.py lint pr-title     校验环境变量 PR_TITLE（CI 用）
"""

from __future__ import print_function

import argparse
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import check_pr_title  # noqa: E402
import check_skills  # noqa: E402
import init_workspace  # noqa: E402
import install_skills  # noqa: E402
import jd_score  # noqa: E402
import report  # noqa: E402
import resume_build  # noqa: E402
import tracker  # noqa: E402

# (命令, 模块或 None, 一句话说明)。顺序即 --help 的展示顺序。
# 模块为 None 表示这一层还有子命令（见 SUB_TARGETS）。
TARGETS = [
    ("track", tracker, "投递追踪：增删查改、面试/联系人/offer、导入与自检"),
    ("report", report, "复盘与统计（转化率、停留时长、失败归因）"),
    ("resume", resume_build, "按岗位生成投递材料"),
    ("jd", jd_score, "JD 解析与岗位评分"),
    ("init", init_workspace, "初始化工作区（--demo 铺示例数据）"),
    ("skills", None, "技能资产（install 分发 / check 校验）"),
    ("lint", None, "检查器（pr-title 校验 PR 标题规范）"),
]

# (顶层命令, 子命令) -> 模块
SUB_TARGETS = {
    ("skills", "install"): install_skills,
    ("skills", "check"): check_skills,
    ("lint", "pr-title"): check_pr_title,
}

SUB_CHOICES = {"skills": ["install", "check"], "lint": ["pr-title"]}


def build_parser():
    """只解析**到命令这一层**，其余参数留给模块自己（见 main 的说明）。"""
    parser = argparse.ArgumentParser(
        prog="jobws",
        description="求职工作台命令行（唯一入口）",
        epilog="每个命令后面接 --help 看它自己的子命令，例如：jobws track --help")
    subs = parser.add_subparsers(dest="group", metavar="<命令>")

    for name, module, help_text in TARGETS:
        # add_help=False 是必须的：否则 `jobws track --help` 会被这一层吃掉，
        # 打印的是 jobws 自己的说明，用户看不到 track 的 10 个子命令。
        sub = subs.add_parser(name, help=help_text, add_help=False)
        if module is None:
            sub.add_argument("sub", metavar="<子命令>",
                             help="可选：%s" % " / ".join(SUB_CHOICES[name]))
    return parser


def _dispatch(module, rest):
    """把参数交给模块的 main：参数名与退出码语义由各模块自己负责。

    改 sys.argv 而不是传参：8 个模块里只有 check_pr_title 的 main 显式接受
    argv，其余都从 sys.argv 解析——统一改 sys.argv 对两边都成立，也不必去
    改它们的签名。
    """
    saved = sys.argv
    sys.argv = [module.__name__] + list(rest)
    try:
        return module.main()
    finally:
        sys.argv = saved


def main(argv=None):
    parser = build_parser()
    # parse_known_args 而不是 REMAINDER：subparser 里用 REMAINDER 收集剩余参数时，
    # `--help` 会被当成未识别选项回传到顶层（argparse 的已知组合坑），结果
    # `jobws track --help` 报 unrecognized arguments。改成"认识多少解析多少、
    # 剩下的原样转发"之后，--help 与所有子命令参数都进 rest。
    args, rest = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    if not getattr(args, "group", None):
        parser.print_help()
        return 1

    sub = getattr(args, "sub", None)
    if sub:
        module = SUB_TARGETS.get((args.group, sub))
        if module is None:
            print("未知子命令：%s %s（可选：%s）"
                  % (args.group, sub, " / ".join(SUB_CHOICES.get(args.group, []))))
            return 2
    else:
        module = None
        for name, mod, _help in TARGETS:
            if name == args.group:
                module = mod
                break
        if module is None:
            print("命令缺少子命令：%s" % args.group)
            return 2

    try:
        code = _dispatch(module, rest)
    except SystemExit as exc:
        # argparse 的 --help(0) 与用法错误(2) 都走这里：必须原样透出，
        # 否则 `jobws track --help` 会被误报成失败
        return 0 if exc.code is None else exc.code
    return 0 if code is None else code


if __name__ == "__main__":
    sys.exit(main())
