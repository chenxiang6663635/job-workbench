# -*- coding: utf-8 -*-
"""简历版式与强调色（批 4.5）：模板契约、加载白名单、风格注入与端到端 PDF。

钉住的核心口径（每条都对应一个真实会出事的场景）：

1. **占位符契约**——每套版式必须包含全部占位符；少一个，对应区块会被
   render_block 的兜底清成空——渲染"成功"，用户拿到却是一份少了一段
   的 PDF，不报任何错；
2. **版式名白名单**——`--template` 不接受路径字符（../、反斜杠、盘符），
   否则模板目录会被用来读任意文件；
3. **强调色纪律**——预设名与 #hex 之外的值必须显式报错，不许静默回落
   默认色（用户以为换了风格、实际没换）；
4. **端到端**——每套版式都过 Chrome 打印 → A4 → 一页 → 文本层三项
   （本机无 Chrome 时整组跳过，CI 不因此变红）。
"""

import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import resume_build  # noqa: E402

# 占位符契约清单（与 render_block 的替换表一一对应）。
REQUIRED_PLACEHOLDERS = [
    "{{basics.name}}", "{{basics.phone}}", "{{contact_sep}}", "{{basics.email}}",
    "{{contact_sep2}}", "{{basics.location}}", "{{intent_block}}",
    "{{profile_block}}", "{{education_block}}", "{{projects_block}}",
    "{{work_block}}", "{{skills_block}}", "{{extras_block}}",
]

DEMO_JSON = os.path.join(ROOT, "template", "demo", "02_简历工坊", "source",
                         "resume_backend.json")


def _load_demo_data():
    import json
    with io.open(DEMO_JSON, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ---- 模板契约与加载 -----------------------------------------------------------

def test_every_template_keeps_the_contract():
    templates = resume_build.list_templates()
    assert "std_resume" in templates, "默认版式 std_resume 必须在"
    assert len(templates) >= 3, "首批至少三套版式（经典 / 紧凑 / 强调）"
    for tid in templates:
        html = resume_build.load_template(tid)
        for ph in REQUIRED_PLACEHOLDERS:
            assert ph in html, "%s 缺占位符 %s" % (tid, ph)
        assert "@page" in html and "size: A4" in html, "%s 缺 A4 声明" % tid
        assert "--resume-accent" in html, "%s 缺强调色变量" % tid


def test_default_template_loads_without_arg():
    assert resume_build.load_template() == resume_build.load_template("std_resume")


def test_unknown_template_lists_available():
    with pytest.raises(ValueError) as err:
        resume_build.load_template("no_such_layout")
    assert "可用版式" in str(err.value)


@pytest.mark.parametrize("bad", ["../etc", "a/b", "x y", "..\\win", "d:evil"])
def test_template_name_whitelist(bad):
    with pytest.raises(ValueError):
        resume_build.load_template(bad)


# ---- 强调色（风格轴） ---------------------------------------------------------

def test_accent_presets_and_hex():
    assert resume_build.resolve_accent("石墨灰") == "#3f4650"
    assert resume_build.resolve_accent("#123abc") == "#123abc"
    assert resume_build.resolve_accent("") is None
    assert resume_build.resolve_accent("不是颜色") is None


def test_apply_accent_replaces_the_single_variable():
    html = resume_build.load_template("std_resume")
    out = resume_build.apply_accent(html, "#7a2e3a")
    assert "--resume-accent: #7a2e3a;" in out
    assert "#2c5f8d" not in out, "默认色必须被整体替换（风格只有一个入口）"
    assert resume_build.apply_accent(html, None) == html, "None 表示不覆盖"


def test_render_block_leaves_no_placeholder():
    data = _load_demo_data()
    for tid in resume_build.list_templates():
        html = resume_build.render_block(resume_build.load_template(tid), data)
        assert "{{" not in html, "%s 渲染后仍有残留占位符" % tid
        assert data["basics"]["name"] in html


# ---- 端到端：每套版式出一份 ATS 安全的 PDF ------------------------------------

@pytest.fixture(scope="module")
def browser():
    path = resume_build.find_browser()
    if not path:
        pytest.skip("未找到 Chrome / Edge，跳过 PDF 端到端")
    return path


def test_every_template_builds_ats_safe_pdf(tmp_path, browser):
    data = _load_demo_data()
    for tid in resume_build.list_templates():
        html = resume_build.render_block(resume_build.load_template(tid), data)
        tmp_html = os.path.join(str(tmp_path), "%s.html" % tid)
        with io.open(tmp_html, "w", encoding="utf-8") as f:
            f.write(html)
        pdf = os.path.join(str(tmp_path), "%s.pdf" % tid)
        assert resume_build.build_pdf(browser, tmp_html, pdf), "%s PDF 未生成" % tid
        ok, msg = resume_build.check_a4_mediabox(pdf)
        assert ok, "%s 非 A4：%s" % (tid, msg)
        passed, details = resume_build.verify_pdf(pdf)
        assert passed, "%s ATS 校验失败：%s" % (tid, details)
