# -*- coding: utf-8 -*-
"""jd_score 纯函数测试群：档位判定（含小数缝隙）与插件解析的显式失败。

2026-10-08 积累期审计的头号正确性项（1.1-1 / 1.1-2），先红后绿：

- `verdict`：`THRESHOLDS` 是整数闭区间（75-100 / 60-74 / …），而维度分子允许
  小数（`parse_dimension` 的 `\\d+(?:\\.\\d+)?`）——总分 74.5 落进 [60,74] 与
  [75,100] 之间的缝，被无匹配兜底判成最差档「不投」。
- `resolve_profile`：未指定 `--domain` 时按字母序取第一个模板插件
  （`hvac-cooling` 排在 `software-backend` 前）——拿错词典不报错。

本文件在修复前应有两组失败：`test_verdict_accepts_decimal_total_in_the_gap`
与 `test_resolve_profile_prefers_workspace_copy_*`。修复后全绿并成为回归网。
"""
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import jd_score  # noqa: E402


# ---------------------------------------------------------------------------
# verdict：档位按「下界」判定，小数不得落缝
# ---------------------------------------------------------------------------

def test_verdict_accepts_decimal_total_in_the_gap():
    """74.5 必须属「建议投」——修复前它落进两档之间的缝、被判「不投」。"""
    level, action = jd_score.verdict(74.5)
    assert level == "建议投", (level, action)
    assert action == "执行 /apply 生成投递包"


@pytest.mark.parametrize("total,level", [
    (100, "强烈建议投"), (75, "强烈建议投"), (74.999, "建议投"),
    (74, "建议投"), (60, "建议投"), (59.999, "斟酌"),
    (59, "斟酌"), (45, "斟酌"), (44.5, "大概率跳过"),
    (30, "大概率跳过"), (29.5, "不投"), (0, "不投"),
])
def test_verdict_bands_follow_lower_bounds(total, level):
    """半开语义：区间左闭右开，边界整数归属上档（60 → 建议投、59 → 斟酌）。"""
    assert jd_score.verdict(total)[0] == level


def test_verdict_every_half_point_lands_in_a_band():
    """0~100 全轴任意半步长取值都必须命中五档之一——不存在无档可归的缝隙。"""
    tiers = {tier for _lo, _hi, tier, _a in jd_score.THRESHOLDS}
    value = 0.0
    while value <= 100.0:
        level, _action = jd_score.verdict(value)
        assert level in tiers, (value, level)
        value += 0.5


def test_verdict_negative_is_bottom_band_by_definition():
    """负分（合法总分 ≥0，只可能来自手改数据）显式归末档——语义明确，不是"兜底"。"""
    assert jd_score.verdict(-0.5) == (jd_score.THRESHOLDS[-1][2], jd_score.THRESHOLDS[-1][3])


# ---------------------------------------------------------------------------
# resolve_profile：拿不准就显式失败，不猜
# ---------------------------------------------------------------------------

def _mk_template(tmp_path, names):
    """临时模板目录：每个插件只放解析所需的最小文件。"""
    tpl = tmp_path / "profiles"
    for name in names:
        plugin = tpl / name
        (plugin / "directions").mkdir(parents=True)
        (plugin / "profile.md").write_text("# 插件 %s\n" % name, encoding="utf-8")
        (plugin / "lexicon.md").write_text("## Primary（3 分/项）\n\n%s词条\n" % name,
                                           encoding="utf-8")
        (plugin / "directions" / "datacenter.md").write_text("# 方向：数据中心\n",
                                                             encoding="utf-8")
    return tpl


def _mk_workspace(tmp_path, name, with_profile=False):
    ws = tmp_path / name
    (ws / "config").mkdir(parents=True)
    if with_profile:
        (ws / "config" / "profile.md").write_text("# 工作区档案\n", encoding="utf-8")
        (ws / "config" / "lexicon.md").write_text("## Primary（3 分/项）\n\n工作区词条\n",
                                                  encoding="utf-8")
        (ws / "config" / "directions").mkdir()
        (ws / "config" / "directions" / "datacenter.md").write_text("# 方向：数据中心\n",
                                                                     encoding="utf-8")
    return ws


def test_resolve_profile_prefers_workspace_copy_without_fake_warning(tmp_path, monkeypatch):
    """工作区有 config/profile.md：用它，且不再打「回退使用第一个插件」的假警告。

    修复前：domain 被赋成工作区的**父目录名**（与领域毫无关系），并附一条
    「未指定 --domain，回退使用第一个插件 `…`」。
    """
    monkeypatch.setattr(jd_score, "PROFILES",
                        str(_mk_template(tmp_path, ["hvac-cooling", "software-backend"])))
    ws = _mk_workspace(tmp_path, "personal", with_profile=True)

    profile_dir, direction_file, warns = jd_score.resolve_profile(str(ws))

    assert profile_dir == os.path.join(str(ws), "config")
    assert direction_file and direction_file.endswith("datacenter.md")
    assert not any("回退使用第一个插件" in w for w in warns), warns


def test_resolve_profile_missing_workspace_profile_fails_explicitly(tmp_path, monkeypatch):
    """工作区没有档案、又未传 --domain：显式失败，不许按字母序拿第一个插件。"""
    monkeypatch.setattr(jd_score, "PROFILES",
                        str(_mk_template(tmp_path, ["hvac-cooling", "software-backend"])))
    ws = _mk_workspace(tmp_path, "fresh", with_profile=False)

    profile_dir, direction_file, warns = jd_score.resolve_profile(str(ws))

    assert profile_dir is None and direction_file is None
    assert any("--domain" in w for w in warns), warns
    # 不许把任何一个模板插件当成"默认"塞给用户
    assert not any("hvac-cooling" in w or "software-backend" in w for w in warns), warns


def test_resolve_profile_explicit_domain_reads_template(tmp_path, monkeypatch):
    """显式 --domain：从模板目录读——这是无工作区档案时的正路。"""
    tpl = _mk_template(tmp_path, ["hvac-cooling", "software-backend"])
    monkeypatch.setattr(jd_score, "PROFILES", str(tpl))
    ws = _mk_workspace(tmp_path, "fresh", with_profile=False)

    profile_dir, direction_file, warns = jd_score.resolve_profile(
        str(ws), domain="software-backend")

    assert profile_dir == os.path.join(str(tpl), "software-backend")
    assert direction_file and direction_file.endswith("datacenter.md")
    assert warns == [], warns


def test_resolve_profile_workspace_direction_missing_warns_with_real_label(tmp_path, monkeypatch):
    """工作区档案下方向不存在：警告里的插件名不能是父目录名（修复前的怪相）。"""
    monkeypatch.setattr(jd_score, "PROFILES",
                        str(_mk_template(tmp_path, ["hvac-cooling", "software-backend"])))
    ws = _mk_workspace(tmp_path, "personal", with_profile=True)

    profile_dir, direction_file, warns = jd_score.resolve_profile(
        str(ws), direction="not-a-direction")

    assert profile_dir == os.path.join(str(ws), "config")
    assert any("not-a-direction" in w for w in warns), warns
    assert not any(os.path.basename(str(tmp_path)) in w for w in warns), warns
