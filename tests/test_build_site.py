# -*- coding: utf-8 -*-
"""build_site 行为测试：白名单复制（隐私边界）/ 模板注入 / 链接重写四规则。

用 tmp_path 假仓库直测纯函数与 assemble——docs/ 会持续变化，把断言钉在真实
文件上会让测试随内容漂移（与 test_release_notes_structure.py 同款取舍）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site", "scripts"))

import build_site  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """最小假仓库：白名单内外的文件各就位。"""
    root = tmp_path / "repo"
    (root / "web" / "electron").mkdir(parents=True)
    (root / "web" / "electron" / "package.json").write_text(
        '{"name": "fake", "version": "26.9.0"}', encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [26.9.0] - 2026-09-25\n",
        encoding="utf-8")

    docs = root / "docs"
    docs.mkdir()
    (docs / "usage-guide.zh-CN.md").write_text(
        "English: [usage-guide.md](usage-guide.md)\n"
        "索引: [README](README.md)\n"
        "截图: ![dashboard](screenshots/zh-CN/01-dashboard.png)\n"
        "隐私: [data-flow-matrix.md](data-flow-matrix.md)\n"
        "外链: [MkDocs](https://www.mkdocs.org/)\n"
        "锚点: [本页](#中文手册)\n", encoding="utf-8")
    (docs / "usage-guide.md").write_text(
        "简体中文: [usage-guide.zh-CN.md](usage-guide.zh-CN.md)\n", encoding="utf-8")
    (docs / "data-flow-matrix.md").write_text(
        "仓库根: [README](../README.md)\n", encoding="utf-8")
    (docs / "support-and-compatibility.md").write_text(
        "安全: [SECURITY.md](../SECURITY.md)\n", encoding="utf-8")
    (docs / "internal-secret.md").write_text("白名单外，不进产物", encoding="utf-8")
    for rel in ("screenshots/01-dashboard.png",
                "screenshots/zh-CN/01-dashboard.png",
                "screenshots/private/secret.png"):
        path = docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")

    content = root / "site" / "content"
    (content / "sub").mkdir(parents=True)
    (content / "index.tmpl.md").write_text(
        "# 站点\n\n版本 {{VERSION}}（{{RELEASE_DATE}}）\n", encoding="utf-8")
    (content / "download.tmpl.md").write_text("# 下载\n", encoding="utf-8")
    (content / "index.en.tmpl.md").write_text("# Site\n", encoding="utf-8")
    (content / "sub" / "page.tmpl.md").write_text("# 子页\n", encoding="utf-8")
    (content / "notes.md").write_text("不是模板，不进产物", encoding="utf-8")
    return root


def _tree(root):
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file())


def test_parse_version():
    assert build_site.parse_version('{"version": "26.9.0"}') == "26.9.0"


def test_parse_release_date_first_dated_section():
    text = "## [Unreleased]\n\n## [26.9.0] - 2026-09-25\n\n## [26.8.2] - 2026-08-30\n"
    assert build_site.parse_release_date(text) == "2026-09-25"


def test_parse_release_date_without_date_returns_empty():
    assert build_site.parse_release_date("# Changelog\n\n## [Unreleased]\n") == ""


def test_render_template_replaces_placeholders():
    out = build_site.render_template(
        "版本 {{VERSION}}（{{RELEASE_DATE}}）",
        version="26.9.0", release_date="2026-09-25")
    assert out == "版本 26.9.0（2026-09-25）"


def test_render_template_empty_date():
    out = build_site.render_template(
        "版本 {{VERSION}}，日期 {{RELEASE_DATE}}", version="26.9.0", release_date="")
    assert out == "版本 26.9.0，日期 "


def test_rewrite_links_rule1_whitelisted_doc():
    out = build_site.rewrite_links(
        "[英文版](usage-guide.md)", source="docs/usage-guide.zh-CN.md")
    assert out == "[英文版](guide.en.md)"


def test_rewrite_links_rule1_keeps_anchor():
    out = build_site.rewrite_links(
        "[隐私](data-flow-matrix.md#数据流)", source="docs/usage-guide.zh-CN.md")
    assert out == "[隐私](../privacy/index.md#数据流)"


def test_rewrite_links_rule2_repo_file_goes_to_github():
    out = build_site.rewrite_links(
        "[仓库根](../README.md)", source="docs/data-flow-matrix.md")
    assert out == ("[仓库根](https://github.com/chenxiang6663635/job-workbench"
                   "/blob/main/README.md)")


def test_rewrite_links_rule2_nested_doc_goes_to_github():
    out = build_site.rewrite_links(
        "[索引](README.md)", source="docs/usage-guide.zh-CN.md")
    assert out == ("[索引](https://github.com/chenxiang6663635/job-workbench"
                   "/blob/main/docs/README.md)")


def test_rewrite_links_rule3_screenshots():
    out = build_site.rewrite_links(
        "![仪表盘](screenshots/zh-CN/01-dashboard.png)",
        source="docs/usage-guide.zh-CN.md")
    assert out == "![仪表盘](../assets/screenshots/zh-CN/01-dashboard.png)"


def test_rewrite_links_rule4_external_anchor_and_other_untouched():
    text = "[外链](https://www.mkdocs.org/) [锚点](#章节) [文件](logo.png)"
    assert build_site.rewrite_links(text, source="docs/usage-guide.zh-CN.md") == text


def test_assemble_whitelist_only(repo, tmp_path):
    out = tmp_path / "out"
    build_site.assemble(repo, out)
    assert _tree(out) == [
        "assets/screenshots/01-dashboard.png",
        "assets/screenshots/zh-CN/01-dashboard.png",
        "compat/index.md",
        "download.md",
        "index.en.md",
        "index.md",
        "manual/guide.en.md",
        "manual/guide.md",
        "privacy/index.md",
        "sub/page.md",
    ]


def test_assemble_renders_template_placeholders(repo, tmp_path):
    out = tmp_path / "out"
    build_site.assemble(repo, out)
    index = (out / "index.md").read_text(encoding="utf-8")
    assert "26.9.0" in index and "2026-09-25" in index and "{{" not in index


def test_assemble_rewrites_doc_links(repo, tmp_path):
    out = tmp_path / "out"
    build_site.assemble(repo, out)
    guide = (out / "manual" / "guide.md").read_text(encoding="utf-8")
    assert "](guide.en.md)" in guide                       # 规则 1
    assert "blob/main/docs/README.md" in guide             # 规则 2
    assert "](../assets/screenshots/zh-CN/01-dashboard.png)" in guide   # 规则 3
    assert "](https://www.mkdocs.org/)" in guide           # 规则 4
    assert "](#中文手册)" in guide
    privacy = (out / "privacy" / "index.md").read_text(encoding="utf-8")
    assert "blob/main/README.md" in privacy                # 规则 2（../README.md）
    compat = (out / "compat" / "index.md").read_text(encoding="utf-8")
    assert "blob/main/SECURITY.md" in compat


def test_assemble_rebuilds_clean(repo, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.md").write_text("上次的残留", encoding="utf-8")
    build_site.assemble(repo, out)
    assert not (out / "stale.md").exists()


def test_assemble_refuses_repo_root_as_out(repo):
    with pytest.raises(ValueError):
        build_site.assemble(repo, repo)
