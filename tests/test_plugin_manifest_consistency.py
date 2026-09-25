# -*- coding: utf-8 -*-
"""插件清单一致性校验的锁死测试（2026-09-25 发布前收口批）。

背景（独立审计）：「技能清单」在仓库里有三份手写副本——`.codebuddy-plugin/plugin.json`
的 `skills`、`.codebuddy-plugin/marketplace.json` 的 `plugins[0].skills`、以及
`skills/` 磁盘目录。`jwb-domain-setup` 加入时 marketplace.json 漏改（8 vs 9），
而当时的 `check_plugin_assets.py` 只查 commands/agents 的 frontmatter——
没有任何防线能发现。

本文件在**临时仓库骨架**上直接测 `manifest_consistency_problems`：
三处集合必须一致；description 里的技能数量（阿拉伯数字，可写也可不写，
写了就必须对）必须等于集合大小。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from check_plugin_assets import manifest_consistency_problems  # noqa: E402


def _make(tmp_path, *, disk, plugin_list, market_list,
          plugin_desc=None, market_desc=None, market_plugin_desc=None):
    """搭最小仓库骨架：skills/ 磁盘目录 + 两份清单（清单内容与磁盘**各自独立**，
    这样才能构造出「漂移」形态）。"""
    for name in disk:
        (tmp_path / "skills" / name).mkdir(parents=True, exist_ok=True)
    plugin_dir = tmp_path / ".codebuddy-plugin"
    plugin_dir.mkdir(exist_ok=True)

    plugin = {"skills": ["./skills/%s" % n for n in plugin_list]}
    if plugin_desc is not None:
        plugin["description"] = plugin_desc
    market = {"plugins": [{"skills": ["./skills/%s" % n for n in market_list]}]}
    if market_desc is not None:
        market["description"] = market_desc
    if market_plugin_desc is not None:
        market["plugins"][0]["description"] = market_plugin_desc

    (plugin_dir / "plugin.json").write_text(
        json.dumps(plugin, ensure_ascii=False), encoding="utf-8")
    (plugin_dir / "marketplace.json").write_text(
        json.dumps(market, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


def test_consistent_manifests_pass(tmp_path):
    repo = _make(tmp_path, disk=["jwb-a", "jwb-b"],
                 plugin_list=["jwb-a", "jwb-b"], market_list=["jwb-a", "jwb-b"],
                 plugin_desc="技能 2 个、命令 5 个", market_desc="2 skills")
    assert manifest_consistency_problems(repo) == []


def test_counts_may_be_omitted(tmp_path):
    """描述里不写数量是允许的（数量为可选）；写了就必须对。"""
    repo = _make(tmp_path, disk=["jwb-a"], plugin_list=["jwb-a"],
                 market_list=["jwb-a"])
    assert manifest_consistency_problems(repo) == []


def test_missing_skill_in_marketplace_is_flagged(tmp_path):
    """复现真实漂移形态：plugin.json 已加新技能、marketplace.json 停在旧的。"""
    repo = _make(tmp_path, disk=["jwb-a", "jwb-b"],
                 plugin_list=["jwb-a", "jwb-b"], market_list=["jwb-a"],
                 plugin_desc="技能 2 个", market_desc="2 skills")
    problems = manifest_consistency_problems(repo)
    assert any("marketplace.json" in p and "jwb-b" in p for p in problems), problems


def test_missing_skill_in_plugin_json_is_flagged(tmp_path):
    repo = _make(tmp_path, disk=["jwb-a", "jwb-b"],
                 plugin_list=["jwb-a"], market_list=["jwb-a", "jwb-b"])
    problems = manifest_consistency_problems(repo)
    assert any("plugin.json" in p and "jwb-b" in p for p in problems), problems


def test_count_mismatch_in_description_is_flagged(tmp_path):
    """集合一致、但描述数量没跟上（8 vs 9）——数量是派生值，同样要被抓。"""
    repo = _make(tmp_path, disk=["jwb-a", "jwb-b"],
                 plugin_list=["jwb-a", "jwb-b"], market_list=["jwb-a", "jwb-b"],
                 plugin_desc="技能 8 个", market_desc="2 skills")
    problems = manifest_consistency_problems(repo)
    assert any("plugin.json" in p and "8" in p for p in problems), problems


def test_count_mismatch_in_marketplace_plugin_desc_is_flagged(tmp_path):
    """marketplace 的 plugins[0].description 也在校验面内（两份描述都带数量）。"""
    repo = _make(tmp_path, disk=["jwb-a"],
                 plugin_list=["jwb-a"], market_list=["jwb-a"],
                 market_desc="8 skills", market_plugin_desc="技能包（9 个技能）")
    problems = manifest_consistency_problems(repo)
    assert any("marketplace.json" in p and "8" in p for p in problems), problems
    assert any("plugins[0]" in p and "9" in p for p in problems), problems


def test_broken_json_is_reported(tmp_path):
    (tmp_path / "skills" / "jwb-a").mkdir(parents=True)
    plugin_dir = tmp_path / ".codebuddy-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text("{ 坏", encoding="utf-8")
    (plugin_dir / "marketplace.json").write_text("{}", encoding="utf-8")
    problems = manifest_consistency_problems(str(tmp_path))
    assert problems and "plugin.json" in problems[0], problems
