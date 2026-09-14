# -*- coding: utf-8 -*-
"""release_assist 的回归护栏。

抽取规则曾以 pwsh 内联脚本存在于 release.yml（v0.2.2 发布演练时踩过
「$a[0..-1] 反向取值」的坑）。收敛进 Python 后，这里把边界固定下来——
尤其是「精确版本号」与「空段落」两条。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import release_assist  # noqa: E402

SAMPLE = """# Changelog

## [Unreleased]

### Added

- 未发布的东西。

## [0.3.0] - 2026-10-01

### Added

- 新功能 A。

### Fixed

- 修了 B。

## [0.2.2] - 2026-09-13

- 旧版本。
"""


def test_find_section_extracts_exact_range():
    notes = release_assist.find_section(SAMPLE, "0.3.0")
    assert notes.startswith("## [0.3.0]")
    assert "新功能 A" in notes and "修了 B" in notes
    assert "旧版本" not in notes          # 不吞下一段
    assert "未发布的东西" not in notes    # 不吞上一段
    assert not notes.endswith("\n")       # 尾部空行剥掉（调用方补一个换行）


def test_find_section_is_exact_version_only():
    """[0.3.0] 不能把 [0.3.0-beta] 当成同一段放行——beta 不是正式段。"""
    text = SAMPLE.replace("[0.3.0]", "[0.3.0-beta]")
    assert release_assist.find_section(text, "0.3.0") is None
    assert release_assist.find_section(text, "0.3.0-beta").startswith("## [0.3.0-beta]")


def test_find_section_missing_version_returns_none():
    assert release_assist.find_section(SAMPLE, "9.9.9") is None


def test_find_section_handles_empty_section():
    """空段落（段头与下一个段头之间只有空行）返回段头本身，不能变成反向切片。"""
    text = "## [1.0.0]\n\n## [0.9.0]\n\n- x\n"
    assert release_assist.find_section(text, "1.0.0") == "## [1.0.0]"


def test_check_reports_tag_mismatch(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    ok, lines, notes = release_assist.check(
        "0.3.0", tag="v0.2.2", changelog_path=str(changelog))
    assert not ok
    assert any("不一致" in line for line in lines)
    # 段本身存在：说明不一致是**单独**报的，而不是被段缺失掩盖
    assert notes is not None and notes.startswith("## [0.3.0]")


def test_check_reports_missing_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    ok, lines, notes = release_assist.check(
        "9.9.9", tag="v9.9.9", changelog_path=str(changelog))
    assert not ok
    assert notes is None
    assert any("没有 [9.9.9] 段" in line for line in lines)


def test_check_passes_with_released_version(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    ok, lines, notes = release_assist.check(
        "0.2.2", tag="v0.2.2", changelog_path=str(changelog))
    assert ok
    assert notes.startswith("## [0.2.2]")


def test_repo_changelog_smoke():
    """真仓库冒烟：已发布过的 0.2.2 段必须抽得出（防抽取规则漂移）。"""
    with open(release_assist.CHANGELOG, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    notes = release_assist.find_section(text, "0.2.2")
    assert notes is not None
    assert notes.startswith("## [0.2.2]")


def test_read_version_matches_package_json():
    """版本号唯一来源可达：read_version() 能读到合法 semver。"""
    version = release_assist.read_version()
    parts = version.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)
