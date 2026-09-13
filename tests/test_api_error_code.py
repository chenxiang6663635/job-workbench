# -*- coding: utf-8 -*-
"""API 错误的加法改造：detail 之外多给一个 error_code。

这是 i18n 的后端半边（前端 `humanizeError` 按 code 查语言包）。要钉住三条：

1. **加法而非替换**：每个错误都必须同时带 `detail` 与 `error_code`——
   detail 是既有契约（测试、调试脚本、第三方调用都读它），换掉它等于把
   一处改动摊到所有调用方；前端查不到 code 时也要能回落显示 detail。
2. **code 稳定**：同一个语义在不同路由里必须是同一个 code，且**不许变**——
   它一旦改了，前端语言包就对不上，界面会退回中文原文（功能不坏、但英文
   用户看不懂）。所以这里把 code 字样逐个钉死，改动必须是有意识的。
3. **参数齐备**：用户可见的动态值（阶段名、目录名、id）要出现在 `error_params` 里，
   否则英文文案只能靠猜——`{{stage}}` 会原样渲染成花括号。

反面也钉一条：普通 `HTTPException`（未改造的旧路径，如 FastAPI 默认 404）
**不带** error_code，说明这不是全局包装。
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
import tracker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
TRACKING_DIR = "05_投递追踪"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _make_tracking(tmp_path, rows):
    path = tmp_path / WS / TRACKING_DIR
    path.mkdir(parents=True, exist_ok=True)
    with io.open(str(path / "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for row in rows:
            full = {field: "" for field in tracker.FIELDS}
            full.update(row)
            writer.writerow(full)


ONE_ROW = {"id": "A001", "公司": "某某科技", "岗位": "热管理工程师",
           "方向": "other", "批次": "正式批", "当前阶段": "已投"}


def _body(res):
    """取出错误体，并断言「加法」的两条：detail 在、error_code 在。"""
    data = res.json()
    assert "detail" in data, "detail 是既有契约，必须保留"
    assert data.get("error_code"), "每个改造过的错误都要带 error_code"
    return data


# ---- 工作区参数（deps.py）：全局最高频的一类 ----
# 这几条刻意不传合法的 ws：被拒绝的正是查询参数本身

def test_unknown_near_miss_param_carries_code_and_name(client):
    res = client.get("/api/applications?workspace=personal")
    assert res.status_code == 400
    data = _body(res)
    assert data["error_code"] == "ws.unknownParam"
    assert data["error_params"]["name"] == "workspace"


def test_uppercase_ws_param_carries_its_own_code(client):
    res = client.get("/api/applications?WS=personal")
    assert res.status_code == 400
    data = _body(res)
    assert data["error_code"] == "ws.unknownParamCase"
    assert data["error_params"]["name"] == "WS"


def test_empty_ws_param_carries_code(client):
    res = client.get("/api/applications?ws=")
    assert res.status_code == 400
    assert _body(res)["error_code"] == "ws.empty"


def test_missing_workspace_carries_code_and_name(client):
    res = client.get("/api/applications?ws=no-such-ws")
    assert res.status_code == 404
    data = _body(res)
    assert data["error_code"] == "ws.notFound"
    assert data["error_params"]["name"] == "no-such-ws"


def test_absolute_ws_is_rejected_with_code(client):
    # 用根路径而不是 "C:/…"：后者在 Linux（CI）上不是绝对路径，会走成越界分支
    res = client.get("/api/applications?ws=/etc")
    assert res.status_code == 400
    assert _body(res)["error_code"] == "ws.mustBeRelative"


# ---- 投递记录（applications.py）----

def test_missing_record_carries_code_and_id(client):
    res = client.get("/api/applications/NOPE/history", params={"ws": WS})
    assert res.status_code == 404
    data = _body(res)
    assert data["error_code"] == "app.recordNotFound"
    assert data["error_params"]["id"] == "NOPE"


def _new_app(**overrides):
    """新建投递的最小合法载荷（方向与批次是 pydantic 必填）。"""
    body = {"公司": "A公司", "岗位": "B岗位", "方向": "other", "批次": "正式批"}
    body.update(overrides)
    return body


def test_score_out_of_range_carries_code(client):
    res = client.post("/api/applications", params={"ws": WS},
                      json=_new_app(评分=200))
    assert res.status_code == 422
    assert _body(res)["error_code"] == "app.scoreRange"


def test_bad_date_carries_label_and_value(client):
    res = client.post("/api/applications", params={"ws": WS},
                      json=_new_app(截止日期="2026/09/30"))
    assert res.status_code == 422
    data = _body(res)
    assert data["error_code"] == "app.dateFormat"
    assert data["error_params"] == {"label": "截止日期", "value": "2026/09/30"}


def test_terminal_stage_without_reason_carries_stage(client):
    res = client.post("/api/applications", params={"ws": WS},
                      json=_new_app(当前阶段="已挂"))
    assert res.status_code == 422
    data = _body(res)
    assert data["error_code"] == "app.reasonRequired"
    assert data["error_params"]["stage"] == "已挂"


def test_duplicate_record_carries_code(tmp_path, client):
    _make_tracking(tmp_path, [ONE_ROW])
    res = client.post("/api/applications", params={"ws": WS},
                      json=_new_app(公司="某某科技", 岗位="热管理工程师"))
    assert res.status_code == 409
    data = _body(res)
    assert data["error_code"] == "app.duplicate"
    assert data["error_params"]["id"] == "A001"


def test_unknown_stage_carries_stage_list(client):
    res = client.post("/api/applications", params={"ws": WS},
                      json=_new_app(当前阶段="不存在"))
    assert res.status_code == 422
    data = _body(res)
    assert data["error_code"] == "app.stageInvalid"
    assert "已投" in data["error_params"]["stages"]


# ---- 状态建议（B11）：文案来自 tools/ 的校验函数，code 由路由补 ----

def test_suggest_requires_text_with_code(client):
    res = client.post("/api/applications/suggest-status", params={"ws": WS},
                      json={"原文": "   "})
    assert res.status_code == 422
    assert _body(res)["error_code"] == "status.textRequired"


def test_suggest_unknown_stage_carries_code(tmp_path, client):
    _make_tracking(tmp_path, [ONE_ROW])
    res = client.post("/api/applications/apply-status-suggestion", params={"ws": WS},
                      json={"id": "A001", "阶段": "不存在的阶段", "原阶段": "已投"})
    assert res.status_code == 422
    assert _body(res)["error_code"] == "status.stageInvalid"


def test_stale_snapshot_carries_both_stages(tmp_path, client):
    _make_tracking(tmp_path, [ONE_ROW])
    res = client.post("/api/applications/apply-status-suggestion", params={"ws": WS},
                      json={"id": "A001", "阶段": "一面", "原阶段": "笔试"})
    assert res.status_code == 409
    data = _body(res)
    assert data["error_code"] == "status.stale"
    assert data["error_params"] == {"current": "已投", "seen": "笔试"}


def test_monotonicity_refusal_carries_current_and_next(tmp_path, client):
    _make_tracking(tmp_path, [dict(ONE_ROW, 当前阶段="已挂", 状态原因="不合适")])
    res = client.post("/api/applications/apply-status-suggestion", params={"ws": WS},
                      json={"id": "A001", "阶段": "一面", "原阶段": "已挂"})
    assert res.status_code == 422
    data = _body(res)
    assert data["error_code"] == "status.notAllowed"
    assert data["error_params"]["current"] == "已挂"
    assert data["error_params"]["next"] == "一面"


# ---- 反面：未改造的路径不该被贴上 code ----

def test_untouched_http_exception_has_no_code(client):
    """不存在的路由仍走 FastAPI 默认 404，没有 error_code。

    这是刻意的：本改造逐处显式指定 code，不做全局自动包装——按状态码猜一个
    code 出来，只会让前端语言包里多出一堆永远对不上的假语义。
    """
    res = client.get("/api/no-such-endpoint")
    assert res.status_code == 404
    assert "error_code" not in res.json()
