# -*- coding: utf-8 -*-
"""反编造护栏：改写建议的提示词条款 + 本地校验器。

设计立场：AI 只允许「改写既有事实的表述」，绝不允许「新增事实」。
条款由 tests/test_prompt_guardrails.py 锁死——删句即测试失败，
把诚实红线从文档约定变成可执行的工程约束。

校验器五项：空改动 / section 漂移 / 身份字段被改 / 字数爆炸 / 新增数字。
未通过的建议绝不静默接受——前端必须标红并要求用户显式确认。
"""

from __future__ import annotations

import re

# 反编造条款。改这段文字 = 改产品伦理，tests/test_prompt_guardrails.py 会拦。
GUARDRAIL_CLAUSE = (
    "【诚实红线（最高优先级，违反即整份建议作废）】\n"
    "你只能改写简历中已有事实的表述方式，不得编造、虚构或暗示任何新事实。\n"
    "具体禁止：\n"
    "1. 不得新增原文没有的数字、百分比、金额、规模、人数、时长；\n"
    "2. 不得添加原文没有的项目、经历、技能或成果；\n"
    "3. 不得改动姓名、电话、邮箱、地点等身份信息；\n"
    "4. 不得增删段落或条目（只允许在既有条目内改措辞）；\n"
    "5. 每一处改写都必须经得起面试五到十分钟的追问——\n"
    "   写出来的每个动词都意味着你真的做过。\n"
    "如果 JD 要求某能力而简历没有，正确做法是不写，而不是编。"
)

# 身份字段：模型碰都不许碰
IDENTITY_FIELDS = ("name", "phone", "email", "location")

# 结构性 section：条目数不允许变化
SECTION_KEYS = ("education", "projects", "work", "skills", "extras")

# 单段文字长度上限：超出视为塞了新内容
LENGTH_RATIO = 1.5
LENGTH_MIN_DELTA = 30

# 数字 token：用于「新增数字」检测（阿拉伯数字串、百分比）
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def build_rewrite_prompt(data, instruction):
    """生成改写建议的提示词。条款强制拼入，位置在最前（优先级最高）。"""
    import json

    return (
        GUARDRAIL_CLAUSE
        + "\n\n---\n\n以下是当前简历数据（JSON）与用户的改写方向。\n"
        + "只输出修改后的完整 JSON，结构必须与输入完全一致，不要输出任何解释。\n\n"
        + "【用户改写方向】" + (instruction or "").strip() + "\n\n"
        + "【当前简历数据】\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )


def _numbers(text):
    """提取数字 token 集合（含小数与百分号）。"""
    return NUMBER_RE.findall(text or "")


def _walk(orig, sugg, path, issues):
    """递归对比：结构必须一致，叶子字符串做内容检测。"""
    if isinstance(orig, dict):
        if not isinstance(sugg, dict):
            issues.append("结构被破坏：%s（应为对象）" % _path(path))
            return
        for key in orig:
            if key not in sugg:
                issues.append("结构漂移：%s 的「%s」被删除" % (_path(path), key))
            else:
                _walk(orig[key], sugg[key], path + [key], issues)
        for key in sugg:
            if key not in orig:
                issues.append("结构漂移：%s 下新增了「%s」" % (_path(path), key))
        return

    if isinstance(orig, list):
        if not isinstance(sugg, list) or len(orig) != len(sugg):
            issues.append("结构漂移：%s 条目数发生变化（%s → %s）"
                          % (_path(path), len(orig),
                             len(sugg) if isinstance(sugg, list) else "非列表"))
            return
        for i, (o, s) in enumerate(zip(orig, sugg)):
            _walk(o, s, path + [i], issues)
        return

    if isinstance(orig, str):
        if not isinstance(sugg, str):
            issues.append("类型变化：%s（文本被替换为非文本）" % _path(path))
            return
        leaf_path = _path(path)

        # 数字检测：建议里的数字集合必须 ⊆ 原文的数字集合（多重集合）
        orig_nums, sugg_nums = _numbers(orig), _numbers(sugg)
        remaining = list(orig_nums)
        for n in sugg_nums:
            if n in remaining:
                remaining.remove(n)
            else:
                issues.append("新增数字：%s 出现了原文没有的数字「%s」——"
                              "这大概率是编造数据" % (leaf_path, n))
                return

        # 字数爆炸：单段暴增说明塞了新内容（小字符串放宽，避免误报）
        if len(sugg) > len(orig) * LENGTH_RATIO and \
                len(sugg) - len(orig) > LENGTH_MIN_DELTA:
            issues.append("字数爆炸：%s 从 %d 字涨到 %d 字，"
                          "疑似塞入了原文没有的内容"
                          % (leaf_path, len(orig), len(sugg)))


def _path(path):
    """['projects', 0, 'points', 1] → projects[0].points[1]"""
    out = ""
    for p in path:
        out = out + ("[%s]" % p if isinstance(p, int) else
                     ("." if out else "") + str(p))
    return out or "（根）"


def validate_rewrite(original, suggested):
    """校验改写建议。返回 (ok, issues)。

    五项检查全过才算安全；issues 非空时前端必须标红，
    要求用户显式确认后才能落盘，绝不静默接受。
    """
    issues = []

    # 1. 空改动
    if suggested == original:
        return False, ["没有产生任何改动——建议与原文完全一致"]

    # 2+4+5. 结构漂移 / 字数爆炸 / 新增数字（递归对比）
    _walk(original, suggested, [], issues)

    # 3. 身份字段：单独拦截，路径语义更明确
    orig_basics = original.get("basics") or {}
    sugg_basics = (suggested.get("basics") or {}) if \
        isinstance(suggested, dict) else {}
    for field in IDENTITY_FIELDS:
        if orig_basics.get(field) != sugg_basics.get(field):
            issues.append("身份字段被改：%s 不允许任何改动" % field)

    return (not issues), issues
