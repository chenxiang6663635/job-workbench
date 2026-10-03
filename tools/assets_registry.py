#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资产清单的唯一真源（issue #205）：插件清单生成器 + 漂移检查。

**背景**：`.codebuddy-plugin/plugin.json` 与 `marketplace.json` 里的三份清单
（skills / commands / agents）此前是**手写副本**，描述里的数量措辞还各写一份
（实测 5 处）——`jwb-domain-setup` 加入时 marketplace 漏改（8 vs 9），当时的
补丁是"加校验器互校"（PR #200）。本模块把关系倒过来：**清单从磁盘派生、数量
从清单派生**，两份 JSON 由本模块生成，校验器改为「生成物无漂移」。

**真源与派生规则**：
- **集合**的真源 = 磁盘：`skills/jwb-*` 目录、`commands/*.md`、`agents/*.md`；
- **展示顺序**：skills / agents 用字母序（磁盘事实）；**commands 用下面的
  显式顺序**——命令排列是产品决策（today → apply-pack → retro → bank → jd），
  不是字母序。新增命令必须同时登记进 `COMMAND_ORDER`（刻意的摩擦：顺序是
  产品决策，不允许静默追加）；
- **版本号**：从 `web/electron/package.json` 读——那是版本唯一真源
  （见 CONTRIBUTING「版本号体系」）；plugin.json 的 version 由此派生；
- **数量措辞**：由清单长度派生（`{skills}` / `{commands}` / `{agents}` 占位）。

**为什么不"写完自动同步"**：生成式写盘没有可靠触发时机（改磁盘目录不会触发
任何钩子）。因此采用显式两段式：`--write` 重新生成、`--check` 在 CI 上比对
（空即绿）——与仓库其它生成物（four-ends 文档）同款纪律。

用法：
    python tools/assets_registry.py --check    # CI / 本地：生成物与真源是否漂移
    python tools/assets_registry.py --write    # 手改真源（加技能/命令/子代理）后重新生成
"""

from __future__ import print_function

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = ".codebuddy-plugin"

# commands 的展示顺序（产品决策，不是字母序）——新增命令必须登记在这里。
COMMAND_ORDER = ("today", "apply-pack", "retro", "bank", "jd")

# 描述文本的模板：`{skills}` / `{commands}` / `{agents}` 由清单长度派生填装。
# 文本本身是**手写维护的**（叙述是产品文案），但数量不再是。
DESCRIPTIONS = {
    "plugin": (
        "本地优先的求职工作台：投递追踪 / 岗位评估 / 简历 / 投递执行 / 教练"
        "（技能 {skills} 个、命令 {commands} 个、子代理 {agents} 个）"
    ),
    "marketplace_zh": (
        "求职工作台的 CodeBuddy 插件：{skills} 个技能——五个求职向（投递追踪 / 岗位评估 / "
        "简历 / 投递执行 / 教练）+ 一个扩展向（领域插件生成）+ 三个开发向（CLI 契约 / "
        "API 审查 / MCP 指南）。数据与命令都在这台机器上，CLI 与可选 MCP 见仓库 README。"
    ),
    "marketplace_en": (
        "Job Workbench plugin for CodeBuddy: {skills} skills — five job-hunting "
        "(application tracking, job evaluation, resume, applying, coaching), one "
        "setup/extension skill (domain profile generation), plus three maintainer-facing "
        "(CLI contract, API review, MCP guide). All data and commands stay on this machine; "
        "see the repository README for the CLI and optional MCP server."
    ),
    "marketplace_plugin_zh": (
        "求职工作台技能包（{skills} 个技能）：求职向——投递追踪（jwb-track）/ 岗位评估"
        "（jwb-jd）/ 简历（jwb-resume）/ 投递执行（jwb-apply）/ 求职教练（jwb-recruit-coach）；"
        "扩展向——领域插件生成（jwb-domain-setup）；开发向——CLI 契约（jwb-cli-contract）/ "
        "API 审查（jwb-api-review）/ MCP 指南（jwb-mcp-server）。技能调用仓库内的 jobws CLI；"
        "插件内容即本仓库（技能在 skills/ 下，插件机制按约定读它——不另做镜像）。"
    ),
    "marketplace_plugin_en": (
        "Skills for Job Workbench ({skills} skills): job-hunting — application tracker, "
        "job-pool evaluation, resume workshop, applying, and a recruiting coach; "
        "setup/extension — domain profile generation; maintainer-facing — CLI contract, "
        "API review, and MCP guide. Skills drive the in-repo jobws CLI; the plugin content "
        "is this repository itself (skills live in skills/ — no second copy is maintained)."
    ),
}

REPO_URL = "https://github.com/chenxiang6663635/job-workbench"
# 注意：plugins[0].author.url 是**作者主页**、不是仓库地址（两者不同，别用 REPO_URL 顶）。
AUTHOR_URL = "https://github.com/chenxiang6663635"
AUTHOR = "chenxiang6663635"
LICENSE = "MIT"


def _list_skills(repo_root):
    """skills/ 下的技能目录名（jwb- 前缀），字母序。"""
    base = os.path.join(repo_root, "skills")
    if not os.path.isdir(base):
        return []
    return sorted(name for name in os.listdir(base)
                  if name.startswith("jwb-") and os.path.isdir(os.path.join(base, name)))


def _list_commands(repo_root):
    """commands/*.md 的基名，按 COMMAND_ORDER 排（顺序即产品决策）。"""
    base = os.path.join(repo_root, "commands")
    if not os.path.isdir(base):
        return []
    on_disk = sorted(name[:-3] for name in os.listdir(base) if name.endswith(".md"))
    return on_disk


def _list_agents(repo_root):
    """agents/*.md 的基名，字母序。"""
    base = os.path.join(repo_root, "agents")
    if not os.path.isdir(base):
        return []
    return sorted(name[:-3] for name in os.listdir(base) if name.endswith(".md"))


def _app_version(repo_root):
    """版本唯一真源：web/electron/package.json（CONTRIBUTING「版本号体系」）。"""
    path = os.path.join(repo_root, "web", "electron", "package.json")
    with io.open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)["version"]


def load_registry(repo_root):
    """真源快照：三类清单 + 派生计数 + 一切生成所需的常量。"""
    skills = _list_skills(repo_root)
    commands = _list_commands(repo_root)
    agents = _list_agents(repo_root)
    return {
        "version": _app_version(repo_root),
        "skills": skills,
        "commands": commands,
        "agents": agents,
        "counts": {"skills": len(skills), "commands": len(commands), "agents": len(agents)},
    }


def validate_registry(reg):
    """真源自身的问题（空清单、命令顺序未登记）——返回问题列表。"""
    problems = []
    if not reg["skills"]:
        problems.append("skills/ 下没有 jwb-* 技能目录——插件清单会是空的")
    missing = [name for name in reg["commands"] if name not in COMMAND_ORDER]
    if missing:
        problems.append(
            "commands/ 下有未登记展示顺序的命令：%s——请把它们加进 assets_registry.COMMAND_ORDER"
            % ", ".join(sorted(missing)))
    absence = [name for name in COMMAND_ORDER if name not in reg["commands"]]
    if absence:
        problems.append(
            "COMMAND_ORDER 里登记了磁盘上不存在的命令：%s——删掉登记或补上文件"
            % ", ".join(absence))
    return problems


def _skill_paths(skills):
    return ["./skills/%s" % name for name in skills]


def _agent_paths(agents):
    return ["./agents/%s.md" % name for name in agents]


def _command_paths(commands):
    ordered = [name for name in COMMAND_ORDER if name in commands]
    ordered += [name for name in commands if name not in COMMAND_ORDER]
    return ["./commands/%s.md" % name for name in ordered]


def render_plugin_json(reg):
    """plugin.json 的完整文本（缩进 2 / UTF-8 / 尾换行——与既有文件逐字节同形）。"""
    doc = {
        "name": "job-workbench",
        "version": reg["version"],
        "description": DESCRIPTIONS["plugin"].format(**reg["counts"]),
        "author": {"name": AUTHOR},
        "repository": REPO_URL,
        "homepage": REPO_URL,
        "license": LICENSE,
        "skills": _skill_paths(reg["skills"]),
        "agents": _agent_paths(reg["agents"]),
        "commands": _command_paths(reg["commands"]),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def render_marketplace_json(reg):
    """marketplace.json 的完整文本。"""
    doc = {
        "name": "job-workbench",
        "description": DESCRIPTIONS["marketplace_zh"].format(**reg["counts"]),
        "description_en": DESCRIPTIONS["marketplace_en"].format(**reg["counts"]),
        "owner": {"name": AUTHOR},
        "plugins": [{
            "name": "job-workbench",
            "description": DESCRIPTIONS["marketplace_plugin_zh"].format(**reg["counts"]),
            "description_en": DESCRIPTIONS["marketplace_plugin_en"].format(**reg["counts"]),
            "source": "./",
            "skills": _skill_paths(reg["skills"]),
            "agents": _agent_paths(reg["agents"]),
            "commands": _command_paths(reg["commands"]),
            "author": {"name": AUTHOR, "url": AUTHOR_URL},
            "homepage": REPO_URL,
            "repository": REPO_URL,
            "license": LICENSE,
        }],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _targets(reg):
    return {
        "plugin.json": render_plugin_json(reg),
        "marketplace.json": render_marketplace_json(reg),
    }


def write_all(repo_root):
    """按真源重新生成两份 JSON；返回被写文件的相对路径列表（内容未变的也写，
    便于"顺手跑一次"的幂等语义——返回值只用于日志）。"""
    reg = load_registry(repo_root)
    problems = validate_registry(reg)
    if problems:
        raise SystemExit("真源有问题，拒绝生成：\n  - " + "\n  - ".join(problems))

    written = []
    for name, text in sorted(_targets(reg).items()):
        path = os.path.join(repo_root, PLUGIN_DIR, name)
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written.append("%s/%s" % (PLUGIN_DIR, name))
    return written


def check_all(repo_root):
    """生成物与真源是否漂移——返回问题列表（空 = 绿，CI 用）。"""
    try:
        reg = load_registry(repo_root)
    except (OSError, ValueError, KeyError) as exc:
        return ["读真源失败（%s）——插件清单位置或版本真值源坏了吗？" % exc]

    problems = list(validate_registry(reg))
    for name, expected in sorted(_targets(reg).items()):
        path = os.path.join(repo_root, PLUGIN_DIR, name)
        try:
            with io.open(path, "r", encoding="utf-8", newline="") as handle:
                actual = handle.read()
        except OSError as exc:
            problems.append("%s/%s 读不出来：%s" % (PLUGIN_DIR, name, exc))
            continue
        if actual != expected:
            problems.append(
                "%s/%s 与真源漂移——清单由 tools/assets_registry.py 生成，"
                "手改会被覆盖：跑 `python tools/assets_registry.py --write` 重新生成"
                % (PLUGIN_DIR, name))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="assets_registry",
        description="插件资产清单的唯一真源：--write 生成 / --check 比对漂移")
    parser.add_argument("--root", default=ROOT, help="仓库根（默认自动定位）")
    parser.add_argument("--write", action="store_true", help="按真源重新生成两份 JSON")
    parser.add_argument("--check", action="store_true", help="比对生成物与真源（CI 用）")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.write:
        for rel in write_all(args.root):
            print("已生成 %s" % rel)
        return 0

    problems = check_all(args.root)
    if not problems:
        print("assets-registry: OK（清单与真源一致）")
        return 0
    print("assets-registry: FAIL（%d 项）" % len(problems))
    for item in problems:
        print("  - %s" % item)
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
