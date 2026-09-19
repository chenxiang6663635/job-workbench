# -*- coding: utf-8 -*-
"""看板的「近 7 天宣讲会」区块：数据来自 talks.csv，与主表时间线无关。

钉住三件容易静默坏掉的事：

1. **时间列带时刻也要进窗口**：`talks.时间` 是 `YYYY-MM-DD HH:MM`，而窗口判定
   用的是纯日期——不取日期前缀，整条会被静默丢掉（"少给数据"比报错危险）；
2. **窗口是闭区间 [today, today+7]**：今天与第 7 天都算「近 7 天」，第 8 天不算；
3. **空时间跳过 + 按时间升序**：时间待定的活动不进区块；进来的先到先排。
"""

import csv
import io
import os
import sys
from datetime import date, timedelta

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import tracker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
TRACKING_DIR = "05_投递追踪"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """同 test_dashboard_pool：应用根指到临时目录，不依赖仓库里真实的 personal/。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    ws = tmp_path / WS
    ws.mkdir()
    (ws / TRACKING_DIR).mkdir()

    import main  # noqa: E402  （ROOT 改写之后再导入）
    return TestClient(main.app)


def _write_talks(tmp_path, rows):
    """写 talks.csv：表头走 `TALK_FIELDS`（列名同源，别在这里手抄一份）。"""
    path = os.path.join(str(tmp_path), WS, TRACKING_DIR, "talks.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.TALK_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _row(talk_id, company, when_text, attend="待定"):
    return {"宣讲会id": talk_id, "公司": company, "时间": when_text,
            "形式": "线下", "地点或链接": "", "关联记录": "",
            "是否参加": attend, "收获": "", "备注": ""}


def _talks(client):
    res = client.get("/api/dashboard", params={"ws": WS})
    assert res.status_code == 200
    return res.json()["upcomingTalks"]


def test_upcoming_talks_window_is_inclusive(client, tmp_path):
    """闭区间 [today, today+7]：今天与第 7 天都在，第 8 天不在。"""
    today = date.today()
    _write_talks(tmp_path, [
        _row("T001", "今天公司", "%s 14:00" % today.isoformat()),
        _row("T002", "第七天公司", "%s 09:30" % (today + timedelta(days=7)).isoformat()),
        _row("T003", "第八天公司", "%s 09:30" % (today + timedelta(days=8)).isoformat()),
    ])
    assert [item["id"] for item in _talks(client)] == ["T001", "T002"]


def test_upcoming_talks_keeps_timed_rows(client, tmp_path):
    """时间带时刻（YYYY-MM-DD HH:MM）也要进窗口——不取日期前缀会静默丢整条。"""
    today = date.today()
    _write_talks(tmp_path, [_row("T001", "某公司", "%s 14:00" % today.isoformat())])
    items = _talks(client)
    assert len(items) == 1
    assert items[0]["时间"].endswith("14:00")


def test_upcoming_talks_skips_empty_time(client, tmp_path):
    """时间待定的活动不进「近 7 天」——没有日期就无从谈起。"""
    _write_talks(tmp_path, [_row("T001", "待定公司", "")])
    assert _talks(client) == []


def test_upcoming_talks_sorted_by_time(client, tmp_path):
    """按时间升序：先来的排在前面（与 CSV 行序无关）。"""
    today = date.today()
    day2 = (today + timedelta(days=2)).isoformat()
    day5 = (today + timedelta(days=5)).isoformat()
    # CSV 里故意把晚的写在前面，输出必须是早的在前
    _write_talks(tmp_path, [_row("T001", "第五天公司", "%s 09:00" % day5),
                            _row("T002", "后天公司", "%s 09:00" % day2)])
    assert [item["id"] for item in _talks(client)] == ["T002", "T001"]
