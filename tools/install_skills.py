# -*- coding: utf-8 -*-
"""把仓库内的技能、命令与子代理分发到本机已装的 AI CLI 目录。

各家 CLI 的目录约定不同，本脚本把这些资产复制到对应位置，使同一份真源
（仓库内的 `skills/`、`commands/`、`agents/`）能在多个运行时下工作。

用法：
    python tools/install_skills.py                 # 分发三类资产到所有已装 CLI
    python tools/install_skills.py --dry-run       # 只报告，不复制
    python tools/install_skills.py --target claude # 只装某一个宿主
    python tools/install_skills.py --prune         # 删除目标里源码已不存在的旧技能目录
    python tools/install_skills.py --link          # 实验：改用符号链接（默认拷贝）

落点（批 10 从「只有 skills」扩到三类资产，表在 tools/skill_assets.py）：

    skills    用户级 ~/.agents/skills/（跨运行时，推荐）
              项目级 .codebuddy/skills/  .claude/skills/  .agents/skills/  .codex/skills/
    commands  项目级 .codebuddy/commands/  .claude/commands/
    agents    项目级 .codebuddy/agents/    .claude/agents/

为什么 commands / agents 也要分发：它们是「仓库即插件」的另一半——`.codebuddy-plugin/`
清单里登记了 5 个命令与 2 个子代理，只装技能等于插件壳只生效一半。
**只落 `.codebuddy/` 与 `.claude/`**：前者的目录约定来自本仓库自身的宿主与插件清单，
后者是 Claude Code 有文档的 `.claude/commands`、`.claude/agents`；`.agents/` 与
`.codex/` 目前只约定 **skills** 目录——命令与子代理的目录约定没有依据，往宿主目录里
放它不认的东西，比少装一处更糟。

**分发前会先校验**（调 tools/check_skills.py 与 tools/check_plugin_assets.py —— 校验的
唯一实现，含技能 / 插件壳的版本号一致性）：不合规或重名**直接拒绝分发**。把坏资产装到
宿主侧只有两种下场：被跳过，或重名/格式错被静默忽略——**两种都不报错**，所以只能在这一
头拦住。

`--link`（实验）用符号链接代替拷贝：真源改一次，五个落点同时生效，不再有「副本过期」。
Windows 上建符号链接需要开发者模式或管理员权限，失败会明确报错并提示改回默认拷贝；
已存在的真实副本**不替换**（避免误删用户数据），只提示先手动删除。

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


# 同目录的 check_skills 是校验的唯一实现：这里不重写一套规则
# （两份实现迟早分叉，而分叉掉的那一半正好就是没拦住的那一半）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_skills import describe, inspect_skills  # noqa: E402
# 机制层（表与原语）另置一处：本文件只做「校验 → 遍历 → 输出」的编排。
# ASSETS 在这里**原样再导出**，四端检查器仍可从本模块取到镜像目标表。
from skill_assets import (  # noqa: E402
    ASSETS, ROOT, copy_tree, find_legacy, is_inside_repo, link_tree, resolve_path,
)


def _build_parser():
    parser = argparse.ArgumentParser(description="分发技能 / 命令 / 子代理到本机 AI CLI")
    parser.add_argument("--target", default="all",
                        help="目标：all / user / codebuddy / claude / agents / codex")
    parser.add_argument("--dry-run", action="store_true", help="只报告不复制")
    parser.add_argument("--prune", action="store_true",
                        help="删除目标里源码已不存在的旧技能目录（仅项目级目标）")
    parser.add_argument("--link", action="store_true",
                        help="实验：改用符号链接（Windows 需开发者模式或管理员权限）")
    return parser


def _validate(root):
    """分发前的双重校验：技能 + 插件资产（命令与子代理）。

    两种坏法都不报错：技能被跳过 / 重名被静默覆盖；命令与子代理的 frontmatter
    写坏了宿主同样只是不加载。所以装之前是唯一能拦住它们的时机。
    """
    ok = True

    results = inspect_skills(os.path.join(root, "skills"))
    if any(item["problems"] for item in results):
        print("技能校验未通过，拒绝分发：")
        print(describe(results))
        ok = False
    else:
        print("技能校验通过：%d 个合规（无重名、name 与目录名一致、必填项齐全）"
              % len(results))

    # 函数内 import：check_plugin_assets 反向引用 check_skills 的 frontmatter 解析器，
    # 模块级互相 import 会成环（同 check_skills.main 的处理）。
    from check_plugin_assets import inspect_plugin_assets
    findings = inspect_plugin_assets(root)
    if findings:
        print("插件资产校验未通过，拒绝分发：")
        for label, problems in findings:
            print("  [%s]" % label)
            for problem in problems:
                print("    - %s" % problem)
        ok = False
    else:
        print("插件资产校验通过（命令与子代理的 frontmatter 齐全）")
    return ok


def _handle_legacy(path, kind, legacy, args):
    """改名后残留的旧名目录：宿主照样会加载它们，与新名并存——按目标类型处置。"""
    if kind != "project":
        # 用户级共享目录：不列"陈旧"（会把别人装的技能也算进来），只提示
        print("      发现旧名目录：%s" % "、".join(legacy))
        print("      这是多项目共享位置，判断不了归属，请人工确认后删除")
        return
    print("      发现旧名目录：%s" % "、".join(legacy))
    if not args.prune:
        print("      加 --prune 删除它们（旧名会被宿主照样加载，与新名并存）")
        return
    if args.dry_run:
        print("      --prune 会删除它们（演练，未删除）")
        return
    if not is_inside_repo(path):
        print("      目标不在本仓库内（符号链接？），拒绝删除：%s" % path)
        return
    removed = []
    for name in legacy:
        # rmtree 遇到符号链接会抛 OSError；不接住的话前面已删的回不来
        try:
            shutil.rmtree(os.path.join(path, name))
            removed.append(name)
        except OSError as exc:
            print("      删除 %s 失败：%s" % (name, exc))
    if removed:
        print("      --prune：已删除 %s" % "、".join(removed))


def _install_one(asset, src, key, desc, kind, rel, args):
    """分发单个资产到单个落点，返回是否成功（演练视为成功）。"""
    target = resolve_path(kind, rel)
    print("  [%s] %s" % (key, desc))
    print("        %s" % target)
    if args.dry_run:
        print("        将建符号链接（演练）" if args.link else "        将复制（演练）")
    else:
        try:
            if args.link:
                linked, skipped, failed = link_tree(src, target)
                print("        已建链 %d 项" % len(linked))
                if skipped:
                    print("        以下项已是真实副本，未替换（先手动删除再用 --link）：%s"
                          % "、".join(skipped))
                if failed:
                    print("        以下项建链失败：%s" % "、".join(failed))
                    return False
            else:
                copy_tree(src, target)
                print("        已复制")
        except OSError as exc:
            print("        失败：%s" % exc)
            if args.link:
                print("        符号链接需要权限：Windows 请开启开发者模式或以管理员运行；"
                      "也可去掉 --link 用默认拷贝")
            return False

    # 旧名残留只与技能目录有关（commands / agents 没有历史改名）
    if asset == "skills":
        legacy = find_legacy(target)
        if legacy:
            _handle_legacy(target, kind, legacy, args)
    return True


def main():
    args = _build_parser().parse_args()

    # 真源缺失＝显式失败：静默「分发到 0 个位置」会让调用方以为装好了
    # （独立审查 MAJOR-2：旧实现在这里 return 1，泛化时不该丢）。
    skills_dir = os.path.join(ROOT, "skills")
    if not os.path.isdir(skills_dir):
        print("错误：找不到 skills 源目录 %s" % skills_dir)
        return 1
    if not [n for n in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, n))]:
        print("错误：%s 下没有任何技能目录——多半是路径不对，拒绝分发" % skills_dir)
        return 1

    if not _validate(ROOT):
        print("")
        print("修好上面这些问题再分发：不合规的资产会被宿主跳过，重名的会被静默覆盖。")
        return 1

    known = {key for _asset, _rel, targets in ASSETS for key, _d, _k, _r in targets}
    if args.target != "all" and args.target not in known:
        print("错误：未知的 --target `%s`" % args.target)
        print("可选：all、%s" % "、".join(sorted(known)))
        return 1

    print("")
    done = 0
    for asset, rel_src, targets in ASSETS:
        src = os.path.join(ROOT, rel_src)
        if not os.path.isdir(src):
            continue
        selected = [t for t in targets if args.target in ("all", t[0])]
        if not selected:
            continue
        count = len([n for n in os.listdir(src)
                     if os.path.isdir(os.path.join(src, n))]) \
            if asset == "skills" else len([n for n in os.listdir(src) if n.endswith(".md")])
        print("== %s（%d 项）==" % (asset, count))
        for key, desc, kind, rel in selected:
            if _install_one(asset, src, key, desc, kind, rel, args):
                done += 1
        print("")

    if args.dry_run:
        print("演练模式，未写入。去掉 --dry-run 实际执行。")
    else:
        print("完成：已处理 %d 个落点（技能 / 命令 / 子代理；拷贝是幂等的）。" % done)
        print("")
        print("若之后新增或修改了 skills/、commands/、agents/，重跑本脚本即可同步。")
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py skills install ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
