# -*- coding: utf-8 -*-
"""投递状态建议的 HTTP 层（B11 阶段 2）。

规则层（`tools/status_parse.py`）已由 `tests/test_status_parse.py` 钉住判断口径；
这里钉的是**端点的语义边界**，四条：

1. **未确认绝不改写**：`suggest-status` 是只读的——调用完追踪表字节不变、
   时间线文件不该被创建。这是整个功能最该被信任的一条。
2. **用户确认才写**：`apply-status-suggestion` 写回并留痕，且**依据要进时间线**
   （半年后得说得清「这条为什么从一面变成已挂」）。
3. **前端不可信**：单调性、终态、必填原因、枚举全部在服务端**锁内**重算，
   直接构造违反规则的请求必须被拦住。
4. **乐观并发**：用户确认时看到的阶段与库里的不一致 → 409 要求重新解析，
   绝不照着旧快照写（那会抹掉别处的改动）。
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


def _tracking_bytes(tmp_path):
    return (tmp_path / WS / TRACKING_DIR / "tracker.csv").read_bytes()


def _history(tmp_path):
    path = tmp_path / WS / TRACKING_DIR / "history.csv"
    if not os.path.isfile(str(path)):
        return []
    with io.open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _suggest(client, text, **body):
    payload = {"原文": text}
    payload.update(body)
    return client.post("/api/applications/suggest-status", params={"ws": WS}, json=payload)


def _apply(client, **body):
    payload = {"id": "A001", "阶段": "二面"}
    payload.update(body)
    return client.post("/api/applications/apply-status-suggestion",
                       params={"ws": WS}, json=payload)


ONE_ROW = [{"id": "A001", "公司": "示例科技", "岗位": "后端开发", "当前阶段": "已投",
            "方向": "other", "批次": "正式批"}]


# --- 1. suggest：只读 --------------------------------------------------------

def test_suggest_never_writes(tmp_path, client):
    """红线：解析只是预览——追踪表字节不变，时间线文件不该被创建。"""
    _make_tracking(tmp_path, ONE_ROW)
    before = _tracking_bytes(tmp_path)

    res = _suggest(client, "示例科技邀请您参加二面。")

    assert res.status_code == 200
    assert _tracking_bytes(tmp_path) == before
    assert _history(tmp_path) == [], "预览阶段不该写时间线"


def test_suggest_returns_actionable_suggestion(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    body = _suggest(client, "示例科技邀请您参加二面。").json()
    assert body["matches"][0]["id"] == "A001"
    assert body["matches"][0]["建议阶段"] == "二面"
    assert body["matches"][0]["可覆盖"] is True
    assert body["matches"][0]["证据"], "建议必须带原文证据，否则用户没法复核"


def test_suggest_rejects_empty_text(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    assert _suggest(client, "   ").status_code == 422


def test_suggest_can_focus_a_record_when_the_text_has_no_company_name(tmp_path, client):
    """站内信通篇不写公司名时的兜底：用户点选记录后仍能拿到建议。"""
    _make_tracking(tmp_path, ONE_ROW)
    body = _suggest(client, "您好，您的简历已进入笔试环节。", id="A001").json()
    assert body["matches"][0]["id"] == "A001"
    assert body["matches"][0]["建议阶段"] == "笔试"
    assert body["matches"][0]["命中"] == "手动指定"


def test_suggest_accepts_an_explicit_null_id(tmp_path, client):
    """前端把「没指定记录」序列化成 null 是最自然的写法，不该因此 422。

    pydantic v2 下 `id: str = None` 只声明了默认值，**显式传 null 会校验失败**
    （端到端验证时踩到过：界面只显示一句「Input should be a valid string」）。
    """
    _make_tracking(tmp_path, ONE_ROW)
    res = client.post("/api/applications/suggest-status", params={"ws": WS},
                      json={"原文": "示例科技邀请您参加二面。", "id": None})
    assert res.status_code == 200
    assert res.json()["matches"][0]["建议阶段"] == "二面"


def test_suggest_reports_a_missing_focus_id_instead_of_crashing(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    res = _suggest(client, "您好，您的简历已进入笔试环节。", id="A999")
    assert res.status_code == 200
    assert res.json()["matches"] == []
    assert any("A999" in n for n in res.json()["notes"])


# --- 2. apply：写回并留痕 ----------------------------------------------------

def test_apply_writes_the_stage_and_records_the_evidence(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)

    res = _apply(client, 阶段="二面", 原阶段="已投", 依据="邀请您参加第二轮面试")

    assert res.status_code == 200
    assert res.json()["item"]["当前阶段"] == "二面"

    rows = tracker.read_rows(str(tmp_path / WS))
    assert rows[0]["当前阶段"] == "二面"

    entries = _history(tmp_path)
    assert any(e["字段"] == "当前阶段" and e["新值"] == "二面" for e in entries)
    source = [e for e in entries if e["字段"] == "状态来源"]
    assert source, "时间线里必须留下依据，否则事后说不清这次改动从哪来"
    assert "邀请您参加第二轮面试" in source[0]["新值"]


def test_apply_updates_only_the_target_row(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW + [
        {"id": "A002", "公司": "云帆智算", "岗位": "算法工程师", "当前阶段": "一面",
         "方向": "other", "批次": "正式批"}])

    _apply(client, 阶段="二面", 原阶段="已投")

    rows = tracker.read_rows(str(tmp_path / WS))
    other = [r for r in rows if r["id"] == "A002"][0]
    assert other["当前阶段"] == "一面"


# --- 3. 前端不可信：服务端锁内重算 -------------------------------------------

def test_apply_refuses_to_knock_an_offer_down(tmp_path, client):
    """直接构造违反红线的请求（跳过前端）也必须被拦。"""
    _make_tracking(tmp_path, [{"id": "A001", "公司": "示例科技", "岗位": "后端开发",
                               "当前阶段": "offer", "方向": "other", "批次": "正式批"}])

    res = _apply(client, 阶段="已挂", 原阶段="offer", 状态原因="很遗憾，不再推进")

    assert res.status_code == 422
    assert "不覆盖" in res.json()["detail"]
    assert tracker.read_rows(str(tmp_path / WS))[0]["当前阶段"] == "offer"


def test_apply_refuses_to_move_a_terminal_record(tmp_path, client):
    _make_tracking(tmp_path, [{"id": "A001", "公司": "示例科技", "岗位": "后端开发",
                               "当前阶段": "已挂", "状态原因": "面试未通过",
                               "方向": "other", "批次": "正式批"}])

    res = _apply(client, 阶段="offer", 原阶段="已挂")

    assert res.status_code == 422
    assert "终态" in res.json()["detail"]


def test_apply_refuses_a_weaker_stage(tmp_path, client):
    _make_tracking(tmp_path, [{"id": "A001", "公司": "示例科技", "岗位": "后端开发",
                               "当前阶段": "三面", "方向": "other", "批次": "正式批"}])
    res = _apply(client, 阶段="一面", 原阶段="三面")
    assert res.status_code == 422
    assert "不强于" in res.json()["detail"]


def test_apply_requires_a_reason_when_landing_on_a_terminal_stage(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    res = _apply(client, 阶段="已挂", 原阶段="已投")
    assert res.status_code == 422
    assert "状态原因" in res.json()["detail"]


def test_apply_rejects_an_unknown_stage(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    assert _apply(client, 阶段="随便编的阶段", 原阶段="已投").status_code == 422


def test_apply_reports_a_missing_record(tmp_path, client):
    _make_tracking(tmp_path, ONE_ROW)
    assert _apply(client, id="A999", 阶段="二面", 原阶段="已投").status_code == 404


# --- 4. 乐观并发 -------------------------------------------------------------

def test_apply_requires_the_stage_the_user_saw(tmp_path, client):
    """`原阶段` 必填：它是乐观并发的唯一依据，不该能被省略。

    之前用 Optional，不传就静默跳过校验——等于把「别照旧快照写」这道保护
    变成了可选项（一个竞态窗口就足以让旧快照覆盖别人的改动）。
    """
    _make_tracking(tmp_path, ONE_ROW)
    res = client.post("/api/applications/apply-status-suggestion",
                      params={"ws": WS}, json={"id": "A001", "阶段": "二面"})
    assert res.status_code == 422


def test_apply_conflicts_when_the_record_moved_since_the_user_looked(tmp_path, client):
    """用户确认时看到「已投」，但库里已经是「笔试」——必须 409 而不是照写。

    建议是几分钟前在旧快照上算出来的；照写会把别处（另一个标签页 / CLI /
    批量导入）的改动抹掉。宁可让用户重新解析一次。
    """
    _make_tracking(tmp_path, [{"id": "A001", "公司": "示例科技", "岗位": "后端开发",
                               "当前阶段": "笔试", "方向": "other", "批次": "正式批"}])

    res = _apply(client, 阶段="二面", 原阶段="已投")

    assert res.status_code == 409
    assert "重新解析" in res.json()["detail"]
    assert tracker.read_rows(str(tmp_path / WS))[0]["当前阶段"] == "笔试"
