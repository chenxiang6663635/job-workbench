# -*- coding: utf-8 -*-
"""校验 PR 标题是否符合提交规范（格式 + 中文）。

为什么需要它：squash 合并会把 PR 标题**直接变成主干上的提交 subject**，
而本地 pre-commit / commit-msg 只在开发者自己敲 `git commit` 时运行——
标题由服务器生成，任何本地钩子都拦不到。所以这一刀只能由 CI 补。

用法：
    python tools/check_pr_title.py                    # 读环境变量 PR_TITLE
    python tools/check_pr_title.py --title "feat: 中文说明"

CI 里请走环境变量而不是把标题拼进 shell 命令：PR 标题是外部可控输入，
`run: ... "${{ github.event.pull_request.title }}"` 形式会被 shell 解释，
带引号/反引号的标题可能变成命令注入。环境变量传递不经过 shell 解析。

退出码：0 通过，1 不合规，2 没拿到标题（配置问题，不该静默算通过）。
"""

from __future__ import print_function

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import commit_header  # noqa: E402

TAG = "[pr-title]"


def main(argv=None):
    """argv=None 时取 sys.argv[1:]；显式传入便于测试，不必改全局 sys.argv。"""
    parser = argparse.ArgumentParser(description="校验 PR 标题")
    parser.add_argument("--title", help="PR 标题；不给则读环境变量 PR_TITLE")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    title = args.title if args.title is not None else os.environ.get("PR_TITLE")
    if not title:
        print("%s[FAIL] 没拿到 PR 标题（--title 或环境变量 PR_TITLE 都没有）" % TAG)
        return 2

    problems = commit_header.validate(title, source=commit_header.SOURCE_PR_TITLE)
    if problems:
        for problem in problems:
            print("%s[FAIL] %s" % (TAG, problem))
        print("")
        print("PR 标题在 squash 合并后会直接成为主干上的提交 subject，因此与提交信息同一套规则。")
        print("改标题：gh pr edit <编号> --title \"feat(scope): 中文说明\"")
        return 1

    print("%s[OK] %s" % (TAG, title))
    return 0


if __name__ == "__main__":
    sys.exit(main())
