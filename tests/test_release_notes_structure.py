# -*- coding: utf-8 -*-
"""structure_notes 行为测试：下载引导置顶 / 技术细节折叠 / 其余小节原样。

直测纯函数（不依赖仓库当前版本与 CHANGELOG 状态——subprocess 端到端会在
「bump 后、落章前」的窗口里因段缺失而误报，不适合做回归网）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import release_notes_format  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _expected_asset(version):
    """从 package.json 的 build.artifactName 派生产物名——一处断言钉住四方
    （package.json / release.yml 构建校验 / _ASSET_NAME / 本测试），改名漂移即红。"""
    with open(os.path.join(_REPO_ROOT, "web", "electron", "package.json"),
              encoding="utf-8-sig") as fh:
        name = json.load(fh)["build"]["artifactName"]
    return name.replace("${version}", version).replace("${ext}", "exe")


SAMPLE = "\n".join([
    "## [26.9.0] - 2026-09-25",
    "",
    "### Highlights (English)",
    "",
    "- highlight line",
    "",
    "### 看得见的变化",
    "",
    "- 一条看得见的变化",
    "",
    "### 技术细节",
    "",
    "#### Infrastructure",
    "",
    "- 内部工程条目",
])


def test_download_block_right_after_head():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    lines = out.splitlines()
    assert lines[0] == "## [26.9.0] - 2026-09-25"
    assert "## 下载（Windows 安装包）" in lines[1:6]
    assert _expected_asset("26.9.0") in out


def test_tech_details_folded():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    assert "<details>" in out and "</details>" in out
    assert out.index("### 技术细节") > out.index("<details>")
    assert out.index("#### Infrastructure") < out.index("</details>")
    assert out.index("### 看得见的变化") < out.index("<details>")


def test_sections_kept_verbatim():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    assert "### Highlights (English)" in out
    assert "- 一条看得见的变化" in out


def test_no_tech_details_is_noop():
    minimal = "\n".join(["## [26.9.1] - 2026-09-27", "", "### 看得见的变化", "", "- 小改动"])
    out = release_notes_format.structure_notes(minimal, "26.9.1")
    assert "<details>" not in out


def test_fold_closes_before_next_section():
    # 防御分支（审查 MINOR 2）：技术细节之后若再加同级 ### 小节，details 必须先闭合
    sample2 = "\n".join([
        "## [26.9.1] - 2026-09-27",
        "",
        "### 技术细节",
        "",
        "#### Infrastructure",
        "",
        "- 内部条目",
        "",
        "### 追加小节",
        "",
        "- 追加内容",
    ])
    out = release_notes_format.structure_notes(sample2, "26.9.1")
    assert out.index("</details>") < out.index("### 追加小节")
    assert "- 追加内容" in out
