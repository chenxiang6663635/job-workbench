# -*- coding: utf-8 -*-
"""英文对照文档的接线与对齐（2026-10-12「双语文档」批）。

四对文件（中文原版 ↔ 英文对照版）在仓库里成对存在：

    docs/glossary.md             ↔ docs/glossary.en-US.md
    docs/README.md               ↔ docs/README.en-US.md
    template/AGENTS.example.md   ↔ template/AGENTS.example.en-US.md
    template/workspace/README.md ↔ template/workspace/README.en-US.md

本测试钉三件事（只读检查，不改文件）：

1. 术语表两版的词条列**逐条同序**——补了中文忘英文、或顺序漂移即红；
2. 每对文件互指对方文件名——删掉对照版、或断掉互链即红；
3. 英文 README 的三个「英文读者入口」（三层词典示例 / Doc index / Glossary）
   指向英文版，不回退到全中文文档。

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


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return handle.read()


def _terms(text):
    terms = []
    for line in text.splitlines():
        match = TERM_RE.match(line)
        if match:
            terms.append(match.group("term").strip())
    return terms


def test_glossary_terms_match_in_order():
    zh = _terms(_read("docs/glossary.md"))
    en = _terms(_read("docs/glossary.en-US.md"))
    assert zh, "中文术语表一条词条都没解析到，多半是表格格式变了"
    assert en == zh, (
        "英文对照版与中文版的词条不同序/不同集：中文 %d 条、英文 %d 条；"
        "首个差异：%s" % (len(zh), len(en), next(
            (("%r != %r" % (a, b)) for a, b in zip(zh, en) if a != b), "（前缀相同，条数不同）"))
    )


@pytest.mark.parametrize("zh_rel,en_rel", PAIRS)
def test_companions_reference_each_other(zh_rel, en_rel):
    zh_name = os.path.basename(zh_rel)
    en_name = os.path.basename(en_rel)
    assert en_name in _read(zh_rel), "%s 未指回英文对照版 %s" % (zh_rel, en_name)
    assert zh_name in _read(en_rel), "%s 未指回中文原版 %s" % (en_rel, zh_name)


def test_english_readme_points_at_english_docs():
    readme = _read("README.md")
    for target in ("docs/README.en-US.md",
                   "docs/glossary.en-US.md",
                   "template/AGENTS.example.en-US.md"):
        assert target in readme, "英文 README 的对应入口未指向 %s" % target
