# -*- coding: utf-8 -*-
"""i18n 键健康检查器（tools/check_i18n_keys.py，issue #212）的五类样本测试。

覆盖「检查器真的拦得住」与「检查器不误报」两面——后者是实测教训：粗口径会
把数据字段键（mailProvider.*）与模板键（reminderDays_*）判成死键，检查器一
上线就误报一片。
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import check_i18n_keys  # noqa: E402


def _fake_repo(tmp_path, zh_keys, en_keys=None, ts_corpus="", py_corpus=""):
    """最小仓库：两份 locale + 前端语料（App.tsx）+ 后端语料（providers.py）。"""
    if en_keys is None:
        en_keys = zh_keys
    locales = tmp_path / "web" / "frontend" / "src" / "i18n" / "locales"
    locales.mkdir(parents=True)
    for name, keys in (("zh-CN.ts", zh_keys), ("en.ts", en_keys)):
        body = "".join('  "%s": "值",\n' % key for key in keys)
        (locales / name).write_text("const loc = {\n%s};\n" % body, encoding="utf-8")

    src = tmp_path / "web" / "frontend" / "src"
    if ts_corpus:
        (src / "App.tsx").write_text(ts_corpus, encoding="utf-8")

    backend = tmp_path / "web" / "backend"
    backend.mkdir(parents=True)
    if py_corpus:
        (backend / "providers.py").write_text(py_corpus, encoding="utf-8")
    return tmp_path


def test_dead_key_is_reported(tmp_path):
    """定义了但无人引用 → 报死键（检查器的本职）。"""
    root = _fake_repo(tmp_path, ["live.key", "dead.key"],
                      ts_corpus='const label = t("live.key");\n')

    dead, zh_only, en_only = check_i18n_keys.find_violations(str(root))

    assert dead == ["dead.key"]
    assert zh_only == [] and en_only == []


def test_plural_base_counts_as_referenced(tmp_path):
    """`x_one`/`x_other` 经基名 x 被 t("x", {count}) 引用 → 不算死键。"""
    root = _fake_repo(tmp_path, ["n_one", "n_other"],
                      ts_corpus='const text = t("n", { count: total });\n')

    dead, _zh, _en = check_i18n_keys.find_violations(str(root))

    assert dead == []


def test_template_prefix_counts_as_referenced(tmp_path):
    """`t(`drill.mode.${m}`)` 覆盖 drill.mode.* → 放过（静态不可判定时不误报）。"""
    root = _fake_repo(tmp_path, ["drill.mode.due", "drill.mode.random"],
                      ts_corpus='const text = t(`drill.mode.${mode}`);\n')

    dead, _zh, _en = check_i18n_keys.find_violations(str(root))

    assert dead == []


def test_underscore_template_and_concat_prefixes(tmp_path):
    """`reminderDays_${v}` 与 `"mailProvider." + id` 两种形态都要放过。"""
    root = _fake_repo(tmp_path, ["settings.reminderDays_3", "mailProvider.gmail"],
                      ts_corpus='const a = t(`settings.reminderDays_${days}`);\n'
                                'const b = t("mailProvider." + provider.id);\n')

    dead, _zh, _en = check_i18n_keys.find_violations(str(root))

    assert dead == []


def test_data_field_value_in_python_counts_as_referenced(tmp_path):
    """键作为**后端 Python 的字段值**出现（provider 元数据）→ 不算死键。

    这是跨端语料的实测依据：mailProvider.* 只在后端被字面量声明。
    """
    root = _fake_repo(tmp_path, ["mailProvider.gmail"],
                      py_corpus='PROVIDERS = [{"label_key": "mailProvider.gmail"}]\n')

    dead, _zh, _en = check_i18n_keys.find_violations(str(root))

    assert dead == []


def test_asymmetry_is_reported_both_directions(tmp_path):
    """中英键集合互差 → 两个方向都要报（逐原键比，不做复数归并）。"""
    root = _fake_repo(tmp_path, ["both.key", "zh.only"],
                      en_keys=["both.key", "en.only"],
                      ts_corpus='t("both.key"); t("zh.only"); t("en.only");\n')

    dead, zh_only, en_only = check_i18n_keys.find_violations(str(root))

    assert dead == []
    assert zh_only == ["zh.only"]
    assert en_only == ["en.only"]


def test_locale_files_are_not_their_own_corpus(tmp_path):
    """locale 自身不进语料——否则每个键都能"命中"自己，检查器永远绿。"""
    root = _fake_repo(tmp_path, ["never.used"])  # 没有任何引用

    dead, _zh, _en = check_i18n_keys.find_violations(str(root))

    assert dead == ["never.used"]


def test_main_exit_codes(tmp_path, capsys):
    """退出码三态：绿 0 / 有问题 1；--list-dead 恒 0（人工清理入口）。"""
    clean = _fake_repo(tmp_path / "clean", ["ok.key"], ts_corpus='t("ok.key");\n')
    assert check_i18n_keys.main(["--root", str(clean)]) == 0
    assert "OK" in capsys.readouterr().out

    dirty = _fake_repo(tmp_path / "dirty", ["dead.key"])
    assert check_i18n_keys.main(["--root", str(dirty)]) == 1
    assert "FAIL" in capsys.readouterr().out

    assert check_i18n_keys.main(["--root", str(dirty), "--list-dead"]) == 0
    assert "dead.key" in capsys.readouterr().out


def test_real_repo_is_clean():
    """真实仓库当前全绿（存量 5 个死键已随本批清掉）。

    这条同时是**回归网**：将来往 locale 加键却没人引用、或只补一种语言，
    CI 会在 PR 上红——那正是本检查器存在的意义。
    """
    dead, zh_only, en_only = check_i18n_keys.find_violations(ROOT_DIR)
    assert dead == [], "新出现的死键：%s" % dead
    assert zh_only == [] and en_only == [], (zh_only, en_only)
