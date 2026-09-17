# -*- coding: utf-8 -*-
"""插件资产校验（批 8）：仓库根 commands/ 与 agents/ 的合规检查。

从 check_skills.py 拆出（那里是水位文件，只许变小；而「技能」与「插件资产」
本就是两件独立的校验职责，拆开各自表述更清楚）。

宿主按**目录约定**扫描仓库根的 commands/ 与 agents/（本机插件样例实证：manifest
不声明也会被扫到）；这里做最低限度校验，防「写坏了但没人发现」——它是唯一防线。
"""

from __future__ import annotations

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
