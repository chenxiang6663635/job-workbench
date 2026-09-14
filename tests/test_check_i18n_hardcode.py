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


def _make_repo(tmp_path, files, allowlist="", electron_files=None):
    """按 {相对 src 的路径: 内容} 造一个小源码树，可选写允许清单。

    electron_files 同理，但落在 web/electron/（第二棵被扫的源码树）。
    """
    for rel, text in files.items():
        full = tmp_path / SRC / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        io.open(str(full), "w", encoding="utf-8").write(text)
    for rel, text in (electron_files or {}).items():
        full = tmp_path / "web" / "electron" / rel
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


def test_interpolated_key_is_skipped(tmp_path):
    """模板串插值键（`domain.${group}.${raw}`）静态不可判定：跳过而非误报。

    领域枚举的显示层（lib/domainLabels.ts）按「组.真值」拼动态键，未登记的值
    靠 defaultValue 原样回落——把它当「key 不存在」报出来是假阳性。
    """
    files = {
        "lib/domainLabels.ts": (
            'const k = t(`domain.${group}.${raw}`, { defaultValue: raw });'
        ),
        "i18n/locales/zh-CN.ts": 'const zhCN = {\n  "app.title": "x",\n} as const;',
    }
    assert _missing(tmp_path, files) == []


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


# ---- 9. Electron 主进程（第二棵源码树，web/electron） ----

def _run_with_electron(tmp_path, files, electron_files, allowlist=""):
    root = _make_repo(tmp_path, files, allowlist, electron_files)
    unallowed, _ok, _plural, _missing, errors = checker.check(root)
    return unallowed, errors


def test_electron_cjk_string_is_reported(tmp_path):
    """main.js 的用户可见串（窗口标题/更新对话框/日志）与前端同一套口径。"""
    files = {"placeholder.js": "const x = 1;\n"}
    electron = {
        "main.js": 'log("后端已就绪");\n'
                   'const win = new BrowserWindow({ title: "求职工作台" });\n',
    }
    unallowed, errors = _run_with_electron(tmp_path, files, electron)
    assert errors == []
    assert {u[0].replace(os.sep, "/") for u in unallowed} == {"electron/main.js"}
    snippets = {u[2] for u in unallowed}
    assert "后端已就绪" in snippets and "求职工作台" in snippets
    assert all(u[3] == "string" for u in unallowed)


def test_electron_comment_is_not_a_hit(tmp_path):
    """注释不翻的口径在 Electron 侧同样成立（main.js 的注释全是中文）。"""
    files = {"placeholder.js": "const x = 1;\n"}
    electron = {"main.js": "// 后端已就绪（注释不翻）\nconst x = 1;\n"}
    unallowed, errors = _run_with_electron(tmp_path, files, electron)
    assert unallowed == []
    assert errors == []


def test_electron_release_dir_is_skipped(tmp_path):
    """release/ 是本地打包产物（含旧文案的 bundle），不在检查范围。"""
    files = {"placeholder.js": "const x = 1;\n"}
    electron = {os.path.join("release", "bundle.js"): 'log("后端已就绪");\n'}
    unallowed, errors = _run_with_electron(tmp_path, files, electron)
    assert unallowed == []
    assert errors == []


# ---- 10. 硬编码英文（中文界面下的英文残留） ----
# 这一类的存在理由与中文那类**相反**：中文检查防的是"英文界面里冒中文"，
# 它只看 CJK，于是"中文界面里冒英文"（设置页的 Provider、Electron 的窗口标题与
# 更新对话框）三处都是它的结构性盲区——tsc / eslint / UI 冒烟同样看不见。
# 判定同样从紧：只扫 pages/** 与 web/electron/**，只认 JSX 裸文本、少数文案属性
# 与 Electron 的对话框文案键；豁免用**同一份清单的 `en:` 段**（片段级 + 理由）。

EN_SCOPE = os.path.join("pages", "Settings.tsx")


def _en(tmp_path, files, allowlist="", electron_files=None):
    root = _make_repo(tmp_path, files, allowlist, electron_files)
    unallowed, ok, errors = checker.check_english(root)
    return unallowed, ok, errors


def test_real_repo_has_no_violations():
    """对**真实仓库**跑一遍：两类检查都不得有未豁免命中（独立审查 m7）。

    合成树证明判定逻辑，证明不了"仓库此刻真的干净"。缺这条时，仓库里新冒出来的
    一句硬编码文案只能等 CI 发现——而 CI 跑的就是同一条命令，人却常常只跑 pytest。
    与 `test_check_ui_tokens.py::test_real_repo_has_no_violations` 同一用意。
    """
    unallowed, _ok, plural, missing, errors = checker.check(ROOT_DIR)
    en_unallowed, _en_ok, en_errors = checker.check_english(ROOT_DIR)

    assert unallowed == []
    assert en_unallowed == []
    assert plural == []
    assert missing == []
    assert errors + en_errors == []


def test_english_jsx_bare_text_is_reported(tmp_path):
    files = {EN_SCOPE: "const el = <CardTitle>Provider</CardTitle>;\n"}
    unallowed, _, errors = _en(tmp_path, files)
    assert [u[2] for u in unallowed] == ["Provider"]
    assert errors == []


def test_english_bare_text_after_a_self_closing_tag_is_reported(tmp_path):
    """`<Icon /> Provider` —— 设置页卡片标题的真实形态（图标 + 文案）。"""
    files = {EN_SCOPE: '<CardTitle className="x">\n  <Icon size={16} /> Provider\n</CardTitle>\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert [u[2] for u in unallowed] == ["Provider"]


def test_translated_jsx_text_is_not_reported(tmp_path):
    files = {EN_SCOPE: 'const el = <CardTitle>{t("settings.providerTitle")}</CardTitle>;\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_chinese_bare_text_is_not_the_english_checks_business(tmp_path):
    """中文裸文本归中文检查管（它更严：裸文本永不放行），这里不重复报。"""
    files = {EN_SCOPE: "const el = <p>中文文案</p>;\n"}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_english_text_attribute_is_reported(tmp_path):
    files = {EN_SCOPE: '<button title="Switch workspace" />\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert [u[2] for u in unallowed] == ["Switch workspace"]


def test_translated_text_attribute_is_not_reported(tmp_path):
    files = {EN_SCOPE: '<button title={t("nav.switchWorkspaceTitle")} />\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_arrow_function_continuation_is_not_reported(tmp_path):
    """`=>` 的 `>` 不是标签收尾——否则链式调用的每一行都会被当成裸文本。

    真实误报（2026-09-13 首次在仓库上试跑时抓到）：`const loadPaths = () =>`
    的下一行 `api` 被报成"硬编码英文 api"。误报的代价不是多看一眼，而是
    检查被绕过——CI 恒红之后，人就会开始往清单里塞假条目。
    """
    files = {EN_SCOPE: "const loadPaths = () =>\n  api\n    .systemPaths()\n    .then(f);\n"}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_jsx_expression_continuation_is_not_reported(tmp_path):
    """`onClick={() =>` 之后那行是 JSX 表达式（取数/调用），不是裸文本。"""
    files = {EN_SCOPE: 'const el = <Button onClick={() =>\n  setInfo(t("x.y"))\n} />;\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_single_line_block_comment_is_not_reported(tmp_path):
    """单行块注释里的属性不算命中（独立审查 m1）。

    `/* title="X" */` 这种写法：进 `_scan_line` 时置 in_block=True 又立刻闭合，
    返回的 in_block 是 False——只看"行首是否在块注释里"会漏掉它，于是注释里的
    文案被当成真命中。注释不翻是本项目口径，误报会把人逼去清单里塞假条目。
    """
    files = {EN_SCOPE: '/* title="Switch workspace" */\nconst x = 1;\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_line_comment_attribute_is_not_reported(tmp_path):
    files = {EN_SCOPE: '// title="Switch workspace"\nconst x = 1;\n'}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_comparison_expression_is_not_reported(tmp_path):
    """同行比较表达式不是 JSX（独立审查 m2）。

    `len > min && len < max` 会命中"`>Text<`"的形状——`EN_JSX_INLINE` 必须要求
    那个 `>` 属于一个标签（前面出现过 `<Tag` / `</` / `<>`），否则 `.ts`/`.js`
    文件里的比较运算会被成片误报。
    """
    files = {EN_SCOPE: "const ok = len > min && len < max;\nconst y = 2;\n"}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_english_outside_the_scope_is_not_reported(tmp_path):
    """范围是 pages/**、components/** 与 web/electron/**——`lib/**` 之类仍不扫。

    （2026-09-14 扩范围到 components：这条原来拿 components 当"范围外"的例子，
    扩完就不成立了，改用 lib/ 继续钉住「范围之外不报」这件事。）
    """
    files = {os.path.join("lib", "Widget.tsx"): "const el = <p>Hardcoded</p>;\n"}
    unallowed, _, _ = _en(tmp_path, files)
    assert unallowed == []


def test_electron_dialog_copy_is_reported(tmp_path):
    files = {"placeholder.ts": "const x = 1;\n"}
    electron = {"main.js": 'dialog.showMessageBox({ title: "Update available" });\n'}
    unallowed, _, errors = _en(tmp_path, files, electron_files=electron)
    assert [u[2] for u in unallowed] == ["Update available"]
    assert errors == []


def test_electron_i18n_table_is_exempt(tmp_path):
    """主进程语言包（web/electron/i18n.js）是英文的家——与前端 i18n/locales 同理。"""
    files = {"placeholder.ts": "const x = 1;\n"}
    electron = {"i18n.js": 'const T = { en: { update: "Update available" } };\n'}
    unallowed, _, _ = _en(tmp_path, files, electron_files=electron)
    assert unallowed == []


def test_english_allowlist_is_fragment_level(tmp_path):
    files = {EN_SCOPE: "const a = <p>Provider</p>;\nconst b = <p>Legacy badge</p>;\n"}
    allowlist = "en:pages/Settings.tsx = Provider  # 品牌名，不翻\n"
    unallowed, ok, errors = _en(tmp_path, files, allowlist=allowlist)
    assert [h[2] for h in ok] == ["Provider"]
    assert [u[2] for u in unallowed] == ["Legacy badge"]
    assert errors == []


def test_multiple_allowlist_lines_for_one_file_merge(tmp_path):
    """同一文件允许分多行登记（每行写自己的理由）——是合并不是覆盖。

    首版实现是赋值，于是同一文件的三行只剩最后一行生效：清单"看着写了"、
    实际没放行，而且**不报任何错**。英文那类尤其需要分行——"示例值"与
    "协议取值"是两种理由，挤在一行会把它们糊成一句。
    """
    files = {EN_SCOPE: 'const a = <img alt="Provider" />;\nconst b = <img alt="Legacy badge" />;\n'}
    allowlist = ("en:pages/Settings.tsx = Provider  # 品牌名\n"
                 "en:pages/Settings.tsx = Legacy badge  # 旧标识\n")

    unallowed, ok, errors = _en(tmp_path, files, allowlist=allowlist)

    assert [h[2] for h in ok] == ["Provider", "Legacy badge"]
    assert unallowed == []
    assert errors == []


def test_english_allowlist_zombie_entry_is_an_error(tmp_path):
    """两类僵尸都要报（与中文清单同一纪律），只是报的粒度不同：
    文件已无命中报文件，片段已不再出现报片段——留着任何一条，都会给将来的
    同名英文预授权。"""
    allowlist = "en:pages/Settings.tsx = Provider  # 已经改走 t() 了\n"

    _, _, file_level = _en(tmp_path, {EN_SCOPE: "const x = 1;\n"}, allowlist=allowlist)
    assert any("Settings.tsx" in e for e in file_level)

    _, _, frag_level = _en(tmp_path, {EN_SCOPE: "const a = <p>Legacy badge</p>;\n"},
                           allowlist=allowlist)
    assert any("Provider" in e for e in frag_level)


def test_en_prefixed_entry_does_not_leak_into_the_chinese_check(tmp_path):
    """`en:` 段是另一套豁免：不能顺手把同一文件的中文数据也放行。"""
    files = {os.path.join("components", "X.tsx"): 'const s = "已挂";\n'}
    unallowed, _, errors = _run(tmp_path, files,
                                allowlist="en:components/X.tsx = 已挂  # 故意写在同一行\n")
    assert [u[2] for u in unallowed] == ["已挂"]
    assert errors == []


# ---- 英文检查：范围是否被真正消费、误报回归（2026-09-14） ----

def test_english_scope_really_covers_components(tmp_path):
    """`EN_SCOPE_RELS` 必须被真正消费，components 里的硬编码英文要报。

    2026-09-14 实测：check_english 的 targets 曾是硬编码的 pages + electron，
    把范围常量改了、检查行为纹丝不动——插进去的硬编码英文照样漏过（反向验证抓到）。
    """
    files = {os.path.join("components", "Foo.tsx"): "<span>Hardcoded English</span>\n"}
    root = _make_repo(tmp_path, files)
    unallowed, _ok, _errors = checker.check_english(root)
    assert [u[2] for u in unallowed] == ["Hardcoded English"]


def test_semicolon_terminated_jsx_text_is_not_a_hit():
    """类型注解 `=> void;` 里冒出来的 `void;` 不是文案。

    泛型的 `<K` 会被 TAG_LIKE 认成标签、`> void;` 又被当成行尾文案，两处叠加就是
    2026-09-14 扩到 components 时抓到的三处误报；规则：以 `;` 结尾一律当代码跳过。
    """
    hits = checker.find_hardcoded_english(
        "set: <K extends keyof Draft>(k: K, v: Draft[K]) => void;\n")
    assert hits == []


def test_english_scope_comes_from_the_constant(tmp_path, monkeypatch):
    """范围必须由 `EN_SCOPE_RELS` 决定：改常量要立刻生效。

    与上一条互补——那条证明 components 被扫；这条证明"扫哪里"由常量说了算，
    即使有人把 targets 再改回硬编码（同时把常量留着当摆设），这里也会红。
    """
    files = {
        os.path.join("pages", "A.tsx"): "const a = <span>From pages</span>;\n",
        os.path.join("components", "B.tsx"): "const b = <span>From components</span>;\n",
    }
    root = _make_repo(tmp_path, files)
    monkeypatch.setattr(checker, "EN_SCOPE_RELS",
                        (os.path.join("web", "frontend", "src", "components"),))
    unallowed, _ok, _errors = checker.check_english(root)
    assert [u[2] for u in unallowed] == ["From components"]
