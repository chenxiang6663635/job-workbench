# -*- coding: utf-8 -*-
"""邮件 → 候选事实的 HTTP 层（批 9）：只读、不落盘、错误码复用。

钉三条（与 IMAP 面的红线同源）：

1. **只读**：调用前后工作区文件字节不变——它只是把「已经拉到手的正文」解释成
   建议，写不写由用户逐条确认后的既有链路决定；
2. **ICS 优先**：同一封邮件带 ICS 时，时间与会议链接以 ICS 为准（source=ics）；
3. **同义不新造 code**：空输入复用 `status.textRequired`（前端语言包已覆盖）。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
TRACKING_DIR = "05_投递追踪"

ICS = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "METHOD:REQUEST",
    "BEGIN:VEVENT",
    "UID:abc-123@example.com",
    "DTSTART;TZID=Asia/Shanghai:20260925T140000",
    "SUMMARY:面试邀请（技术面）",
    "URL:https://meeting.tencent.com/dm/abc123",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
])

ROW = {"id": "A001", "公司": "云帆智算", "岗位": "后端工程师", "当前阶段": "已投"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402

    return TestClient(main.app)


def _seed(tmp_path, rows):
    from jobws_core import tracker

    path = tmp_path / WS / TRACKING_DIR
    path.mkdir(parents=True, exist_ok=True)
    with io.open(str(path / "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for row in rows:
            full = {field: "" for field in tracker.FIELDS}
            full.update(row)
            writer.writerow(full)
    # mails.csv 也建一份：只读断言要有字节可比
    with io.open(str(path / "mails.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.MAIL_FIELDS)
        writer.writeheader()
        writer.writerow({field: "" for field in tracker.MAIL_FIELDS})


def _snapshot(tmp_path):
    out = {}
    for base, _dirs, files in os.walk(str(tmp_path / WS)):
        for name in files:
            path = os.path.join(base, name)
            with io.open(path, "rb") as f:
                out[path] = f.read()
    return out


def _suggest(client, **body):
    payload = {"原文": "", "ics": "", "id": ""}
    payload.update(body)
    return client.post("/api/imap/suggest-facts", params={"ws": WS}, json=payload)


def test_suggest_facts_prefers_ics(tmp_path, client):
    _seed(tmp_path, [ROW])
    res = _suggest(client, 原文="（正文略）", ics=ICS)
    assert res.status_code == 200, res.text

    facts = res.json()["facts"]
    time_fact = next(f for f in facts if f["kind"] == "时间")
    assert time_fact["value"] == "2026-09-25 14:00"
    assert time_fact["source"] == "ics"
    assert any(f["kind"] == "会议链接" and f["source"] == "ics" for f in facts)


def test_suggest_facts_is_read_only(tmp_path, client):
    _seed(tmp_path, [ROW])
    before = _snapshot(tmp_path)

    res = _suggest(client, 原文="云帆智算：面试改到 2026-09-25 14:00，"
                                 "见 https://meeting.tencent.com/dm/new001")

    assert res.status_code == 200, res.text
    assert _snapshot(tmp_path) == before, "只读端点不得改动工作区任何文件"


def test_suggest_facts_matches_records_and_stage(tmp_path, client):
    _seed(tmp_path, [ROW])
    facts = _suggest(client, 原文="云帆智算 后端工程师：很遗憾，本次不再推进。").json()["facts"]

    record = next(f for f in facts if f["kind"] == "公司岗位")
    assert record["value"] == "A001"
    stage = next(f for f in facts if f["kind"] == "阶段")
    assert stage["value"] == "已挂"
    assert stage["targetId"] == "A001"


def test_suggest_facts_focus_id_beats_matching(tmp_path, client):
    _seed(tmp_path, [ROW, {"id": "A007", "公司": "星河数据", "岗位": "热管理",
                           "当前阶段": "测评"}])
    facts = _suggest(client, 原文="您的简历已进入笔试环节", id="A007").json()["facts"]

    record = next(f for f in facts if f["kind"] == "公司岗位")
    assert record["value"] == "A007"
    assert record["note"] == "手动指定"


def test_suggest_facts_requires_text(client):
    res = _suggest(client)
    assert res.status_code == 422
    assert res.json()["error_code"] == "status.textRequired"
