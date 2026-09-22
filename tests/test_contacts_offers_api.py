# -*- coding: utf-8 -*-
"""联系人 / Offer 的 HTTP 契约（T 批补网）：GET / POST / PATCH 与拒绝分支。

此前这两个域只有批 D 的删除测试（`test_record_deletes_api.py`），CRUD 主路径
零覆盖——而它们是**直写**端点（锁内 read-modify-write）。这里钉住：

1. 创建 → 列表往返（落盘后的字节由领域层读回核对）；
2. 拒绝分支的错误码稳定：422 必填缺失 / 404 关联不存在 / 422 无可更新字段；
3. PATCH 只改传入字段并回报 `_changed`；Offer 关联记录版从主表带出公司并入账时间线。
"""

import os
import sys

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


def _app_row(app_id="A001"):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": app_id, "公司": "云帆", "岗位": "后端", "当前阶段": "已投"})
    return row


# --- 联系人 -------------------------------------------------------------------


def test_contacts_create_and_list_roundtrip(client, tmp_path):
    ws_dir = str(tmp_path / WS)

    res = client.post("/api/progress/contacts", params={"ws": WS}, json={
        "姓名": "林工", "角色": "HR", "联系方式": "lin@example.com",
        "下次跟进": "2026-09-25"})
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["联系人id"] == "C001"
    assert created["姓名"] == "林工"

    res = client.get("/api/progress/contacts", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["rows"][0]["联系人id"] == "C001"
    assert len(tracker.read_contacts(ws_dir)) == 1


def test_contacts_reject_branches_use_stable_codes(client, tmp_path):
    res = client.post("/api/progress/contacts", params={"ws": WS}, json={"姓名": "  "})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.nameRequired"

    res = client.post("/api/progress/contacts", params={"ws": WS},
                      json={"姓名": "林工", "关联记录": "A999"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.linkNotFound"


def test_contacts_patch_updates_only_given_fields(client, tmp_path):
    ws_dir = str(tmp_path / WS)
    client.post("/api/progress/contacts", params={"ws": WS},
                json={"姓名": "林工", "角色": "HR"})

    res = client.patch("/api/progress/contacts/C001", params={"ws": WS},
                       json={"备注": "内推人"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["_changed"] == ["备注"]
    assert body["备注"] == "内推人"
    assert body["角色"] == "HR", "未传入的字段不得被动"
    assert tracker.read_contacts(ws_dir)[0]["备注"] == "内推人"

    res = client.patch("/api/progress/contacts/C001", params={"ws": WS}, json={})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.noFieldsToUpdate"

    res = client.patch("/api/progress/contacts/C999", params={"ws": WS},
                       json={"备注": "x"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.contactNotFound"


# --- Offer --------------------------------------------------------------------


def test_offers_create_and_list_roundtrip(client, tmp_path):
    ws_dir = str(tmp_path / WS)

    res = client.post("/api/progress/offers", params={"ws": WS}, json={
        "公司": "云帆", "岗位": "后端", "月薪": "20k", "答复截止日": "2026-10-01"})
    assert res.status_code == 201, res.text
    assert res.json()["offer_id"] == "O001"

    res = client.get("/api/progress/offers", params={"ws": WS})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert len(tracker.read_offers(ws_dir)) == 1


def test_offers_reject_branches_use_stable_codes(client, tmp_path):
    res = client.post("/api/progress/offers", params={"ws": WS},
                      json={"岗位": "后端"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.companyRequired"

    res = client.post("/api/progress/offers", params={"ws": WS},
                      json={"关联记录": "A999"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.linkNotFound"


def test_offer_with_link_carries_company_and_records_history(client, tmp_path):
    ws_dir = str(tmp_path / WS)
    tracker.write_rows([_app_row()], ws_dir)

    res = client.post("/api/progress/offers", params={"ws": WS},
                      json={"关联记录": "A001", "月薪": "20k"})
    assert res.status_code == 201, res.text
    assert res.json()["公司"] == "云帆", "公司应从主表带出"

    history = tracker.read_history(ws_dir)
    assert any(r["字段"] == "offer" for r in history)


def test_offers_patch_updates_only_given_fields(client, tmp_path):
    client.post("/api/progress/offers", params={"ws": WS},
                json={"公司": "云帆", "月薪": "20k"})

    res = client.patch("/api/progress/offers/O001", params={"ws": WS},
                       json={"答复截止日": "2026-10-01"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["_changed"] == ["答复截止日"]
    assert body["月薪"] == "20k"

    res = client.patch("/api/progress/offers/O001", params={"ws": WS}, json={})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.noFieldsToUpdate"

    res = client.patch("/api/progress/offers/O999", params={"ws": WS},
                       json={"备注": "x"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.offerNotFound"
