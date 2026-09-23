# -*- coding: utf-8 -*-
"""投递追踪表 PATCH / 列表筛选 / 建议写回的三处 HTTP 契约（审计修复批 P1）。

三条都是「两侧各自合法、合起来才错」的类型：

1. PATCH 里显式 `null` = 清空该字段——此前 `model_dump()` 把 None 一律滤掉，
   「清空评分」被静默变成「没有提供任何字段」，用户点了清空、刷新又是旧值；
2. `due_within` 负数此前被 `>= 0` 静默退化成「不过滤」：调用方要「最近到期」
   却拿到全量列表（语义相反且无声），而足够大的值还能把 OverflowError 顶成 500；
3. apply-status 只比「当前阶段」：另一处改的是状态原因 / 下次动作时照样被覆盖——
   乐观并发保护了字段 A，写操作却会覆盖 B/C/D。
"""

import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import tracker  # noqa: E402

WS = "ws-app"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _seed(tmp_path, **over):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": "A001", "公司": "云帆", "岗位": "后端", "当前阶段": "已投",
                "评分": "88"})
    row.update(over)
    tracker.write_rows([row], str(tmp_path / WS))
    return row


# --- 1. PATCH：显式 null 清空、未提供的字段不动 ------------------------------


def test_patch_null_clears_the_field(client, tmp_path):
    """显式 null 必须清空落盘，不能留原值，更不能把 Python 的 None 写成字符串。"""
    _seed(tmp_path)

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"评分": None})
    assert res.status_code == 200, res.text
    assert res.json()["item"]["评分"] == ""

    rows = tracker.read_rows(str(tmp_path / WS))
    assert rows[0]["评分"] == ""
    assert "None" not in str(rows[0].values()), "落盘里出现 'None' 说明把 None 当值写了"


def test_patch_null_leaves_other_fields_alone(client, tmp_path):
    """清空一个字段不该顺带走别的值——曾是 Moon 去重 alias 的同款取舍在这的重演。"""
    _seed(tmp_path, 备注="旧备注")

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"评分": None})
    assert res.status_code == 200, res.text

    rows = tracker.read_rows(str(tmp_path / WS))
    assert rows[0]["备注"] == "旧备注"
    assert rows[0]["岗位"] == "后端"


def test_patch_score_accepts_decimal_and_rounds_half_up(client, tmp_path):
    """评分允许小数（与新增路径同口径），落盘按四舍五入取整——round() 是银行家舍入。"""
    _seed(tmp_path)

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"评分": 88.6})
    assert res.status_code == 200, res.text
    assert res.json()["item"]["评分"] == "89"

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"评分": 86.5})
    assert res.status_code == 200, res.text
    assert res.json()["item"]["评分"] == "87", "86.5 应进到 87，不是取偶得 86"


def test_patch_score_range_is_still_enforced(client, tmp_path):
    _seed(tmp_path)

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"评分": 120})
    assert res.status_code == 422
    assert res.json()["error_code"] == "app.scoreRange"


# --- 2. due_within 的取值范围 ------------------------------------------------


def test_due_within_negative_is_rejected(client, tmp_path):
    """负数是「语义相反且无声」：此前 >= 0 的判定让它退化成返回全量。"""
    _seed(tmp_path)

    res = client.get("/api/applications", params={"ws": WS, "due_within": -3})
    assert res.status_code == 422
    assert res.json()["error_code"] == "app.dueWithinRange"


def test_due_within_absurd_value_is_rejected(client, tmp_path):
    """足够大的天数会让 timedelta 抛 OverflowError → 此前是 500 而不是一句人话。"""
    _seed(tmp_path)

    res = client.get("/api/applications", params={"ws": WS, "due_within": 10 ** 9})
    assert res.status_code == 422
    assert res.json()["error_code"] == "app.dueWithinRange"


def test_due_within_zero_still_filters_today(client, tmp_path):
    _seed(tmp_path, 下次动作日期=date.today().isoformat())

    res = client.get("/api/applications", params={"ws": WS, "due_within": 0})
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1


# --- 3. apply-status：并发比对覆盖所有将写字段 -------------------------------


def test_apply_status_detects_reason_change(client, tmp_path):
    """别人改的是状态原因时，只比阶段会让这条覆盖写静默通过。"""
    _seed(tmp_path, 状态原因="已由另一处改写")

    res = client.post("/api/applications/apply-status-suggestion", params={"ws": WS},
                      json={"id": "A001", "阶段": "一面", "原阶段": "已投",
                            "原状态原因": "更早的快照"})
    assert res.status_code == 409, res.text
    assert res.json()["error_code"] == "status.staleField"
    assert res.json()["error_params"]["field"] == "状态原因"

    rows = tracker.read_rows(str(tmp_path / WS))
    assert rows[0]["当前阶段"] == "已投", "冲突时一个字都不许写"


def test_apply_status_accepts_matching_snapshot(client, tmp_path):
    """快照一致照常写回——这条是对上一条的否定验证：守卫不能变成一律拒绝。"""
    _seed(tmp_path)

    res = client.post("/api/applications/apply-status-suggestion", params={"ws": WS},
                      json={"id": "A001", "阶段": "一面", "原阶段": "已投",
                            "原状态原因": ""})
    assert res.status_code == 200, res.text
    assert res.json()["item"]["当前阶段"] == "一面"
