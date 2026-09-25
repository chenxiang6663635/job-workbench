# -*- coding: utf-8 -*-
"""插件资产校验（批 8）：仓库根 commands/ 与 agents/ 的合规检查。

从 check_skills.py 拆出（那里是水位文件，只许变小；而「技能」与「插件资产」
本就是两件独立的校验职责，拆开各自表述更清楚）。

宿主按**目录约定**扫描仓库根的 commands/ 与 agents/（本机插件样例实证：manifest
不声明也会被扫到）；这里做最低限度校验，防「写坏了但没人发现」——它是唯一防线。
"""

from __future__ import annotations

import json
import os
import re

# frontmatter 解析器与技能校验共用（单行 key: value，不引 YAML 依赖）。
# 函数内引用而非模块级 import：check_skills 会在 main() 里 import 本模块，
# 模块级互相 import 会成环。
_ALLOWED_TOOLS_PATTERN = r"^[A-Za-z_][\w-]*(\(.+\))?$"


def _read_frontmatter(path):
    """读文件并解析 frontmatter；返回 (字段字典, 问题列表)。"""
    from check_skills import _parse_frontmatter

    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return None, ["读不出来：%s" % exc]
    fields, error, _end = _parse_frontmatter(text)
    if error:
        return None, [error]
    return fields, []


def _inspect_command(path, _label):
    fields, problems = _read_frontmatter(path)
    if fields is None:
        return problems
    if not fields.get("description"):
        problems.append("缺少 description：命令列表里会显示成文件名")
    allowed = fields.get("allowed-tools")
    for part in [p.strip() for p in (allowed or "").split(",") if p.strip()]:
        if not re.match(_ALLOWED_TOOLS_PATTERN, part):
            problems.append(
                "allowed-tools 片段不合规：%r（形如 Bash(git add:*)）" % part)
    return problems


def _inspect_agent(path, _label):
    fields, problems = _read_frontmatter(path)
    if fields is None:
        return problems
    for key in ("name", "description", "tools"):
        if not fields.get(key):
            problems.append("缺少 %s（子代理必需字段）" % key)
    mode = fields.get("agentMode")
    if mode and mode not in ("agentic", "readonly"):
        problems.append("agentMode 取值可疑：%r（本机样例为 agentic）" % mode)
    return problems


def inspect_plugin_assets(repo_root):
    """校验仓库根的 commands/ 与 agents/；返回 [(相对路径, [问题])]，只含有问题项。"""
    findings = []

    def _walk(sub, inspector):
        base = os.path.join(repo_root, sub)
        if not os.path.isdir(base):
            return
        for name in sorted(os.listdir(base)):
            if not name.endswith(".md"):
                continue
            label = "%s/%s" % (sub, name)
            problems = inspector(os.path.join(base, name), label)
            if problems:
                findings.append((label, problems))

    _walk("commands", _inspect_command)
    _walk("agents", _inspect_agent)
    return findings


# ---- 清单一致性（2026-09-25 发布前收口批）-------------------------------------
#
# 「技能清单」有三份手写副本：plugin.json 的 skills、marketplace.json 的
# plugins[0].skills、以及 skills/ 磁盘目录。jwb-domain-setup 加入时
# marketplace.json 漏改（8 vs 9）——当时没有任何校验能发现（独立审计）。
# 集合与数量都是**派生值**：下面的校验断言"写出来的清单与磁盘事实一致"。

# 描述里的技能数量形态（只认**阿拉伯数字**：写对只有一种写法，中文数字
# 「八个」这类不在校验面内——改文案时统一用阿拉伯数字）。
# 中文两种语序（「技能 9 个」「9 个技能」）+ 英文（「9 skills」）。
_SKILL_COUNT_RES = (
    re.compile(r"技能\s*(\d+)\s*个"),
    re.compile(r"(\d+)\s*个技能"),
    re.compile(r"(\d+)\s*skills?\b"),
)


def _skill_dirs(skills_root):
    """skills/ 下的实际技能目录名集合（jwb- 前缀 + 目录）。"""
    if not os.path.isdir(skills_root):
        return set()
    return {name for name in os.listdir(skills_root)
            if name.startswith("jwb-")
            and os.path.isdir(os.path.join(skills_root, name))}


def _listed_skill_names(items):
    """清单里的路径写法（`./skills/jwb-x` / `skills/jwb-x` / `jwb-x`）统一成目录名。"""
    return {os.path.basename(str(p).rstrip("/\\")) for p in (items or [])}


def _count_problems(label, description, expected):
    """描述里的数量（若有写明）必须等于集合大小。"""
    problems = []
    for pattern in _SKILL_COUNT_RES:
        for found in pattern.findall(description or ""):
            if int(found) != expected:
                problems.append(
                    "%s 的描述写着 %s（个）技能，skills/ 下实际 %d 个——"
                    "数量是派生值，加/删技能时描述要一起改"
                    % (label, found, expected))
    return problems


def manifest_consistency_problems(repo_root):
    """插件清单三处一致：plugin.json == marketplace.json == skills/ 实际目录。

    返回问题列表（空 = 通过）。读不出 JSON 直接算问题——校验器自身的失败同样
    要响亮（静默跳过会让"清单坏了"以绿灯形态存活）。
    """
    problems = []
    plugin_dir = os.path.join(repo_root, ".codebuddy-plugin")
    actual = _skill_dirs(os.path.join(repo_root, "skills"))

    def _load(name):
        try:
            with open(os.path.join(plugin_dir, name), "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError) as exc:
            problems.append("%s 读不出来：%s" % (name, exc))
            return None

    plugin = _load("plugin.json")
    market = _load("marketplace.json")
    if plugin is None or market is None:
        return problems

    plugin_skills = _listed_skill_names(plugin.get("skills"))
    if plugin_skills != actual:
        problems.append(
            "plugin.json 的技能集合与 skills/ 目录不一致：漏列 %s、多列 %s"
            % (sorted(actual - plugin_skills) or "无",
               sorted(plugin_skills - actual) or "无"))

    market_plugins = market.get("plugins") or []
    market_skills = _listed_skill_names(
        market_plugins[0].get("skills") if market_plugins else [])
    if market_skills != actual:
        problems.append(
            "marketplace.json 的技能集合与 skills/ 目录不一致：漏列 %s、多列 %s"
            % (sorted(actual - market_skills) or "无",
               sorted(market_skills - actual) or "无"))

    problems.extend(_count_problems(
        "plugin.json", plugin.get("description"), len(actual)))
    problems.extend(_count_problems(
        "marketplace.json", market.get("description"), len(actual)))
    if market_plugins:
        problems.extend(_count_problems(
            "marketplace.json（plugins[0]）", market_plugins[0].get("description"),
            len(actual)))
    return problems
