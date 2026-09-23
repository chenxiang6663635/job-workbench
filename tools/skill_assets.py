# -*- coding: utf-8 -*-
"""分发的机制层：资产表 + 拷贝 / 建链 / 清理原语（批 10 自 install_skills.py 拆出）。

为什么拆：`install_skills.py` 到 324 行破了规模预算；拆点选在「机制」与「编排」之间——
本模块只回答「资产从哪来、落哪去、怎么落」，不含任何输出与参数解析，
因此可以被四端检查器（`four_ends_extras` 从 `ASSETS` 派生镜像目标）与测试直接复用。
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_skills import LEGACY_NAMES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 资产清单：真源目录相对仓库根 → 各落点 (目标标识, 说明, 路径类型, 相对路径)。
# 目标标识在多个资产间重复（codebuddy / claude 各有三类资产）——`--target codebuddy`
# 就是「装这个宿主的全部资产」，与用户直觉一致。
#
# 为什么 commands / agents 只落 `.codebuddy/` 与 `.claude/`：前者的命令 / 子代理
# 目录约定来自本仓库自身的宿主与插件清单（`.codebuddy-plugin/plugin.json`），后者是
# Claude Code 有文档的 `.claude/commands`、`.claude/agents`。`.agents/` 与 `.codex/`
# 目前只约定 **skills** 目录——命令与子代理的目录约定没有依据，往宿主目录里放它不认
# 的东西，比少装一处更糟。
ASSETS = [
    ("skills", "skills", [
        ("user", "用户级 ~/.agents/skills/（跨运行时，推荐）", "user", None),
        ("codebuddy", "项目级 .codebuddy/skills/", "project", ".codebuddy/skills"),
        ("claude", "项目级 .claude/skills/", "project", ".claude/skills"),
        ("agents", "项目级 .agents/skills/", "project", ".agents/skills"),
        ("codex", "项目级 .codex/skills/", "project", ".codex/skills"),
    ]),
    ("commands", "commands", [
        ("codebuddy", "项目级 .codebuddy/commands/", "project", ".codebuddy/commands"),
        ("claude", "项目级 .claude/commands/", "project", ".claude/commands"),
    ]),
    ("agents", "agents", [
        ("codebuddy", "项目级 .codebuddy/agents/", "project", ".codebuddy/agents"),
        ("claude", "项目级 .claude/agents/", "project", ".claude/agents"),
    ]),
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


def link_tree(src, dst):
    """逐项建符号链接（--link）。返回 (已建链, 跳过, 失败)。

    已存在的**真实副本**不替换：用户可能在那里放了自己改过的版本，静默覆盖不可接受。
    已存在的链接则重建（幂等：重跑不会累积）。

    重建走「先建临时链 → `os.replace` 原子替换」：直接 unlink 再 symlink 的话，
    建链失败（权限不足）会把原有的好链弄丢——那是把可用的分发变成坏的。
    """
    if not os.path.isdir(dst):
        os.makedirs(dst)
    linked, skipped, failed = [], [], []
    for item in sorted(os.listdir(src)):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.exists(d) and not os.path.islink(d):
            skipped.append(item)
            continue
        tmp = d + ".jobws-tmp"
        try:
            if os.path.islink(tmp):
                os.unlink(tmp)
            os.symlink(s, tmp, target_is_directory=os.path.isdir(s))
            os.replace(tmp, d)
            linked.append(item)
        except OSError as exc:
            failed.append("%s（%s）" % (item, exc))
            if os.path.islink(tmp):
                os.unlink(tmp)
    return linked, skipped, failed


def is_inside_repo(path):
    """目标是否真的落在本仓库内。

    --prune 承诺只对**项目级**目标生效，而「项目级」是按 ASSETS 表里的 kind
    静态判断的。若 .claude / .agents 是指向用户目录的符号链接或 junction（很常见
    的配置共享做法），kind 仍然是 project，那道保护就失效了。删之前用 realpath
    确认它确实在仓库里。
    """
    repo = os.path.realpath(ROOT)
    target = os.path.realpath(path)
    return target == repo or target.startswith(repo + os.sep)


def find_legacy(target_dir):
    """目标目录里**改名前的旧名**目录（apply / jd / resume / track / recruit-coach）。

    只认这五个已知旧名。早先的实现是「凡不在源码名单里的目录都算陈旧」，
    那会把用户自己装的第三方技能（比如从教程里装的 pdf-fill）一起删掉，
    没有确认、没有备份。要清理的是这五个名字，不是「一切陌生目录」。
    """
    if not os.path.isdir(target_dir):
        return []
    return sorted(d for d in os.listdir(target_dir)
                  if d in LEGACY_NAMES and os.path.isdir(os.path.join(target_dir, d)))
