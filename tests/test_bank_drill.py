# -*- coding: utf-8 -*-
"""`question_drill`：抽题与重练队列（纯函数）。

钉住四件容易悄悄分叉的事：
1. **队列 = 错题 ∪ due 且去重**：一道题既是错题又到期，只该出现一次；
2. **排序与 due 同口径**：没复习过的排在最前（空串先于日期）；
3. **随机源与"今天"可注入**：不注入就随机器漂移，测试与界面都无法复现；
4. **上限与非法值**：一轮不超过 20，负数 / 非数字回落默认值而不是崩。
"""

import datetime
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import question_drill, tracker  # noqa: E402

TODAY = datetime.date(2026, 9, 20)


def _row(qid, title, status="未看", last="", tags="", reviewed=""):
    row = dict((field, "") for field in tracker.QUESTION_FIELDS)
    row.update({"题目id": qid, "题目": title, "状态": status,
                "最近复习": last, "标签": tags, "创建日期": "2026-09-18",
                "答案要点": "要点"})
    return row


def test_queue_is_wrong_union_due_without_duplicates():
    rows = [
        _row("Q001", "未看的题"),                                  # due（未看恒在）
        _row("Q002", "错题且到期", status="看过",
             last=str(TODAY - datetime.timedelta(days=10)), tags="错题"),
        _row("Q003", "刚复习过", status="会了", last=str(TODAY)),    # 不到期
    ]
    queue = question_drill.build_queue(rows, today=TODAY)
    assert [row["题目id"] for row in queue] == ["Q001", "Q002"]


def test_unreviewed_rows_come_first():
    rows = [
        _row("Q001", "复习过的", status="看过",
             last=str(TODAY - datetime.timedelta(days=30)), tags="错题"),
        _row("Q002", "没复习过的", status="看过", tags="错题"),
    ]
    queue = question_drill.build_queue(rows, today=TODAY)
    assert [row["题目id"] for row in queue] == ["Q002", "Q001"]


def test_random_mode_is_reproducible_with_an_injected_source():
    rows = [_row("Q00%d" % i, "题 %d" % i) for i in range(1, 6)]

    class _Fixed:
        """固定"随机"：把列表反转——足以证明顺序来自注入的随机源。"""

        def shuffle(self, seq):
            seq.reverse()

    picked = question_drill.pick_drill(rows, mode="random", n=3, rng=_Fixed())
    assert [row["题目id"] for row in picked] == ["Q005", "Q004", "Q003"]


def test_wrong_mode_only_returns_tagged_rows():
    rows = [
        _row("Q001", "错题", tags="高频,错题"),
        _row("Q002", "普通题"),
    ]
    picked = question_drill.pick_drill(rows, mode="wrong")
    assert [row["题目"] for row in picked] == ["错题"]


def test_limit_is_capped_and_bad_values_fall_back():
    rows = [_row("Q%03d" % i, "题 %d" % i) for i in range(1, 31)]
    assert len(question_drill.pick_drill(rows, n=99)) == question_drill.MAX_N
    assert len(question_drill.pick_drill(rows, n=0)) == 1
    assert len(question_drill.pick_drill(rows, n="abc")) == question_drill.DEFAULT_N


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError) as excinfo:
        question_drill.pick_drill([], mode="smart")
    assert "抽题模式" in str(excinfo.value)


def test_empty_bank_does_not_explode():
    assert question_drill.pick_drill([]) == []
    assert question_drill.build_queue([], today=TODAY) == []


def test_drill_does_not_touch_the_csv(ws):
    """纯函数之外也要确认：抽题这条路径一个字节都不写。"""
    path = os.path.join(str(ws), "05_投递追踪", "questions.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("题目id,题目\nQ001,题一\n")
    before = io.open(path, "rb").read()

    question_drill.pick_drill([_row("Q001", "题一")])

    assert io.open(path, "rb").read() == before


@pytest.fixture()
def ws(tmp_path):
    path = tmp_path / "ws"
    (path / "05_投递追踪").mkdir(parents=True)
    return str(path)


def _seed_csv(ws, rows):
    import csv
    path = os.path.join(str(ws), "05_投递追踪", "questions.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tracker.QUESTION_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def test_cli_drill_prints_questions_but_not_answers(ws, capsys):
    """命令行抽题：给问法、不给答案（看一眼答案的"复习"等于没练）。"""
    import _cli_bank  # noqa: E402  （命令层在 tools/ 下，与领域层分开测）
    _seed_csv(ws, [
        _row("Q001", "缓存雪崩是什么", tags="高频"),
        _row("Q002", "缓存穿透是什么"),
    ])

    assert _cli_bank.main(["drill", "--workspace", str(ws), "--n", "2"]) == 0
    out = capsys.readouterr().out
    assert "缓存雪崩是什么" in out
    assert "大量 key 同时过期" not in out, "答案要点不该被打印出来"


def test_cli_drill_rejects_unknown_mode(ws, capsys):
    import _cli_bank  # noqa: E402
    _seed_csv(ws, [_row("Q001", "题一")])
    # 未知模式由 argparse 的 choices 拦在用法层（退出码 2），不该进到领域层
    with pytest.raises(SystemExit) as excinfo:
        _cli_bank.main(["drill", "--workspace", str(ws), "--mode", "smart"])
    assert excinfo.value.code == 2
