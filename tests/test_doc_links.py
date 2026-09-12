# -*- coding: utf-8 -*-
"""文档相对链接可达（B4 / #4）。

文档里的相对链接是「改了文件名就会静默断掉」的那类东西——本地点不开没人报，
发布出去才被第一个读者撞见。这里把根目录与 `docs/` 下的 Markdown 全扫一遍。

只管相对链接：外链的可达性取决于网络与对方站点，不该进这套秒级回归。
"""

import os
import re

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 相对链接（含图片），允许后面跟一个可选的 title
LINK_RE = re.compile(r"!?\[[^\]]*\]\(<?([^()<>\s]+)>?(?:\s+\"[^\"]*\")?\)")

# 外部 / 非文件类目标，一律跳过
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "#")

# 不扫的目录：生成物、依赖、私有数据、技能分发副本
SKIP_DIRS = {".git", "node_modules", "dist", "release", "personal",
             "template", ".codebuddy", ".agents", ".claude", ".codex",
             "__pycache__", "snapshots"}


# 根目录这几类前缀是本地草稿 / 临时产出区（见 .gitignore），不入库、也不该被扫描——
# 否则这套断言在本机与 CI 上会扫出不同的结果。
LOCAL_DRAFT_PREFIXES = ("research_", "tmp_", "plan_", "report_")


def _markdown_files():
    """根目录的 md + docs/ 下的 md（递归）。"""
    found = []
    for name in sorted(os.listdir(ROOT_DIR)):
        path = os.path.join(ROOT_DIR, name)
        if (name.endswith(".md") and os.path.isfile(path)
                and not name.startswith(LOCAL_DRAFT_PREFIXES)):
            found.append(path)
    docs = os.path.join(ROOT_DIR, "docs")
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if name.endswith(".md"):
                found.append(os.path.join(dirpath, name))
    return found


def _links(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    for target in LINK_RE.findall(text):
        if target.startswith(SKIP_PREFIXES):
            continue
        # 锚点与查询串不参与文件可达性
        target = target.split("#")[0].split("?")[0]
        if target:
            yield target


def test_all_relative_links_resolve():
    broken = []
    checked = 0
    for md in _markdown_files():
        base = os.path.dirname(md)
        for target in _links(md):
            checked += 1
            resolved = os.path.normpath(os.path.join(base, target))
            if not (os.path.isfile(resolved) or os.path.isdir(resolved)):
                broken.append("%s -> %s" % (os.path.relpath(md, ROOT_DIR), target))
    assert broken == [], "以下文档相对链接指向了不存在的目标：\n" + "\n".join(broken)
    assert checked > 0, "一个链接都没扫到，多半是正则或扫描范围坏了"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[使用指南](docs/usage-guide.md)", ["docs/usage-guide.md"]),
        ("![预览](docs/screenshots/01-dashboard.png)", ["docs/screenshots/01-dashboard.png"]),
        ("[外链](https://example.com/x)", []),
        ("[同页锚点](#安装)", []),
        ('[带标题](docs/usage-guide.md "使用指南")', ["docs/usage-guide.md"]),
        ("[尖括号](<docs/usage-guide.md>)", ["docs/usage-guide.md"]),
    ],
)
def test_link_regex(tmp_path, raw, expected):
    """正则本身要有断言：它是最容易「看起来对、实际漏」的一环。"""
    path = tmp_path / "a.md"
    path.write_text(raw, encoding="utf-8")
    assert list(_links(str(path))) == expected
