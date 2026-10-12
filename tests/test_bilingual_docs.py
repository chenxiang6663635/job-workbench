# -*- coding: utf-8 -*-
"""英文对照文档的接线与对齐（2026-10-12「双语文档」批）。

四对文件（中文原版 ↔ 英文对照版）在仓库里成对存在：

    docs/glossary.md             ↔ docs/glossary.en-US.md
    docs/README.md               ↔ docs/README.en-US.md
    template/AGENTS.example.md   ↔ template/AGENTS.example.en-US.md
    template/workspace/README.md ↔ template/workspace/README.en-US.md

本测试钉三件事（只读检查，不改文件）：

1. 术语表两版的词条列**逐条同序**（含加粗内空白——补了中文忘英文、格式漂移即红）；
2. 每对文件**在带标记的行上**互指对方文件名（标记：英文侧「英文对照版」、
   中文原版侧「中文原版 / 简体中文版」）——只查裸子串会在第 4 对产生假阳
   （`README.md` 字样本就在文件里大量出现），故要求同一行带互指标记；
3. 英文 README 的三个「英文读者入口」指向英文版，且**不再链接**三份中文目标
   （防止入口被改回去，2026-10-12 独立审查 M1/M5 的对应网）。

为什么要有它：对照版是「不跑代码、没有编译器」的那类资产，漂移是静默的——
正是 usage-guide en/zh 靠人工同步的地方。
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAIRS = [
    ("docs/glossary.md", "docs/glossary.en-US.md"),
    ("docs/README.md", "docs/README.en-US.md"),
    ("template/AGENTS.example.md", "template/AGENTS.example.en-US.md"),
    ("template/workspace/README.md", "template/workspace/README.en-US.md"),
]

# 术语表的数据行：首列是加粗词条 `| **术语** | ...`
TERM_RE = re.compile(r"^\|\s*\*\*(?P<term>[^*]+)\*\*\s*\|")

# 互指标记：中文原版指英文版用「英文对照版」；英文对照版指中文原版用「中文原版 / 简体中文版」
ZH_SIDE_MARKERS = ("英文对照版",)
EN_SIDE_MARKERS = ("中文原版", "简体中文版")

EN_READER_ENTRIES = (
    "docs/README.en-US.md",
    "docs/glossary.en-US.md",
    "template/AGENTS.example.en-US.md",
)
ZH_LINK_TARGETS_FORBIDDEN_IN_EN_README = (
    "](docs/README.md)",
    "](docs/glossary.md)",
    "](template/AGENTS.example.md)",
)


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return handle.read()


def _terms(text):
    terms = []
    for line in text.splitlines():
        match = TERM_RE.match(line)
        if match:
            # 不 strip：加粗内首尾空白漂移（`** x **`）也要红
            terms.append(match.group("term"))
    return terms


def _has_marked_line(text, markers, name):
    """存在一行同时包含互指标记与对方文件名。"""
    return any(
        name in line and any(marker in line for marker in markers)
        for line in text.splitlines()
    )


def test_glossary_terms_match_in_order():
    zh = _terms(_read("docs/glossary.md"))
    en = _terms(_read("docs/glossary.en-US.md"))
    assert zh, "中文术语表一条词条都没解析到，多半是表格格式变了"
    assert en == zh, (
        "英文对照版与中文版的词条不同序/不同集：中文 %d 条、英文 %d 条；"
        "首个差异：%s" % (len(zh), len(en), next(
            (("%r != %r" % (a, b)) for a, b in zip(zh, en) if a != b),
            "（前缀相同，条数不同）"))
    )


@pytest.mark.parametrize("zh_rel,en_rel", PAIRS)
def test_companions_reference_each_other(zh_rel, en_rel):
    zh_name = os.path.basename(zh_rel)
    en_name = os.path.basename(en_rel)
    assert _has_marked_line(_read(zh_rel), ZH_SIDE_MARKERS, en_name), (
        "%s 没有一行同时含「英文对照版」与 %s" % (zh_rel, en_name))
    assert _has_marked_line(_read(en_rel), EN_SIDE_MARKERS, zh_name), (
        "%s 没有一行同时含「中文原版 / 简体中文版」与 %s" % (en_rel, zh_name))


def test_english_readme_points_at_english_docs():
    readme = _read("README.md")
    for target in EN_READER_ENTRIES:
        assert target in readme, "英文 README 的对应入口未指向 %s" % target
    for target in ZH_LINK_TARGETS_FORBIDDEN_IN_EN_README:
        assert target not in readme, (
            "英文 README 又链接了中文文档 %s——英文读者入口不应回退"
            "（改指英文版；确要提中文原件时用纯文本指名并说明）" % target)
