# -*- coding: utf-8 -*-
"""到点提醒的轻端点（首发前收口批 笔 5）。

桌面壳要在**窗口就绪后**与运行期内周期性地问一句"今天有什么到点的事"，然后发一条系统
通知。它需要的是一份小、快、只读的答复——而不是把整个看板（漏斗、健康度、最近动作）
拉一遍。

判定全部复用看板那三个 helper（`_upcoming_todos` / `_upcoming_talks` / `_overdue_pending`）：
"什么算到点"只能有一处定义，否则通知说今天到期、看板说没有，用户只能信一个。
"""

import datetime
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jobws_core import tracker  # noqa: E402

WS = "ws-remind"
TODAY = datetime.date.today()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.setenv("JOBWS_WORKSPACE", WS)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _row(**overrides):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"公司": "某公司", "岗位": "某岗位"})
    row.update(overrides)
    return row


def _seed(tmp_path):
    ws = str(tmp_path / WS)
    tracker.write_rows([
        _row(id="A001", 公司="过期公司", 当前阶段="待投",
             截止日期=(TODAY - datetime.timedelta(days=1)).isoformat()),
        _row(id="A002", 公司="待办公司", 当前阶段="已投", 下次动作="发跟进邮件",
             下次动作日期=(TODAY + datetime.timedelta(days=2)).isoformat()),
        # 终态记录不该出现在提醒里：它没有"该做的事"，只有历史
        _row(id="A003", 公司="终态公司", 当前阶段="已挂",
             下次动作日期=TODAY.isoformat()),
    ], ws)
    tracker.write_talks([
        {"宣讲会id": "T001", "公司": "宣讲公司",
         "时间": "%s 14:00" % (TODAY + datetime.timedelta(days=1)).isoformat()},
    ], ws)
    return ws


def _fingerprint(root):
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as handle:
                out[rel] = handle.read()
    return out


def test_due_reports_the_three_buckets(tmp_path, client):
    _seed(tmp_path)

    res = client.get("/api/reminders/due")

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["date"] == TODAY.isoformat()
    assert data["workspace"] == WS
    assert data["counts"] == {"todos": 1, "talks": 1, "overdue": 1}, data["counts"]
    assert data["todos"][0]["公司"] == "待办公司"
    assert data["todos"][0]["说明"] == "发跟进邮件"
    assert data["overdue"][0]["公司"] == "过期公司"
    assert data["talks"][0]["公司"] == "宣讲公司"


def test_due_is_read_only(tmp_path, client):
    ws = _seed(tmp_path)
    before = _fingerprint(ws)

    client.get("/api/reminders/due")

    assert _fingerprint(ws) == before, "提醒是只读查询，不许动任何字节"


def test_due_on_empty_workspace_is_all_zeros(tmp_path, client):
    res = client.get("/api/reminders/due")

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["counts"] == {"todos": 0, "talks": 0, "overdue": 0}
    assert data["todos"] == [] and data["talks"] == [] and data["overdue"] == []
