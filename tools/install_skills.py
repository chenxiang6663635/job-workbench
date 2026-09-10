# -*- coding: utf-8 -*-
"""把仓库内的 skills/ 分发到本机已装的 AI CLI 目录。

各家 CLI 的 skills 目录约定不同，本脚本检测已安装的 CLI 并复制到对应位置，
使同一份 skills 源能在多个运行时下工作。

用法：
    python tools/install_skills.py                 # 检测并复制到所有已装的 CLI
    python tools/install_skills.py --dry-run       # 只报告，不复制
    python tools/install_skills.py --target all    # 复制到用户级 skills（跨运行时）
    python tools/install_skills.py --target codebuddy
    python tools/install_skills.py --prune         # 删除目标里源码已不存在的旧技能目录

目标位置：
    项目级  .codebuddy/skills/  .claude/skills/  .agents/skills/
    用户级  ~/.agents/skills/（Codex / Copilot CLI / Gemini CLI 共同识别的别名）

用户级目录是跨运行时的推荐位置，装一次所有 CLI 都能用。

**分发前会先校验**（调 tools/check_skills.py —— 校验的唯一实现）：
不合规或重名**直接拒绝分发**。把坏技能装到宿主侧只有两种下场：被跳过，或
重名被静默覆盖——**两种都不报错**，所以只能在这一头拦住。

`--prune` 只对**项目级**目标生效：用户级 ~/.agents/skills/ 是多项目共享的位置，
里面可能有别人装的技能，本脚本判断不了归属，绝不自动删。改名后残留的旧名目录
（如 `apply/`、`jd/`）会照样被宿主加载，和新的 `jwb-*` 并存，所以该清理。

退出码：0 成功，1 失败（含校验未通过）。
"""

from __future__ import print_function

import argparse
import os
import shutil
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

# 同目录的 check_skills 是校验的唯一实现：这里不重写一套规则
# （两份实现迟早分叉，而分叉掉的那一半正好就是没拦住的那一半）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_skills import describe, inspect_skills  # noqa: E402

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


def find_stale(target_dir, skill_names):
    """目标目录里存在、但源码里已没有的技能目录（改名的残留）。

    这些残留会被宿主照样加载，与新的 `jwb-*` 并存——不清理等于改名没生效。
    """
    if not os.path.isdir(target_dir):
        return []
    return sorted(d for d in os.listdir(target_dir)
                  if os.path.isdir(os.path.join(target_dir, d))
                  and d not in skill_names)


def main():
    parser = argparse.ArgumentParser(description="分发 skills 到本机 AI CLI")
    parser.add_argument("--target", default="all",
                        help="目标：all / user / codebuddy / claude / agents / codex")
    parser.add_argument("--dry-run", action="store_true", help="只报告不复制")
    parser.add_argument("--prune", action="store_true",
                        help="删除目标里源码已不存在的旧技能目录（仅项目级目标）")
    args = parser.parse_args()

    if not os.path.isdir(SKILLS_SRC):
        print("错误：找不到 skills 源目录 %s" % SKILLS_SRC)
        return 1

    # 先校验再分发：坏技能装出去的两种下场（被跳过 / 被静默覆盖）都不报错，
    # 所以装之前是唯一能拦住它的时机。--dry-run 也要校验——这正是演练的意义。
    results = inspect_skills(SKILLS_SRC)
    if any(item["problems"] for item in results):
        print("校验未通过，拒绝分发：")
        print(describe(results))
        print("")
        print("修好上面这些问题再分发。")
        return 1
    print("校验通过：%d 个技能合规（无重名、name 与目录名一致、必填项齐全）" % len(results))

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
        print("[%s] %s" % (key, desc))
        print("      %s" % path)
        if args.dry_run:
            print("      将复制（演练）")
        else:
            try:
                copy_tree(SKILLS_SRC, path)
                done += 1
                print("      已复制")
            except OSError as exc:
                print("      失败：%s" % exc)
                continue

        # 改名后残留的旧名目录：宿主照样会加载它们，与新名并存
        stale = find_stale(path, skill_names)
        if stale:
            print("      源码已不存在的旧技能目录：%s" % "、".join(stale))
            if not args.prune:
                print("      它们不会被更新；加 --prune 删除（仅项目级目标生效）")
            elif kind != "project":
                print("      --prune 不作用于用户级目录（多项目共享，判断不了归属），请手工删除")
            elif args.dry_run:
                print("      --prune 会删除它们（演练，未删除）")
            else:
                for name in stale:
                    shutil.rmtree(os.path.join(path, name))
                print("      --prune：已删除 %s" % "、".join(stale))
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
