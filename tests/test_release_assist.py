# -*- coding: utf-8 -*-
"""release_assist 的回归护栏。

抽取规则曾以 pwsh 内联脚本存在于 release.yml（v0.2.2 发布演练时踩过
「$a[0..-1] 反向取值」的坑）。收敛进 Python 后，这里把边界固定下来——
尤其是「精确版本号」与「空段落」两条。
"""

import os
import sys

import pytest

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


def test_main_rejects_version_argument_mismatch(tmp_path, monkeypatch, capsys):
    """--version 与 package.json 不一致时不得放行——预检不能被一个参数绕过（M1）。"""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(release_assist, "CHANGELOG", str(changelog))
    real = release_assist.read_version()
    fake = "0.0.1" if real != "0.0.1" else "0.0.2"
    monkeypatch.setattr(sys, "argv",
                        ["release_assist", "--version", fake, "--tag", "v" + fake])
    assert release_assist.main() == 1
    assert "不一致" in capsys.readouterr().out


def test_main_missing_changelog_exits_two(tmp_path, monkeypatch, capsys):
    """文件缺失 → 退出码 2（模块 docstring 的契约；M3）。"""
    monkeypatch.setattr(release_assist, "CHANGELOG", str(tmp_path / "nope.md"))
    monkeypatch.setattr(sys, "argv", ["release_assist"])
    assert release_assist.main() == 2
    assert "找不到" in capsys.readouterr().out


def test_main_missing_package_json_exits_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_assist, "PACKAGE_JSON", str(tmp_path / "nope.json"))
    monkeypatch.setattr(sys, "argv", ["release_assist"])
    assert release_assist.main() == 2
    assert "找不到" in capsys.readouterr().out


def test_main_rejects_package_json_without_version(tmp_path, monkeypatch, capsys):
    """package.json 缺 version 键 → 退出码 2（读取/配置错误契约；第三轮 M）。"""
    bad = tmp_path / "package.json"
    bad.write_text('{"name": "x"}', encoding="utf-8")
    monkeypatch.setattr(release_assist, "PACKAGE_JSON", str(bad))
    monkeypatch.setattr(sys, "argv", ["release_assist"])
    assert release_assist.main() == 2
    assert "version" in capsys.readouterr().out


def test_main_changelog_read_failure_exits_two(monkeypatch, capsys):
    """CHANGELOG 读取失败（OSError）→ 退出码 2（第三轮 M 的异常面）。"""
    def _boom(*args, **kwargs):
        raise OSError("模拟读取失败")
    monkeypatch.setattr(release_assist, "check", _boom)
    monkeypatch.setattr(sys, "argv", ["release_assist"])
    assert release_assist.main() == 2
    assert "读取 CHANGELOG 失败" in capsys.readouterr().out


def test_check_raises_when_changelog_missing(tmp_path):
    """check 的库契约：路径不存在抛 FileNotFoundError（入口层映射 2；第三轮 M）。"""
    with pytest.raises(FileNotFoundError):
        release_assist.check("0.2.2", changelog_path=str(tmp_path / "nope.md"))
