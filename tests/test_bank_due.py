# -*- coding: utf-8 -*-
"""`jobws bank due`：今日待复习的间隔阶梯与保守规则。

规则写死在 `question_review.REVIEW_INTERVALS`：未看恒在；看过 3 天 / 会了 14 天；
`最近复习` 为空 / 脏 / 状态未知一律待复习（宁可多提醒，不静默漏）。
领域层用例注入固定日期（不随机器时间漂移）；CLI 用例用相对今天构造数据。
"""

import csv
import datetime
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import _cli_bank  # noqa: E402
from jobws_core import question_review  # noqa: E402
from jobws_core import tracker  # noqa: E402

TODAY = "2026-09-19"          # 领域层用例的固定"今天"
TODAY_ISO = datetime.date.today().isoformat()  # CLI 用例用真实今天（不漂移）


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "ws" / "05_投递追踪").mkdir(parents=True)
    return tmp_path / "ws"


def _seed(ws, questions):
    """questions: [(题目, 状态, 最近复习), ...]"""
    fields = list(tracker.QUESTION_FIELDS)
    path = ws / "05_投递追踪" / "questions.csv"
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (title, status, last) in enumerate(questions, start=1):
            row = dict((f, "") for f in fields)
            row.update({"题目id": "Q%03d" % index, "题目": title, "状态": status,
                        "最近复习": last, "领域": "技术面", "科目": "网络"})
            writer.writerow(row)
    return path


def _titles(items):
    return [row["题目"] for row, _reason in items]


# --- 规则 -------------------------------------------------------------------


def test_unseen_is_always_due(ws):
    _seed(ws, [("没学过", "未看", "")])
    items = question_review.due_questions(str(ws), today=TODAY)
    assert _titles(items) == ["没学过"]
    assert "未看" in items[0][1]


def test_seen_interval_boundary_is_inclusive(ws):
    _seed(ws, [
        ("刚好到期", "看过", "2026-09-16"),   # +3 = 今天（含今天）
        ("还没到期", "看过", "2026-09-17"),   # +3 = 明天
    ])
    items = question_review.due_questions(str(ws), today=TODAY)
    assert _titles(items) == ["刚好到期"]
    assert items[0][1] == "已到期"


def test_known_interval_is_two_weeks(ws):
    _seed(ws, [
        ("会了到期", "会了", "2026-09-05"),   # +14 = 今天
        ("会了未到期", "会了", "2026-09-06"),  # +14 = 明天
    ])
    assert _titles(question_review.due_questions(str(ws), today=TODAY)) == ["会了到期"]


def test_overdue_days_in_reason(ws):
    _seed(ws, [("拖了六天", "看过", "2026-09-10")])   # +3 = 09-13
    items = question_review.due_questions(str(ws), today=TODAY)
    assert items[0][1] == "已到期 6 天"


def test_last_reviewed_today_is_not_due(ws):
    _seed(ws, [("刚看过", "看过", "2026-09-19")])
    assert question_review.due_questions(str(ws), today=TODAY) == []


# --- 保守规则（宁可多提醒）--------------------------------------------------


def test_never_reviewed_when_last_empty(ws):
    _seed(ws, [("看过但没记录", "看过", "")])
    items = question_review.due_questions(str(ws), today=TODAY)
    assert items[0][1] == "从没复习过"


def test_dirty_date_counts_as_due(ws):
    _seed(ws, [("脏日期", "看过", "上周二")])
    items = question_review.due_questions(str(ws), today=TODAY)
    assert "不是日期" in items[0][1]


def test_unknown_status_counts_as_due(ws):
    _seed(ws, [("脏状态", "背过了", "2026-09-18")])
    items = question_review.due_questions(str(ws), today=TODAY)
    assert _titles(items) == ["脏状态"]
    assert "状态无法识别" in items[0][1]


# --- 排序 -------------------------------------------------------------------


def test_never_reviewed_sorts_first(ws):
    _seed(ws, [
        ("有日期的", "看过", "2026-09-10"),
        ("没记录的", "看过", ""),
    ])
    assert _titles(question_review.due_questions(str(ws), today=TODAY)) == [
        "没记录的", "有日期的"]


# --- CLI --------------------------------------------------------------------


def test_cli_due_prints_table_and_count(ws, capsys):
    _seed(ws, [("没学过", "未看", ""), ("刚看过", "看过", TODAY_ISO)])
    assert _cli_bank.main(["due", "--workspace", str(ws)]) == 0
    out = capsys.readouterr().out
    assert "没学过" in out and "刚看过" not in out
    assert "共 1 道待复习" in out


def test_cli_due_empty_state(ws, capsys):
    _seed(ws, [("刚看过", "看过", TODAY_ISO)])
    assert _cli_bank.main(["due", "--workspace", str(ws)]) == 0
    assert "今日没有待复习的题" in capsys.readouterr().out
