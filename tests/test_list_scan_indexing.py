# -*- coding: utf-8 -*-
"""列表 / 看板的时间线扫描治理（P 批，2026-09-21）：索引化 + 结构回归网。

体检缺口：`applications.py` 列表与 `dashboard.py` 的静态/待推进两块，此前
**每行各自全量遍历一次时间线**（O(行数 × 条目数)）。治理方式：领域层新增
`tracker.history_by_id(entries)` 归组一次，逐行传「该 id 的子集」。

本文件钉四件事：
1. **归组语义**：history_by_id 按键归组、保序、strip 后归类；
2. **等价性**：子集扫描与全量扫描在 stale_days / health_score / stage_base_date
   下结果逐一相等（这是替换成立的前提，不是抽样）；
3. **结构**：列表端点整表只读一次时间线，且每一行只收到**自己 id** 的条目
   （防止「读了 1 次但仍逐行传全量」这种半吊子回归）；
4. **端到端对账**：两个端点返回的 stageDays / health / stale / pending 与
   领域函数在同一份数据上的计算结果一致，且夹具确实造出了待判定记录
   （空集断言是假绿——夹具退化时这条会先响）。
"""

import csv
import io
import json
import os
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import tracker  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _row(app_id, stage, **extra):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": app_id, "公司": "云帆", "岗位": "后端",
                "方向": "backend", "批次": "正式批", "当前阶段": stage})
    row.update(extra)
    return row


def _write_history(ws_dir, entries):
    """直写时间线 CSV——`append_history` 会强制盖写「时间」为当下，
    造不出「20 天前的阶段变更」这类历史夹具。"""
    path = tracker.history_path(ws_dir)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.HISTORY_FIELDS,
                                extrasaction="ignore", restval="")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def _seed(ws_dir):
    """四行四态：A001 逾期（urgent）/ A002 静默（投递日期已老，无时间线）/
    A003 静默（阶段变更在 20 天前）/ A004 终态（两处都不参与）。"""
    today = date.today()
    tracker.write_rows([
        _row("A001", "待投",
             截止日期=(today - timedelta(days=1)).isoformat(),
             投递日期=(today - timedelta(days=10)).isoformat()),
        _row("A002", "已投", 投递日期=(today - timedelta(days=30)).isoformat()),
        _row("A003", "已投", 投递日期=today.isoformat()),
        _row("A004", "已挂", 投递日期=today.isoformat()),
    ], ws_dir)
    _write_history(ws_dir, [
        {"时间": (today - timedelta(days=20)).isoformat() + " 10:00",
         "id": "A003", "字段": "当前阶段", "原值": "待投", "新值": "已投"},
        {"时间": (today - timedelta(days=5)).isoformat() + " 10:00",
         "id": "A001", "字段": "备注", "原值": "", "新值": "跟进过"},
    ])


# --- 1. 归组语义 ----------------------------------------------------------------

def test_history_by_id_groups_and_strips():
    entries = [
        {"id": "A001", "字段": "a"},
        {"id": "A002", "字段": "b"},
        {"id": "A001", "字段": "c"},
        {"字段": "d"},                     # 无 id：归到空键
        {"id": "  A002  ", "字段": "e"},   # 带空白：strip 后归类
    ]
    grouped = tracker.history_by_id(entries)
    assert [e["字段"] for e in grouped["A001"]] == ["a", "c"]
    assert [e["字段"] for e in grouped["A002"]] == ["b", "e"]
    assert [e["字段"] for e in grouped[""]] == ["d"]


def test_history_by_id_sees_whitespace_row_id_like_domain(tmp_path):
    """行 id 带空白时，归组键与领域函数对「同一记录」的判定必须一致。"""
    ws_dir = str(tmp_path / "ws")
    os.makedirs(ws_dir)
    today = date.today()
    tracker.write_rows([_row(" A001 ", "已投",
                             投递日期=(today - timedelta(days=30)).isoformat())],
                       ws_dir)
    _write_history(ws_dir, [
        {"时间": (today - timedelta(days=9)).isoformat() + " 10:00",
         "id": "A001", "字段": "当前阶段", "原值": "", "新值": "已投"},
    ])
    entries = tracker.read_history(ws_dir)
    row = tracker.read_rows(ws_dir)[0]
    own = tracker.history_by_id(entries).get((row.get("id") or "").strip(), [])
    assert tracker.stage_base_date(row, own) == today - timedelta(days=9)


# --- 2. 等价性：子集扫描 == 全量扫描 ---------------------------------------------

def test_subset_scan_equals_full_scan(tmp_path):
    ws_dir = str(tmp_path / "ws")
    os.makedirs(ws_dir)
    _seed(ws_dir)

    entries = tracker.read_history(ws_dir)
    by_id = tracker.history_by_id(entries)
    rows = tracker.read_rows(ws_dir)
    assert len(rows) == 4, "夹具退化"

    for row in rows:
        own = by_id.get((row.get("id") or "").strip(), [])
        assert tracker.stale_days(row, own) == tracker.stale_days(row, entries)
        assert tracker.health_score(row, own) == tracker.health_score(row, entries)
        assert tracker.stage_base_date(row, own) == tracker.stage_base_date(row, entries)


# --- 3. 结构：只读一次、且逐行只收自己的条目 -------------------------------------

def test_applications_list_reads_history_once_and_passes_own_entries(
        client, tmp_path, monkeypatch):
    ws_dir = str(tmp_path / WS)
    _seed(ws_dir)

    reads = {"n": 0}
    real_read = tracker.read_history

    def counting_read(*args, **kwargs):
        reads["n"] += 1
        return real_read(*args, **kwargs)

    seen = []
    real_stale = tracker.stale_days

    def capturing_stale(row, entries, today=None):
        seen.append((row.get("id", ""), [e.get("id", "") for e in entries]))
        return real_stale(row, entries, today)

    monkeypatch.setattr(tracker, "read_history", counting_read)
    monkeypatch.setattr(tracker, "stale_days", capturing_stale)

    res = client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert reads["n"] == 1, "时间线应整表只读一次（每行各自全量读是旧病）"
    assert len(seen) == 4, "每行应各判一次 stale_days——捕获网没挂上或行数不符"
    for row_id, entry_ids in seen:
        assert all(eid == row_id for eid in entry_ids), (row_id, entry_ids)


def test_dashboard_reads_history_once_and_passes_own_entries(
        client, tmp_path, monkeypatch):
    """看板与列表页**同一张结构网**（独立审查 M1）。

    只数 `read_history` 次数是不够的：把 `by_id.get(...)` 改回传全量 history，
    次数仍然是 1——用例照样绿，而 O(行数 × 条目数) 已经悄悄回来了。
    所以这里与 applications 那条一样，既数次数、也捕获**每行实际收到的条目 id**。
    """
    ws_dir = str(tmp_path / WS)
    _seed(ws_dir)

    reads = {"n": 0}
    real_read = tracker.read_history

    def counting_read(*args, **kwargs):
        reads["n"] += 1
        return real_read(*args, **kwargs)

    seen = []
    real_stale = tracker.stale_days

    def capturing_stale(row, entries, today=None):
        seen.append((row.get("id", ""), [e.get("id", "") for e in entries]))
        return real_stale(row, entries, today)

    monkeypatch.setattr(tracker, "read_history", counting_read)
    monkeypatch.setattr(tracker, "stale_days", capturing_stale)

    res = client.get("/api/dashboard", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert reads["n"] == 1, "看板时间线应整表只读一次"
    assert seen, "捕获网没挂上——看板已不走 tracker.stale_days，这条用例失去意义"
    for row_id, entry_ids in seen:
        assert all(eid == row_id for eid in entry_ids), (row_id, entry_ids)


# --- 4. 端到端对账：端点输出 == 领域函数 ------------------------------------------

def test_applications_list_meta_matches_domain_functions(client, tmp_path):
    ws_dir = str(tmp_path / WS)
    _seed(ws_dir)

    res = client.get("/api/applications", params={"ws": WS})
    assert res.status_code == 200, res.text
    items = {it["id"]: it for it in res.json()["items"]}
    assert set(items) == {"A001", "A002", "A003", "A004"}

    entries = tracker.read_history(ws_dir)
    for row in tracker.read_rows(ws_dir):
        item = items[row["id"]]
        days = tracker.stale_days(row, entries)
        assert item["stageDays"] == (days if days is not None else "")
        # 端点经 JSON 往返：先归一化再逐字段比
        expected = json.loads(json.dumps(tracker.health_score(row, entries)))
        assert item["health"] == expected, row["id"]


def test_dashboard_stale_and_pending_match_domain_functions(client, tmp_path):
    ws_dir = str(tmp_path / WS)
    _seed(ws_dir)

    res = client.get("/api/dashboard", params={"ws": WS})
    assert res.status_code == 200, res.text
    data = res.json()

    rows = tracker.read_rows(ws_dir)
    entries = tracker.read_history(ws_dir)

    expected_stale = {}
    for row in rows:
        if row.get("当前阶段") in tracker.TERMINAL_STAGES:
            continue
        days = tracker.stale_days(row, entries)
        if days is not None and days >= tracker.STALE_DAYS:
            expected_stale[row["id"]] = days
    assert expected_stale, "夹具没造出静默记录——这条网就白跑了"
    assert {s["id"]: s["days"] for s in data["stale"]} == expected_stale

    expected_pending = {}
    for row in rows:
        health = tracker.health_score(row, entries)
        if health["level"] not in (None, "ok"):
            expected_pending[row["id"]] = health["level"]
    assert expected_pending, "夹具没造出待推进记录"
    assert {p["id"]: p["level"] for p in data["pending"]} == expected_pending
