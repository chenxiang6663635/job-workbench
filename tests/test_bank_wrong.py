# -*- coding: utf-8 -*-
"""`jobws bank wrong`：错题本（标签方案）。

设计要点：错题 = 标签里含「错题」的题（**零 schema 变更**，标签本就是分类位）；
标记动作**复用 `question.update` 的两段式**（不新增写操作）——本文件同时钉住
「重算标签串」的细节：追加、分隔符归一（中文顿号/逗号 → 英文逗号）、移除时
保留其余标签、无变化 / 找不到 id 的明确报错。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import _cli_bank  # noqa: E402
from jobws_core import approval  # noqa: E402
from jobws_core import question_bank  # noqa: E402
from jobws_core import question_review  # noqa: E402
from jobws_core import tracker  # noqa: E402


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "ws" / "05_投递追踪").mkdir(parents=True)
    return tmp_path / "ws"


def _seed(ws, rows):
    path = ws / "05_投递追踪" / "questions.csv"
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tracker.QUESTION_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _question(qid, title, tags=""):
    row = dict((f, "") for f in tracker.QUESTION_FIELDS)
    row.update({"题目id": qid, "题目": title, "标签": tags, "状态": "未看",
                "领域": "技术面", "科目": "网络"})
    return row


def _apply(plan, ws):
    result = approval.preview("question.update", str(ws), plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    return approval.apply(result["token"])


def _tags_of(ws, qid):
    row = question_bank.find_question(question_bank.read_questions(str(ws)), qid)
    return row["标签"]


# --- 列表视图 ---------------------------------------------------------------


def test_wrong_questions_filters_by_tag(ws):
    _seed(ws, [
        _question("Q001", "错题甲", "网络基础,错题"),
        _question("Q002", "普通题", "网络基础"),
        _question("Q003", "错题乙", "错题"),
    ])
    titles = [r["题目"] for r in question_review.wrong_questions(str(ws))]
    # 不依赖中文码点的排序直觉：只钉「选了哪些、没选哪些」
    assert sorted(titles) == sorted(["错题甲", "错题乙"])
    assert "普通题" not in titles


def test_split_tags_tolerates_separators():
    assert question_review.split_tags("a、b，c;d e") == ["a", "b", "c", "d", "e"]
    assert question_review.split_tags("") == []


# --- 标记（复用 update 两段式）----------------------------------------------


def test_mark_appends_tag_and_writes(ws):
    _seed(ws, [_question("Q001", "一题", "网络基础")])
    errors, plan = question_review.preview_mark_wrong("Q001", True, str(ws))
    assert errors == []
    assert _tags_of(ws, "Q001") == "网络基础"  # 预览不落盘

    _apply(plan, ws)

    assert _tags_of(ws, "Q001") == "网络基础,错题"
    assert [r["题目"] for r in question_review.wrong_questions(str(ws))] == ["一题"]


def test_mark_normalizes_separators(ws):
    _seed(ws, [_question("Q001", "一题", "a、b")])
    errors, plan = question_review.preview_mark_wrong("Q001", True, str(ws))
    assert errors == []
    _apply(plan, ws)
    assert _tags_of(ws, "Q001") == "a,b,错题"


def test_mark_remove_keeps_other_tags(ws):
    _seed(ws, [_question("Q001", "一题", "错题,高频")])
    errors, plan = question_review.preview_mark_wrong("Q001", False, str(ws))
    assert errors == []
    _apply(plan, ws)
    assert question_review.wrong_questions(str(ws)) == []
    assert _tags_of(ws, "Q001") == "高频"


def test_mark_no_change_cases(ws):
    _seed(ws, [_question("Q001", "已标", "错题"), _question("Q002", "未标", "")])
    errors, plan = question_review.preview_mark_wrong("Q001", True, str(ws))
    assert plan is None and any("本来就有" in e for e in errors)
    errors, plan = question_review.preview_mark_wrong("Q002", False, str(ws))
    assert plan is None and any("不在错题本" in e for e in errors)


def test_mark_unknown_id_and_missing_id(ws):
    _seed(ws, [])
    errors, plan = question_review.preview_mark_wrong("Q999", True, str(ws))
    assert plan is None and any("找不到" in e for e in errors)
    errors, plan = question_review.preview_mark_wrong("", True, str(ws))
    assert plan is None and any("缺少题目 id" in e for e in errors)


# --- CLI --------------------------------------------------------------------


def test_cli_wrong_lists(ws, capsys):
    _seed(ws, [_question("Q001", "错题甲", "错题")])
    assert _cli_bank.main(["wrong", "--workspace", str(ws)]) == 0
    out = capsys.readouterr().out
    assert "错题甲" in out and "共 1 道错题" in out


def test_cli_wrong_empty(ws, capsys):
    _seed(ws, [])
    assert _cli_bank.main(["wrong", "--workspace", str(ws)]) == 0
    assert "错题本为空" in capsys.readouterr().out


def test_cli_wrong_add_previews_token_without_writing(ws, capsys):
    _seed(ws, [_question("Q001", "一题", "")])
    assert _cli_bank.main(["wrong", "--add", "Q001", "--workspace", str(ws)]) == 0
    out = capsys.readouterr().out
    assert "确认后落盘" in out and "错题" in out
    assert question_review.wrong_questions(str(ws)) == []  # 预览一个字节不写


def test_cli_wrong_add_and_remove_conflict(ws, capsys):
    _seed(ws, [_question("Q001", "一题", "")])
    code = _cli_bank.main(["wrong", "--add", "Q001", "--remove", "Q001",
                           "--workspace", str(ws)])
    assert code == 2
    assert "只能给一个" in capsys.readouterr().out
