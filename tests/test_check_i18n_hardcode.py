# -*- coding: utf-8 -*-
"""界面硬编码中文检查（`tools/check_i18n_hardcode.py`）自身的钉子。

检查脚本本身就是「防回归的回归」——它错了的后果是两边的：太松则白装，
太严则 CI 恒红、被绕过。所以这里逐条钉住判定口径：

1. **注释不算命中**：中文注释是项目文档惯例（CONTRIBUTING 归资料类）；
2. **字符串里的 `//` 不是注释**：`"https://x"` 之后的内容必须继续被检查——
   用正则去注释会把这一行改成另一行代码，检查随即失真；
3. **语言包豁免**：`i18n/locales/` 是中文的家；
4. **JSX 表达式里的中文不算命中**（`{it.公司}` 是取数），裸文本才可能
   是"写死给用户看的字"；
5. **清单是片段级快照**：只放行登记过的片段，且 **jsx-text 一类永不放行**
   （否则 `<span>已挂</span>` 会借数据豁免溜过去）；
6. **僵尸条目报错**：清单里指向已无命中的文件、或列了却没出现的片段，都必须
   被指出，否则下一处真命中会悄悄获得豁免。
"""

import io
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import check_i18n_hardcode as checker  # noqa: E402

SRC = os.path.join("web", "frontend", "src")


def _make_repo(tmp_path, files, allowlist=""):
    """按 {相对 src 的路径: 内容} 造一个小源码树，可选写允许清单。"""
    for rel, text in files.items():
        full = tmp_path / SRC / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        io.open(str(full), "w", encoding="utf-8").write(text)
    if allowlist:
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        io.open(str(tools_dir / "i18n_hardcode_allowlist.txt"), "w",
                encoding="utf-8").write(allowlist)
    return str(tmp_path)


def _run(tmp_path, files, allowlist=""):
    root = _make_repo(tmp_path, files, allowlist)
    unallowed, ok, _plural, _missing, errors = checker.check(root)
    return unallowed, ok, errors


def _plural(tmp_path, files):
    """复数检查单独取（与硬编码检查共用同一个工具）。"""
    return checker.find_plural_without_count(_make_repo(tmp_path, files))


def _missing(tmp_path, files):
    return checker.find_missing_keys(_make_repo(tmp_path, files))


# ---- 1. 注释 ----

def test_line_comment_is_not_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.tsx": '// 这是一句中文注释\nconst x = 1;\n'})
    assert unallowed == []


def test_block_comment_is_not_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.tsx": "/*\n多行中文注释\n*/\nconst x = 1;\n"})
    assert unallowed == []


# ---- 2. 字符串里的 // ----

def test_slash_in_string_does_not_start_a_comment(tmp_path):
    """`"https://示例"` 里的中文必须照报：把 `//` 当注释会漏掉整行。"""
    unallowed, _, _ = _run(tmp_path, {"a.tsx": 'const url = "https://示例";\n'})
    assert [u[2] for u in unallowed] == ["https://示例"]


def test_code_after_a_string_is_still_scanned(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.tsx": 'const s = "x"; // 注释\nconst y = "中文";\n'})
    assert [u[2] for u in unallowed] == ["中文"]


# ---- 3. 语言包豁免 ----

def test_locale_files_are_exempt(tmp_path):
    unallowed, _, _ = _run(tmp_path, {os.path.join("i18n", "locales", "zh-CN.ts"):
                                      '"a.b": "中文文案",\n'})
    assert unallowed == []


# ---- 4. JSX 表达式 vs 裸文本 ----

def test_jsx_expression_is_not_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.tsx": "const el = <span>{it.公司}</span>;\n"})
    assert unallowed == []


def test_jsx_bare_text_is_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.tsx": "const el = <p>写死的一句话</p>;\n"})
    assert [u[2] for u in unallowed] == ["写死的一句话"]


# ---- 5. 清单：片段级放行 ----

def test_missing_from_allowlist_is_reported(tmp_path):
    unallowed, _, _ = _run(tmp_path, {"a.ts": 'const s = "已挂";\n'})
    assert [u[1] for u in unallowed] == [1]


def test_listed_fragment_is_exempt(tmp_path):
    unallowed, ok, errors = _run(tmp_path, {"a.ts": 'const s = "已挂";\n'},
                                 allowlist="a.ts = 已挂  # 阶段枚举\n")
    assert unallowed == [] and errors == []
    assert [h[2] for h in ok] == ["已挂"]


def test_only_listed_fragments_pass(tmp_path):
    """片段级放行的核心价值：同一文件里没登记的中文照样拦。

    这一条是被实证逼出来的——整文件豁免时，一个"已豁免"的文件里藏了
    4 处漏翻（列头、差异标签、按钮 tooltip），而检查全绿。
    """
    files = {"a.tsx": 'const a = <pre>{"解析卡.md"}</pre>;\nconst b = <p>没翻译的一句</p>;\n'}
    unallowed, ok, _ = _run(tmp_path, files, allowlist="a.tsx = 解析卡.md  # 真实文件名\n")
    assert [h[2] for h in ok] == ["解析卡.md"]
    assert [u[2] for u in unallowed] == ["没翻译的一句"]


def test_bare_text_is_never_exempted(tmp_path):
    """裸文本即便片段在清单里也照拦（清单只放行字符串字面量类命中）。

    否则 `<span>已挂</span>` 这种"写死给用户看的字"会借着数据豁免溜过去
    ——独立审查发现的空子。
    """
    files = {"a.tsx": 'const a = <p>已挂</p>;\n'}
    unallowed, ok, _ = _run(tmp_path, files, allowlist="a.tsx = 已挂  # 阶段枚举\n")
    assert ok == []
    assert [u[2] for u in unallowed] == ["已挂"]


# ---- 6. 清单问题（两类僵尸，都会让下一处真命中悄悄获得豁免） ----

def test_stale_file_entry_is_an_error(tmp_path):
    _, _, errors = _run(tmp_path, {"a.ts": "const x = 1;\n"},
                        allowlist="gone.tsx = 已挂  # 早就删了的文件\n")
    assert any("gone.tsx" in e for e in errors)


def test_stale_fragment_entry_is_an_error(tmp_path):
    _, _, errors = _run(tmp_path, {"a.ts": 'const s = "已挂";\n'},
                        allowlist="a.ts = 已挂|已放弃  # 阶段枚举\n")
    assert any("已放弃" in e for e in errors)


def test_missing_equal_sign_is_an_error(tmp_path):
    _, _, errors = _run(tmp_path, {"a.ts": 'const s = "已挂";\n'},
                        allowlist="a.ts  # 忘了写 =\n")
    assert any("缺少" in e for e in errors)


def test_missing_allowlist_file_is_not_an_error(tmp_path):
    """没有清单文件时只是「全都没豁免」，而不是配置报错。"""
    unallowed, _, errors = _run(tmp_path, {"a.ts": 'const s = "已挂";\n'})
    assert errors == []
    assert len(unallowed) == 1


# ---- 7. 复数 key 必须传 count ----

PLURAL_LOCALE = {
    os.path.join("i18n", "locales", "zh-CN.ts"):
        '"a.count_one": "{{count}} 条",\n"a.count_other": "{{count}} 条",\n',
}


def test_plural_key_without_count_is_reported(tmp_path):
    """不传 count 时 i18next 找不到字面量 key，界面会显示 key 名本身。

    类型与 lint 都拦不住（复数基名也是合法 TranslationKey）——2026-09-12 的
    浏览器冒烟就是这么抓到 `dash.staleSubtitle` 直接显示在页面上的。
    """
    files = dict(PLURAL_LOCALE, **{"a.tsx": 'const x = t("a.count");\n'})
    assert [p[2] for p in _plural(tmp_path, files)] == ["a.count"]


def test_plural_key_with_count_is_fine(tmp_path):
    files = dict(PLURAL_LOCALE, **{"a.tsx": 'const x = t("a.count", { count: n });\n'})
    assert _plural(tmp_path, files) == []


# ---- 8. t() 的 key 必须存在 ----

def test_missing_key_is_reported(tmp_path):
    files = {"a.tsx": 'const x = t("nope.notHere");\n',
             os.path.join("i18n", "locales", "zh-CN.ts"): '"a.b": "有",\n'}
    assert [m[2] for m in _missing(tmp_path, files)] == ["nope.notHere"]


def test_existing_key_is_fine(tmp_path):
    files = {"a.tsx": 'const x = t("a.b");\n',
             os.path.join("i18n", "locales", "zh-CN.ts"): '"a.b": "有",\n'}
    assert _missing(tmp_path, files) == []


def test_plural_base_name_counts_as_existing(tmp_path):
    """`t("a.count", {count})` 用的是基名，语言包里只有 _one/_other。"""
    files = {"a.tsx": 'const x = t("a.count", { count: n });\n',
             os.path.join("i18n", "locales", "zh-CN.ts"):
                 '"a.count_one": "{{count}} 条",\n"a.count_other": "{{count}} 条",\n'}
    assert _missing(tmp_path, files) == []
