# -*- coding: utf-8 -*-
"""check_themes 的三条规则与边界（批 4 主题门禁）。

规则口径 = 施工单：parity（变量齐全）、对比度（正文 4.5:1 / 大字图形 3:1）、
暗色明度阶梯（相邻表面 ≥1.12）。三者共同拦的都是「某套主题某处看不清」——
人眼迟早漏，所以把「缺键 / 低对比 / 阶梯过近 / 亮主题不误报阶梯」四类钉在这。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_themes  # noqa: E402


def _vars(**overrides):
    """构造一套「自身全过」的暗主题变量；缺省值是中性灰，对深面浅面都不低于 3:1。"""
    values = {key: "0 0% 60%" for key in check_themes.EXPECTED_KEYS}
    values.update({
        "background": "222 47% 5%",
        "foreground": "210 40% 96%",
        "card": "222 44% 12%",
        "card-foreground": "210 40% 96%",
        "popover": "222 42% 26%",
        "popover-foreground": "210 40% 96%",
        "secondary": "220 39% 16%",
        "secondary-foreground": "210 40% 96%",
        "muted": "220 39% 16%",
        "muted-foreground": "215 25% 70%",
        "primary": "199 89% 58%",
        "primary-foreground": "222 47% 6%",
        "elevation-0-surface": "222 47% 5%",
        "elevation-1-surface": "222 44% 12%",
        "elevation-2-surface": "222 43% 18%",
        "elevation-3-surface": "222 42% 26%",
    })
    values.update(overrides)
    return values


def test_repo_themes_all_pass():
    """仓库里的主题（默认暗 + 全部皮肤文件）必须全过——门禁的核心承诺，CI 同跑。"""
    assert check_themes.main([]) == 0


def test_parity_flags_missing_key():
    values = _vars()
    key = check_themes.EXPECTED_KEYS[0]
    del values[key]
    problems = check_themes.audit_theme("t", values, set(check_themes.EXPECTED_KEYS))
    assert any("parity" in p and key in p for p in problems), problems


def test_contrast_flags_low_pair():
    """把前景压暗到与背景接近——必须被点名（正文组合 4.5:1）。"""
    problems = check_themes.audit_theme(
        "t", _vars(foreground="210 40% 40%"), set(check_themes.EXPECTED_KEYS))
    assert any("对比度" in p and "foreground" in p for p in problems), problems


def test_ladder_flags_close_surfaces():
    """把 elev-2 拉到与 elev-1 几乎同亮——暗色阶梯规则必须点名。"""
    problems = check_themes.audit_theme(
        "t", _vars(**{"elevation-2-surface": "222 43% 13%"}),
        set(check_themes.EXPECTED_KEYS))
    assert any("明度阶梯" in p for p in problems), problems


def test_light_theme_skips_ladder():
    """亮主题表面恒定（只变阴影，三件套的非对称规则）——阶梯规则不得误报。"""
    values = _vars(**{
        "background": "220 23% 97%",
        "foreground": "222 47% 11%",
        "card": "0 0% 100%",
        "card-foreground": "222 47% 11%",
        "popover-foreground": "222 47% 11%",
        "secondary": "220 14% 94%",
        "secondary-foreground": "222 47% 11%",
        "muted": "220 14% 94%",
        "muted-foreground": "215 25% 35%",
        "primary": "200 98% 39%",
        "primary-foreground": "0 0% 100%",
        "elevation-0-surface": "220 14% 94%",
        "elevation-1-surface": "0 0% 100%",
        "elevation-2-surface": "0 0% 100%",
        "elevation-3-surface": "0 0% 100%",
        "success": "160 84% 30%",
        "warning": "35 92% 30%",
        "destructive": "0 72% 45%",
    })
    # 亮主题的 chart 用较深的值（对白卡 ≥3:1）
    for i in range(1, 9):
        values["chart-%d" % i] = "0 0% 35%"
    problems = check_themes.audit_theme("t", values, set(check_themes.EXPECTED_KEYS))
    assert not any("明度阶梯" in p for p in problems), problems
