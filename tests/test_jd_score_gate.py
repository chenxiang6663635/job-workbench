# -*- coding: utf-8 -*-
"""硬门槛结论判定的测试（此前是零覆盖盲区）。

评分放宽批（2026-09-24）：`[待填]` 不再按 fail 判死，新增第四态「待补档案」——
档案缺事实 ≠ 岗位不合格。判定词序：fail 优先（"不通过"含"通过"），
然后 pass，然后待补档案，其余待确认。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "packages", "jobws-core", "src"))

from jobws_core import jd_score  # noqa: E402


def _card(gate_line):
    """构造一张只含硬门槛小节的解析卡。"""
    return "## 硬门槛\n%s\n" % gate_line


def test_classify_gate_four_states():
    f = jd_score._classify_gate
    assert f("不通过：要求 2027 届，档案为 2026 届") == "不通过"
    assert f("未通过") == "不通过"
    assert f("通过") == "通过"
    assert f("全部满足，通过") == "通过"
    # 放宽批核心：档案缺事实不再是 fail，也不再与「待确认」混色
    assert f("待补档案（缺失字段: 学历、外语）") == "待补档案"
    assert f("待填") == "待补档案"
    assert f("待确认") == "待确认"
    assert f("") is None
    assert f(None) is None


def test_pending_card_does_not_kill():
    """`[待填]` 字段 → 结论「待补档案」：可解析、不判死，缺失字段可从卡片读出。"""
    card = _card(
        "学历: [待填]\n"
        "专业: 制冷及低温工程\n"
        "门槛结论: 待补档案（缺失字段: 学历）\n"
    )
    gates = jd_score.parse_hard_gates(card)
    assert gates["conclusion"] == "待补档案"
    assert gates["reason"] is None
    # 字段仍在 items 里，前端据此渲染「缺哪些字段」
    by_key = {it["key"]: it["value"] for it in gates["items"]}
    assert by_key["学历"] == "[待填]"
    assert by_key["专业"] == "制冷及低温工程"


def test_fail_card_still_terminates():
    """明确 fail 的既有行为钉死：不通过 + 原因保留。"""
    card = _card(
        "学历: 硕士\n"
        "门槛结论: 不通过\n"
        "不通过原因: 要求本地户籍，档案无本地户籍\n"
    )
    gates = jd_score.parse_hard_gates(card)
    assert gates["conclusion"] == "不通过"
    assert "本地户籍" in gates["reason"]


def test_pass_and_unconfirmed_unchanged():
    """回归：通过 / 待确认 / 空卡片的既有行为不变。"""
    assert jd_score.parse_hard_gates(
        _card("门槛结论: 通过\n"))["conclusion"] == "通过"
    assert jd_score.parse_hard_gates(
        _card("门槛结论: 待确认\n"))["conclusion"] == "待确认"
    assert jd_score.parse_hard_gates("## 评分\n技术匹配: 0/30\n")["conclusion"] is None


def test_parse_hard_gates_docstring_states_four_outcomes():
    """parse_hard_gates 的结论取值集合包含「待补档案」（消费方按此渲染）。"""
    doc = jd_score.parse_hard_gates.__doc__ or ""
    assert "待补档案" in doc
