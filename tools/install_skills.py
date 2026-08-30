# -*- coding: utf-8 -*-
"""把仓库内的 skills/ 分发到本机已装的 AI CLI 目录。

各家 CLI 的 skills 目录约定不同，本脚本检测已安装的 CLI 并复制到对应位置，
使同一份 skills 源能在多个运行时下工作。

用法：
    python tools/install_skills.py                 # 检测并复制到所有已装的 CLI
    python tools/install_skills.py --dry-run       # 只报告，不复制
    python tools/install_skills.py --target all    # 复制到用户级 skills（跨运行时）
    python tools/install_skills.py --target codebuddy

目标位置：
    项目级  .codebuddy/skills/  .claude/skills/  .agents/skills/
    用户级  ~/.agents/skills/（Codex / Copilot CLI / Gemini CLI 共同识别的别名）

用户级目录是跨运行时的推荐位置，装一次所有 CLI 都能用。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import os
import shutil
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_SRC = os.path.join(ROOT, "skills")

# (目标标识, 说明, 路径生成函数使用的类型, 路径)
TARGETS = [
    ("user", "用户级 ~/.agents/skills/（跨运行时，推荐）", "user", None),
    ("codebuddy", "项目级 .codebuddy/skills/", "project", ".codebuddy/skills"),
    ("claude", "项目级 .claude/skills/", "project", ".claude/skills"),
    ("agents", "项目级 .agents/skills/", "project", ".agents/skills"),
    ("codex", "项目级 .codex/skills/", "project", ".codex/skills"),
]


def resolve_path(kind, rel):
    if kind == "user":
        home = os.path.expanduser("~")
        return os.path.join(home, ".agents", "skills")
    return os.path.join(ROOT, rel)


def copy_tree(src, dst):
    if not os.path.isdir(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d)
        else:
            shutil.copy2(s, d)


def main():
    parser = argparse.ArgumentParser(description="分发 skills 到本机 AI CLI")
    parser.add_argument("--target", default="all",
                        help="目标：all / user / codebuddy / claude / agents / codex")
    parser.add_argument("--dry-run", action="store_true", help="只报告不复制")
    args = parser.parse_args()

    if not os.path.isdir(SKILLS_SRC):
        print("错误：找不到 skills 源目录 %s" % SKILLS_SRC)
        return 1

    skill_names = sorted(d for d in os.listdir(SKILLS_SRC)
                         if os.path.isdir(os.path.join(SKILLS_SRC, d)))
    print("待分发的 skills（%d 个）：%s" % (len(skill_names), "、".join(skill_names)))
    print("")

    selected = [t for t in TARGETS if args.target == "all" or t[0] == args.target]
    if not selected:
        print("错误：未知的 --target `%s`" % args.target)
        print("可选：all、%s" % "、".join(t[0] for t in TARGETS))
        return 1

    done = 0
    for key, desc, kind, rel in selected:
        path = resolve_path(kind, rel)
        action = "将复制" if args.dry_run else "已复制"
        print("[%s] %s" % (key, desc))
        print("      %s" % path)
        if not args.dry_run:
            try:
                copy_tree(SKILLS_SRC, path)
                done += 1
            except OSError as exc:
                print("      失败：%s" % exc)
                continue
        print("")

    if args.dry_run:
        print("演练模式，未写入。去掉 --dry-run 实际执行。")
    else:
        print("完成：已分发到 %d 个位置。" % done)
        print("")
        print("若之后新增或修改了 skills/，重跑本脚本即可同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
