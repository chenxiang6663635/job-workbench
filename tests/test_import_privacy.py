# -*- coding: utf-8 -*-
"""追踪表 CSV 导入的隐私与原子性（B4 / #4）——此前零测试。

导入是整条链路里最容易「悄悄写脏数据」的地方，钉住四件事：

1. **预览不落盘**：用户只是想看看差异表，预览阶段任何文件都不该出现；
2. **原子写不留垃圾**：写完不能留下 `.jobws_tmp_` 半成品；
3. **可溯源**：提交后时间线里要有「创建」条目，写清公司与岗位；
4. **冲突整批拒绝**：预览之后又冒出同键记录时一行都不写（返回 -1）。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import tracker  # noqa: E402

WS = "ws-ok"
TRACKING = "05_投递追踪"
CSV_TEXT = (
    "公司,岗位,方向,批次,当前阶段\n"
    "公司A,岗位甲,hvac,正式批,已投\n"
    "公司B,岗位乙,datacenter,正式批,一面\n"
)


def _ws(tmp_path):
    return str(tmp_path / WS)


def _tracking_dir(tmp_path):
    return os.path.join(_ws(tmp_path), TRACKING)


def _preview(ws, existing=None):
    rows, _unknown = tracker.parse_import_csv(CSV_TEXT)
    return tracker.preview_import(rows, existing if existing is not None else [], ws)


def _write_rows(tmp_path, rows):
    full = []
    for row in rows:
        record = {f: "" for f in tracker.FIELDS}
        record.update(row)
        full.append(record)
    tracker.write_rows(full, _ws(tmp_path))


def test_preview_writes_nothing(tmp_path):
    """预览只是给人看差异，一个字节都不该落盘。"""
    ws = _ws(tmp_path)
    preview = _preview(ws)
    assert [i["line"] for i in preview["ok"]] == [2, 3]
    assert not os.path.isdir(_tracking_dir(tmp_path))


def test_commit_leaves_no_temp_files(tmp_path):
    """原子写（tmp + os.replace）不能留下半成品。"""
    ws = _ws(tmp_path)
    assert tracker.commit_import(_preview(ws), ws) == 2
    leftovers = [name for name in os.listdir(_tracking_dir(tmp_path))
                 if name.startswith(tracker.TMP_PREFIX)]
    assert leftovers == []


def test_commit_is_traceable_in_history(tmp_path):
    """提交即入账：事后能回答「这两行是谁什么时候进来的」。"""
    ws = _ws(tmp_path)
    assert tracker.commit_import(_preview(ws), ws) == 2
    history = tracker.read_history(ws)
    assert len(history) == 2
    assert [h["字段"] for h in history] == ["创建", "创建"]
    assert "公司A" in history[0]["新值"]
    assert "岗位甲" in history[0]["新值"]


def test_conflict_after_preview_rejects_whole_batch(tmp_path):
    """预览到提交之间主表变了 → 整批拒绝，绝不允许半批写入。"""
    ws = _ws(tmp_path)
    preview = _preview(ws)
    # 手工抢先加了一条同键记录
    _write_rows(tmp_path, [{"id": "A001", "公司": "公司A", "岗位": "岗位甲",
                            "当前阶段": "已投"}])
    assert tracker.commit_import(preview, ws) == -1
    assert len(tracker.read_rows(ws)) == 1


@pytest.mark.parametrize("missing", ["公司", "岗位"])
def test_rows_without_company_or_role_are_errors(tmp_path, missing):
    """公司或岗位缺一不可——缺了就是 error，不是悄悄写个空值进去。"""
    ws = _ws(tmp_path)
    rows, _unknown = tracker.parse_import_csv("公司,岗位\n%s\n" % (
        "只有一家" if missing == "岗位" else ",只有岗位"))
    preview = tracker.preview_import(rows, [], ws)
    assert preview["ok"] == []
    assert preview["error"], "缺关键列的行必须落到 error 桶，而不是被静默丢弃"
