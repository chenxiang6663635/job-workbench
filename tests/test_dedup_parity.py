# -*- coding: utf-8 -*-
"""重复实现收编的同源网（2026-10-09 桶二·收编批）。

三组「同一规则两份实现」收编后，本文件把**同源性**钉住（行为 + 源码双面，
手法沿用 `test_resume_tmp_prefix` 与 `test_containment`）：

1. **非法路径片段**：Web `deps.safe_join` 与 `containment.escape_reason` 的分类一致
   （绝对 / `..` / 盘符相对）。平台差异是**有意**的——posix 上反斜杠是普通字符
   （`test_prep_api` 钉住的既有语义），跨平台严格版在 MCP 侧（见 `mcp/tests/`）。
   盘符相对在 Windows 上是真漏洞：`isabs()` 为 False、`join` 却把根重置到盘根。
2. **CSV 读取**：`restore_row(dict(row))` 这条读取模式只允许在 `csv_cells` 出现
   一处——主表 / 时间线 / 题库三处都走它（编码与还原口径只该有一份）。
3. **严格 ISO 日期**：唯一实现是 `tracker.parse_iso_date`；
   `question_review` 不再自带私有正则副本（脏值语义：解析不出 → 保守处理）。
"""
import io
import os
import sys
from datetime import date

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from apierror import ApiError  # noqa: E402
from jobws_core import containment  # noqa: E402
from jobws_core import csv_cells  # noqa: E402
from jobws_core import question_review  # noqa: E402
from jobws_core import tracker  # noqa: E402


def _read(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# --- 1. 非法路径片段：Web 侧的分类 ---------------------------------------------

@pytest.mark.parametrize("bad", ["../x", "..", "a/../../b", "/etc/passwd"])
def test_safe_join_rejects_traversal_as_illegal_segment(tmp_path, bad):
    with pytest.raises(ApiError) as ei:
        deps.safe_join(str(tmp_path), bad)
    assert ei.value.code == "path.illegalSegment", bad


@pytest.mark.skipif(os.name != "nt", reason="盘符相对只在 Windows 上重置 join 的根")
def test_safe_join_rejects_drive_relative_on_windows(tmp_path):
    """`C:foo`：`isabs()` 为 False、`join` 时却把根重置到 C 盘。

    此前段检查漏它 → 落到归属判定：偶然得 `path.escape`（分类错），
    若进程 CWD 恰在工作区内则**直接放行**并返回相对路径（静默走错）。
    """
    with pytest.raises(ApiError) as ei:
        deps.safe_join(str(tmp_path), "C:foo")
    assert ei.value.code == "path.illegalSegment"


@pytest.mark.skipif(os.name != "posix", reason="posix 上 `C:foo` 是普通文件名（有意差异）")
def test_safe_join_accepts_drive_like_name_on_posix(tmp_path):
    """平台语义差异的显式化：posix 上它只是一个名字，不该被跨平台严格版误伤。"""
    assert deps.safe_join(str(tmp_path), "C:foo").endswith("C:foo")


def test_safe_join_and_escape_reason_agree_on_the_shared_classes():
    """两侧共享的三类（绝对 / .. / 盘符）判定必须同源——同义输入不得分叉。"""
    for bad in ("../x", "/etc/passwd", ".."):
        assert containment.escape_reason(bad), bad
        with pytest.raises(ApiError):
            deps.safe_join(os.getcwd(), bad)


# --- 2. CSV 读取：唯一模式 -----------------------------------------------------

def test_table_readers_no_longer_carry_their_own_copy():
    """八张表的读取入口都不许再留自己的副本（读取模式唯一实现在 csv_cells）。

    `tracker/_history.py` 不在清单里：它按**字节**截尾容错、逐行判结构，输入是
    文本而不是路径——它用的是共享原语 `restore_row`，不是重复的读模式。
    （`packages/*/build/` 是 pip 构建产物、已被 .gitignore 覆盖，不参与判定。）
    """
    sites = [
        "packages/jobws-core/src/jobws_core/tracker/_core.py",
        "packages/jobws-core/src/jobws_core/tracker/applications.py",
        "packages/jobws-core/src/jobws_core/tracker/contacts.py",
        "packages/jobws-core/src/jobws_core/tracker/interviews.py",
        "packages/jobws-core/src/jobws_core/tracker/mails.py",
        "packages/jobws-core/src/jobws_core/tracker/offers.py",
        "packages/jobws-core/src/jobws_core/tracker/talks.py",
        "packages/jobws-core/src/jobws_core/question_bank.py",
    ]
    leftovers = [rel for rel in sites
                 if "restore_row(dict(row))" in _read(os.path.join(ROOT_DIR, rel))]
    assert leftovers == [], leftovers


def test_csv_cells_reader_round_trips_neutralized_cells(tmp_path):
    """共享读取器：写入侧中和过的引号还原、BOM 剥离——写进去什么、读出来什么。"""
    path = str(tmp_path / "t.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("id,备注\n")
        fh.write("%s,%s\n" % (csv_cells.csv_cell("A1"), csv_cells.csv_cell("=SUM(1)")))

    rows = csv_cells.read_rows(path)

    assert rows == [{"id": "A1", "备注": "=SUM(1)"}]


def test_main_table_read_goes_through_the_shared_reader(tmp_path, monkeypatch):
    """主表读取（tracker.read_rows）必须走共享读取器——不是自己再拼一遍。"""
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    tracker.write_rows([{"id": "A1", "公司": "云帆", "岗位": "后端", "备注": "=SUM(1)"}], ws)

    calls = {"n": 0}
    real = csv_cells.read_rows

    def counting(path):
        calls["n"] += 1
        return real(path)

    from jobws_core.tracker import applications
    monkeypatch.setattr(applications, "read_csv_rows", counting)

    rows = tracker.read_rows(ws)

    assert rows[0]["备注"] == "=SUM(1)" and calls["n"] == 1


# --- 3. 严格 ISO 日期：唯一实现 ------------------------------------------------

def test_question_review_has_no_private_date_parser():
    """收编后 `question_review` 不再自带 ISO 正则副本（判定交给 tracker）。"""
    assert not hasattr(question_review, "_DATE_RE")
    assert question_review.parse_iso_date is tracker.parse_iso_date


def test_question_review_dirty_date_matches_tracker_semantics():
    """脏日期（形状对但不是真日期）→ 解析不出 → 保守视为待复习（宁可多提醒）。"""
    assert tracker.parse_iso_date("2026-02-31") is None
    rows = [{"题目": "脏日期题", "状态": "会了", "最近复习": "2026-02-31"}]

    due = question_review.due_from_rows(rows, today=date(2026, 10, 9))

    assert [row["题目"] for row, _why in due] == ["脏日期题"]
