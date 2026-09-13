# -*- coding: utf-8 -*-
"""界面 token 扫描器（`tools/check_ui_tokens.py`）自身的钉子。

扫描器自己错了的后果是两边的：太松则白装（旧类名写回来没人拦），太严则 CI 恒红
并被绕过。所以这里逐条钉住判定口径：

1. **只有确定的模式才算违规**：旧 token 名（`ink`/`good`/`warn`/`bad`/`accent`）、
   原生调色板刻度、white/black 的透明度写法、颜色任意值、CSS 里的原生 select 补丁；
2. **子串陷阱**：`text-warn` 不能命中新 token `text-warning`——2026-09-13 用子串
   手工统计时正是这里误报了 15 处，这条钉子来自一次真实踩坑；
3. **bare `bg-white` / `from-white` 不是违规**：A4 预览纸张与 PDF iframe 的底色是
   「纸张是白的」这个物理隐喻（逐处核过），只有**带透明度**的 white/black 才是
   「本可以用 token 却写死」；
4. **尺寸任意值不在此检查范围**：`max-h-[32rem]`、`w-[123px]` 属视觉刻度问题，
   由审计处理，混进来只会制造噪音；
5. **注释不算命中**：注释里提到旧类名（"旧写法 text-slate-400 已迁走"）不是违规；
6. **类名在字符串里**：与 i18n 扫描器相反，这里必须扫字符串内部（`className="…"`），
   所以注释剥离要保留字符串内容；
7. **清单是片段级**：文件里登记了一个片段，同文件里另一个未登记命中仍要报；
   片段已修掉而清单没删，必须报错（否则给将来的同名写法预授权）。
"""

import io
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import check_ui_tokens as checker  # noqa: E402

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
        io.open(str(tools_dir / "ui_tokens_allowlist.txt"), "w",
                encoding="utf-8").write(allowlist)
    return str(tmp_path)


def _run(tmp_path, files, allowlist=""):
    root = _make_repo(tmp_path, files, allowlist)
    unallowed, ok, errors = checker.check(root)
    return unallowed, ok, errors


def _snips(hits):
    return sorted(h[2] for h in hits)


def _kinds(hits):
    return sorted(set(h[3] for h in hits))


# ---- 1. 四类真命中 + CSS 补丁 -------------------------------------------------


def test_legacy_token_names_are_hits(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "text-ink";\nconst b = "bg-good";\n'
                 'const c = "border-bad";\nconst d = "text-accent";\n'})
    assert _snips(unallowed) == ["bg-good", "border-bad", "text-accent", "text-ink"]
    assert _kinds(unallowed) == ["legacy"]


def test_palette_scales_are_hits(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "text-slate-400";\nconst b = "bg-red-500";\n'
                 'const c = "border-zinc-800";\nconst d = "text-slate-400/50";\n'})
    assert _kinds(unallowed) == ["palette"]
    assert "text-slate-400/50" in _snips(unallowed), "带透明度后缀的刻度也要报"


def test_white_black_alpha_is_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "ring-white/5";\nconst b = "bg-black/60";\n'
                 'const c = "bg-white/[0.05]";\nconst d = "text-black/[.6]";\n'})
    assert _snips(unallowed) == [
        "bg-black/60", "bg-white/[0.05]", "ring-white/5", "text-black/[.6]"]
    assert _kinds(unallowed) == ["alpha"], "任意值透明度同样算去 token 化"


def test_color_arbitrary_values_are_hits(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "bg-[#0a0e17]";\nconst b = "text-[rgb(1,2,3)]";\n'})
    assert _snips(unallowed) == ["bg-[#0a0e17]", "text-[rgb(1,2,3)]"]
    assert _kinds(unallowed) == ["hex"]


def test_css_native_select_patch_is_a_hit(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "index.css": "select {\n  background-color: #000;\n}\n"})
    assert _kinds(unallowed) == ["select-patch"]
    assert unallowed[0][1] == 1


# ---- 2. 不得误报（每条都是真实踩坑或经核实的例外） -----------------------------


def test_warning_token_is_not_flagged_as_warn(tmp_path):
    """子串陷阱：`text-warn` 不能命中 `text-warning`（手工统计时误报过 15 处）。"""
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "text-warning";\nconst b = "bg-warning/15";\n'
                 'const c = "text-success";\n'})
    assert unallowed == []


def test_semantic_tokens_are_not_flagged(tmp_path):
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "border-border-strong";\nconst b = "ring-ring";\n'
                 'const c = "text-muted-foreground";\nconst d = "accent-primary";\n'})
    assert unallowed == [], "语义 token 与 accent-* 表单控件工具类都要放行"


def test_bare_white_is_not_flagged(tmp_path):
    """纸张隐喻：A4 预览与 PDF iframe 的 bare white 不属去 token 化。"""
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "origin-top-left bg-white shadow-elevated";\n'
                 'const b = "bg-gradient-to-b from-white to-primary/70";\n'})
    assert unallowed == []


def test_size_arbitrary_values_are_not_flagged(tmp_path):
    """尺寸任意值属视觉刻度问题（审计批处理），这条检查不碰。"""
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": 'const a = "max-h-[32rem]";\nconst b = "h-[70vh]";\n'
                 'const c = "w-[123px]";\n'})
    assert unallowed == []


def test_comments_are_not_hits(tmp_path):
    """注释里提到旧类名不是违规；块注释还得保持行号不漂。"""
    tsx = ('// 旧写法 text-slate-400 已迁走\n'
           '/* 也别学 ring-white/5 */\n'
           'const ok = "text-primary";\n'
           'const url = "https://example.com/a";\n')
    unallowed, _, _ = _run(tmp_path, {"a.tsx": tsx, "index.css": "/* select { } */\n"})
    assert unallowed == []


def test_class_name_inside_string_is_scanned(tmp_path):
    """与 i18n 扫描器相反：这里必须扫字符串内部，className 就在字符串里。"""
    unallowed, _, _ = _run(tmp_path, {
        "a.tsx": '<div className="rounded-lg text-ink hover:bg-good/10">x</div>\n'})
    assert _snips(unallowed) == ["bg-good/10", "text-ink"], "字符串里的类名要被抓到"


# ---- 3. 豁免清单（片段级 + 僵尸条目） -----------------------------------------


def test_allowlist_is_fragment_level(tmp_path):
    """登记片段后放行；同文件里未登记的第二个命中仍要报。"""
    files = {"a.tsx": 'const a = "ring-white/5";\nconst b = "text-slate-400";\n'}
    allow = "a.tsx = ring-white/5      # 第三方组件原样搬来，暂留\n"
    unallowed, ok, errors = _run(tmp_path, files, allow)
    assert _snips(ok) == ["ring-white/5"]
    assert _snips(unallowed) == ["text-slate-400"]
    assert errors == []


def test_allowlist_stale_entry_errors(tmp_path):
    """片段已修掉但清单没删 → 报错（否则给将来的同名写法预授权）。"""
    files = {"a.tsx": 'const a = "text-primary";\n'}
    allow = "a.tsx = ring-white/5      # 早就改掉了\n"
    unallowed, ok, errors = _run(tmp_path, files, allow)
    assert unallowed == [] and ok == []
    assert errors and "已无命中" in errors[0]


def test_allowlist_line_without_equals_errors(tmp_path):
    files = {"a.tsx": 'const a = "ring-white/5";\n'}
    _, _, errors = _run(tmp_path, files, "a.tsx  ring-white/5\n")
    assert errors and "缺少 `=`" in errors[0]


# ---- 4. 真实仓库现状（本批把 16 处 ring-white/5 收敛为 token 后应恒为 0） ---------


def test_real_repo_has_no_violations():
    unallowed, _ok, errors = checker.check(ROOT_DIR)
    assert errors == []
    assert unallowed == [], "真实仓库出现 token 违规：%s" % unallowed
