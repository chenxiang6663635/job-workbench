# -*- coding: utf-8 -*-
"""`jobws bank delete`：给"导入"装上刹车（2026-09-20）。

钉住五件事：
1. **预览不落盘**：预览后 `questions.csv` 一个字节都没变（按 bytes 断言）；
2. **匹配 0 题报错误**：空转等于骗人（"删除 0 道题"这种预览不该到人眼前）；
3. **留痕落在工作区之外**：删之前整表快照写走，且快照目录**不在工作区内**——
   与被删对象同处一地的留痕会被同一次误操作一起抹掉；
4. **预览后目标消失就整体拒绝**：不许删一半（删一半比什么都不做更难解释）；
5. **--id 与筛选条件互斥**：两条路各走各的，混着给是用法错误。
"""

import csv
import datetime
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import question_delete, tracker  # noqa: E402
from jobws_core.question_bank import read_questions  # noqa: E402

TODAY = datetime.date.today().isoformat()


@pytest.fixture()
def ws(tmp_path):
    path = tmp_path / "ws"
    (path / "05_投递追踪").mkdir(parents=True)
    return str(path)


@pytest.fixture()
def outside(tmp_path, monkeypatch):
    """把留痕根钉到临时目录：既不污染真实快照区，又能断言"在工作区之外"。"""
    root = tmp_path / "snapshots"
    monkeypatch.setattr(question_delete.pathres, "snapshot_root",
                        lambda: str(root))
    return str(root)


def _seed(ws, questions):
    """questions: [(题目, 领域, 科目, 来源, 创建日期), ...]"""
    fields = list(tracker.QUESTION_FIELDS)
    path = os.path.join(ws, "05_投递追踪", "questions.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (title, domain, subject, origin, created) in enumerate(questions, start=1):
            row = dict((f, "") for f in fields)
            row.update({"题目id": "Q%03d" % index, "题目": title, "领域": domain,
                        "科目": subject, "来源": origin, "创建日期": created,
                        "状态": "未看"})
            writer.writerow(row)
    return path


def _bytes(path):
    with io.open(path, "rb") as handle:
        return handle.read()


def test_preview_does_not_touch_the_csv(ws):
    path = _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    before = _bytes(path)
    errors, plan = question_delete.preview_delete_fields("Q001", None, ws)
    assert errors == []
    assert plan["payload"]["ids"] == ["Q001"]
    assert _bytes(path) == before


def test_single_delete_removes_only_that_row(ws, outside):
    _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY),
               ("UDP", "技术面", "网络", "自拟", TODAY)])
    result = question_delete.apply_approved_delete({"ids": ["Q001"]}, ws)
    assert result["written"] == 1
    assert [row["题目"] for row in read_questions(ws)] == ["UDP"]


def test_bulk_undo_filters_todays_imports(ws, outside):
    _seed(ws, [("今天导入的题", "技术面", "网络", "导入", TODAY),
               ("上个月自拟的题", "技术面", "网络", "自拟", "2026-08-01")])
    errors, plan = question_delete.preview_delete_fields(
        None, {"来源": "导入", "今天创建": "1"}, ws)
    assert errors == []
    assert plan["payload"]["ids"] == ["Q001"]


def test_zero_match_is_an_error_not_a_silent_noop(ws):
    _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    errors, plan = question_delete.preview_delete_fields(None, {"领域": "行为面"}, ws)
    assert plan is None
    assert any("没有符合筛选条件" in e for e in errors)


def test_trace_is_a_full_snapshot_and_lives_outside_the_workspace(ws, outside):
    path = _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    _errors, plan = question_delete.preview_delete_fields("Q001", None, ws)
    result = question_delete.apply_approved_delete(plan["payload"], ws)

    trace = result["trace"]
    assert os.path.isfile(trace)
    assert os.path.abspath(trace).startswith(os.path.abspath(outside) + os.sep)
    assert not os.path.abspath(trace).startswith(os.path.abspath(ws) + os.sep)
    # 快照是"删之前"的整表：被删的那道还在里面，恢复 = 整份拷回 questions.csv
    with io.open(trace, "r", encoding="utf-8-sig", newline="") as handle:
        assert [row["题目"] for row in csv.DictReader(handle)] == ["TCP"]
    assert "TCP" not in _bytes(path).decode("utf-8-sig")


def test_refuses_whole_delete_when_a_target_vanished(ws, outside):
    _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    with pytest.raises(tracker.ConflictError) as excinfo:
        question_delete.apply_approved_delete({"ids": ["Q999"]}, ws)
    assert "预览之后" in str(excinfo.value)
    assert len(read_questions(ws)) == 1


def test_id_and_filters_are_mutually_exclusive(ws):
    _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    errors, plan = question_delete.preview_delete_fields("Q001", {"领域": "技术面"}, ws)
    assert plan is None
    assert any("一次只能给" in e for e in errors)


def test_missing_both_is_a_usage_error(ws):
    _seed(ws, [("TCP", "技术面", "网络", "导入", TODAY)])
    errors, plan = question_delete.preview_delete_fields(None, None, ws)
    assert plan is None
    assert any("缺少题目 id" in e for e in errors)
