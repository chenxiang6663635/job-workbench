# -*- coding: utf-8 -*-
"""投递健康度 health_score 的锁死测试。

健康度是「给理由不给黑箱分数」的判定：level 四态 + 每条 reasons 都必须
能被用户核对。这里把四态语义与终态豁免锁死，防止日后有人把它改成
算分制或把终态也拉进来报「停滞」。
"""

import os
import sys

from datetime import date, timedelta

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools")
sys.path.insert(0, TOOLS)

import tracker  # noqa: E402

TODAY = date(2026, 9, 6)


def _row(**kw):
    row = {f: "" for f in tracker.FIELDS}
    row.update({"id": "A001", "当前阶段": "待投"})
    row.update(kw)
    return row


def _score(row, entries=None):
    return tracker.health_score(row, entries or [], today=TODAY)


def test_terminal_stage_not_scored():
    for stage in tracker.TERMINAL_STAGES:
        h = _score(_row(当前阶段=stage))
        assert h["level"] is None, "终态 %s 不应参与判定" % stage
        assert h["reasons"] == []


def test_urgent_when_deadline_within_three_days():
    row = _row(截止日期=str(TODAY + timedelta(days=3)))
    h = _score(row)
    assert h["level"] == "urgent"
    assert any("距截止日 3 天" in r for r in h["reasons"])


def test_urgent_when_deadline_is_today():
    h = _score(_row(截止日期=str(TODAY)))
    assert h["level"] == "urgent"
    assert any("今天就是截止日" in r for r in h["reasons"])


def test_urgent_when_deadline_passed_but_not_applied():
    row = _row(截止日期=str(TODAY - timedelta(days=5)))
    h = _score(row)
    assert h["level"] == "urgent"
    assert any("已过截止日 5 天" in r for r in h["reasons"])


def test_not_urgent_when_deadline_far():
    row = _row(截止日期=str(TODAY + timedelta(days=10)))
    assert _score(row)["level"] == "ok"


def test_not_urgent_after_applied():
    # 已投的不看截止日紧急度（截止日是投递闸门，投了就翻篇）
    row = _row(当前阶段="已投", 截止日期=str(TODAY - timedelta(days=2)),
               投递日期=str(TODAY - timedelta(days=3)))
    assert _score(row)["level"] == "ok"


def test_overdue_next_action():
    row = _row(当前阶段="已投", 下次动作="跟进 HR", 下次动作日期=str(TODAY - timedelta(days=2)))
    h = _score(row)
    assert h["level"] == "overdue"
    assert any("已逾期 2 天" in r and "跟进 HR" in r for r in h["reasons"])


def test_stale_when_stage_days_over_threshold():
    # 无阶段变更历史时以投递日期为基准（见 stage_base_date 的回退规则）
    row = _row(当前阶段="已投", 投递日期=str(TODAY - timedelta(days=tracker.STALE_DAYS + 1)))
    h = _score(row)
    assert h["level"] == "stale"
    assert any("停留 %d 天" % (tracker.STALE_DAYS + 1) in r for r in h["reasons"])


def test_reasons_collect_all_hits_level_takes_worst():
    # 截止日 2 天后 + 下次动作已逾期 + 阶段久停：三条理由全收，level 取最严重
    row = _row(截止日期=str(TODAY + timedelta(days=2)),
               下次动作="改简历", 下次动作日期=str(TODAY - timedelta(days=1)),
               投递日期=str(TODAY - timedelta(days=tracker.STALE_DAYS + 3)))
    h = _score(row)
    assert h["level"] == "urgent"
    assert len(h["reasons"]) == 3, "三条理由都应给出：%s" % h["reasons"]


def test_ok_when_nothing_wrong():
    row = _row(当前阶段="已投", 投递日期=str(TODAY - timedelta(days=5)),
               下次动作日期=str(TODAY + timedelta(days=5)))
    h = _score(row)
    assert h["level"] == "ok"
    assert h["reasons"] == []
