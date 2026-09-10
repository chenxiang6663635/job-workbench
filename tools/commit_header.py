# -*- coding: utf-8 -*-
"""提交信息 header 的唯一校验实现（本地钩子与 CI 共用）。

单一真值源：`.githooks/commit_msg.py`（校验本地提交信息）与
`tools/check_pr_title.py`（校验 PR 标题）都调用这里，不各写一份正则与 type
枚举——两份实现迟早分叉，而分叉掉的那一半正好就是没拦住的那一半。

**为什么 PR 标题也要管**：squash 合并会把 PR 标题**直接变成主干上的提交
subject**。只约定提交信息、不管 PR 标题，就会出现「作者本地提交是中文、
合并进主干却变成英文」的混排。实证：2026-09-10 发现 `53e7b04` / `b774cce`
两条英文 subject 夹在中文提交之间，它们不是本地 `git commit` 产生的，
而是 GitHub 用 PR 标题现场生成的——本地钩子结构上看不到 PR 标题，
所以必须由 CI 补这一刀。

**语言规则是「必须」而不是「允许」**：CONTRIBUTING 提交规范写的是
「提交 subject 与 PR 标题一律中文」。原钩子只写「subject 允许中文」，
那是许可不是要求，于是英文一样通过——许可式规则等于没有规则。

纯 ASCII 的技术型 subject（如 `chore: bump electron to 31.0.0`）会被拦下，
这是有意的：按规则应写成 `chore: 升级 electron 到 31.0.0`。
"""

from __future__ import annotations

import re

TYPES = {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build",
         "ci", "chore", "revert", "data", "job"}

# `!` 后缀 = 破坏性变更（CONTRIBUTING 提交规范要求支持 feat!/fix(x)!）
HEADER_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9][a-z0-9_/-]*)\))?(?P<bang>!)?: (?P<subject>\S.*)$"
)

# 中日韩统一表意文字 + 扩展A + 兼容表意文字。只认汉字，不把全角标点算作中文
# ——「feat: 修复 bug。（只有标点是全角）」这种半英文不该混过去。
#
# 已知边界：汉字区与**日文汉字**共享同一段码位，逐字无法区分（「設定」既是日文
# 也是中文）。所以用假名/谚文做排除：日文句子几乎必含假名、韩文必含谚文，而中文
# 技术文案里出现假名或谚文的概率极低。残余缺口是「纯汉字书写的日文」（如
# 「設定変更」）会被放行——这一点无法可靠区分，只能接受并写在文档里。
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_HANGUL_PATTERN = re.compile(r"[\u3040-\u30ff\uac00-\ud7af]")

MAX_HEADER_LEN = 100

# git 自动生成或工具生成的 header，不适用人工规范
EXEMPT_PREFIXES = ("Merge ", "Revert ", "Initial commit", "fixup!", "Squashed commit")

# 校验来源：两者共用同一套格式/长度规则，但豁免范围不同。
# 提交信息可能由 git 自己生成（Merge/Revert/fixup），PR 标题永远是人工写的
# ——所以标题不该享受豁免，否则把标题写成「Merge xxx」就能整条绕过语言闸。
SOURCE_COMMIT = "commit"
SOURCE_PR_TITLE = "pr_title"


def is_exempt(message: str, source: str = SOURCE_COMMIT) -> bool:
    if source == SOURCE_PR_TITLE:
        return False
    return message.startswith(EXEMPT_PREFIXES)


def validate(message: str, source: str = SOURCE_COMMIT) -> list:
    """校验一条 header（提交 subject 或 PR 标题）。

    返回人类可读的问题列表，空列表表示通过。调用方负责加自己的前缀与退出码，
    这样本地钩子与 CI 能用同一套判定、各自输出。

    **一次返回全部问题**，不是发现第一个就返回：一条英文超长标题同时违反语言
    与长度两条规则，只报一条会让人改完再撞一次（真实案例：PR #16 的标题两条
    都违反）。格式错了才提前返回——那时候 type/subject 都没解析出来，后续检查
    没有意义。
    """
    if not message or not message.strip():
        return ["提交信息为空"]

    message = message.strip()
    if is_exempt(message, source):
        return []

    match = HEADER_PATTERN.match(message)
    if not match:
        return ["header 必须形如 'type(scope): subject'，当前：%s\n"
                "  type 可用：%s" % (message, ", ".join(sorted(TYPES)))]

    problems = []
    if match.group("type") not in TYPES:
        problems.append("未知 type '%s'，可用：%s"
                        % (match.group("type"), ", ".join(sorted(TYPES))))
    if len(message) > MAX_HEADER_LEN:
        problems.append("header 超过 %d 字符（当前 %d），把细节移到正文"
                        % (MAX_HEADER_LEN, len(message)))

    subject = match.group("subject")
    # 先判假名/谚文，再判「有没有汉字」：顺序反了的话，纯谚文的韩文会被报成
    # 「必须含中文」——结论没错但没指出真正的原因，人会一脸问号。
    if KANA_HANGUL_PATTERN.search(subject):
        problems.append("subject 含假名或谚文，看起来不是中文\n"
                        "  当前 subject：%s" % subject)
    elif not CJK_PATTERN.search(subject):
        problems.append("subject 必须含中文（本仓库提交信息与 PR 标题一律中文）\n"
                        "  当前 subject：%s\n"
                        "  改写示例：%s" % (subject, _suggest(match)))
    return problems


def _suggest(match) -> str:
    """给一条纯英文 subject 一个可直接照抄的中文骨架（保留原有的 type/scope）。"""
    prefix = match.group("type")
    if match.group("scope"):
        prefix += "(%s)" % match.group("scope")
    if match.group("bang"):
        prefix += "!"
    return "%s: <用中文说明改了什么>" % prefix
