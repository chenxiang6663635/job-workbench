# -*- coding: utf-8 -*-
"""structure_notes 行为测试：直链首行 / 去版本大标题 / 双折叠区 / 其余小节原样。

直测纯函数（不依赖仓库当前版本与 CHANGELOG 状态——subprocess 端到端会在
「bump 后、落章前」的窗口里因段缺失而误报，不适合做回归网）。

2026-10-06 随模块重构同步重写（11 个成熟项目调研后的模板：直链置顶、
不重复版本号大标题、English Highlights 折叠）。
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


def test_first_line_is_direct_download_link():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    first = out.splitlines()[0]
    asset = _expected_asset("26.9.0")
    assert asset in first
    # 直链 = 版本化 asset URL（发布后恒定），不是「去 Assets 区找」式指引
    assert ("releases/download/v26.9.0/" + asset) in first
    # 第二行 = 校验和直链
    assert "releases/download/v26.9.0/SHA256SUMS.txt" in out.splitlines()[1]


def test_version_title_not_repeated():
    # 页面标题已显示 tag——正文不再重复版本号大标题（11/11 项目均不重复）
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    assert "## [26.9.0] - 2026-09-25" not in out


def test_english_highlights_folded_chinese_visible():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    assert "<summary><b>English Highlights</b></summary>" in out
    assert out.index("### Highlights (English)") > out.index("<details>")
    # 中文「看得见的变化」是可见主体：在第一个 </details> 之后、不在折叠区内
    assert out.index("### 看得见的变化") > out.index("</details>")
    assert "- 一条看得见的变化" in out


def test_tech_details_folded():
    out = release_notes_format.structure_notes(SAMPLE, "26.9.0")
    assert out.count("<details>") == 2  # English Highlights + 技术细节 各一
    assert out.index("### 技术细节") > out.index("</details>")
    assert out.index("#### Infrastructure") < out.rindex("</details>")


def test_h2_sections_demoted_to_h3():
    # 正文只允许一层小节标题：段内 `##`（非段头）一律降为 `###`
    sample2 = "\n".join([
        "## [26.9.1] - 2026-09-27",
        "",
        "### 看得见的变化",
        "",
        "- 小改动",
        "",
        "## 安装说明",
        "",
        "- 未签名提示",
    ])
    out = release_notes_format.structure_notes(sample2, "26.9.1")
    assert "### 安装说明" in out
    assert "\n## 安装说明" not in out
    assert "## [26.9.1]" not in out


def test_no_fold_sections_is_noop_for_details():
    minimal = "\n".join([
        "## [26.9.1] - 2026-09-27",
        "",
        "### 看得见的变化",
        "",
        "- 小改动",
    ])
    out = release_notes_format.structure_notes(minimal, "26.9.1")
    assert "<details>" not in out
    assert "- 小改动" in out


def test_fold_closes_before_next_section():
    # 防御分支（审查 MINOR 2 同源）：折叠区之后若再加同级 ### 小节，details 必须先闭合
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


def test_two_folds_in_a_row_close_independently():
    # Highlights (English) 之后紧跟技术细节：各自成区、互不嵌套
    sample2 = "\n".join([
        "## [26.9.1] - 2026-09-27",
        "",
        "### Highlights (English)",
        "",
        "- highlight",
        "",
        "### 技术细节",
        "",
        "- 内部条目",
    ])
    out = release_notes_format.structure_notes(sample2, "26.9.1")
    assert out.count("<details>") == 2 and out.count("</details>") == 2
    assert out.index("### 技术细节") > out.index("</details>")
