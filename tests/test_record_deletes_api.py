# -*- coding: utf-8 -*-
"""记录删除的 HTTP 端点（批 D）：六组 preview-delete 的契约与旧直删的撤除。

钉住四件事：
1. **预览不落盘**：预览只签发令牌，CSV 一个字节不动；响应 = 令牌 + 摘要 + 差异；
2. **错误码稳定**：找不到 id → 400 + `<域>.deleteFailed`，reason 给具体原因；
3. **旧直删已撤除**：`DELETE /api/progress/mails/{id}` 不再存在（防复活——
   写通道只有 `/api/approvals/apply` 一条）；
4. **落盘端到端**：令牌 POST 到 apply → 行删了 + 留痕在工作区之外。
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
from jobws_core.tracker import deletes  # noqa: E402

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


@pytest.fixture()
def outside(tmp_path, monkeypatch):
    """把留痕根钉到临时目录：不污染真实快照区。"""
    root = tmp_path / "snapshots"
    monkeypatch.setattr(deletes.pathres, "snapshot_root", lambda: str(root))
    return str(root)


def _mail_row(subject="面试邀约", link="", mail_id="M001"):
    row = dict((field, "") for field in tracker.MAIL_FIELDS)
    row.update({"邮件id": mail_id, "主题": subject, "关联记录": link,
                "日期": "2026-09-21"})
    return row


def _app_row(app_id="A001"):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": app_id, "公司": "TCL", "岗位": "前端开发",
                "当前阶段": "已投"})
    return row


def _seed_store(ws_dir, store_key, record_id):
    """按存储描述符造一行（五张从表通用）。"""
    store = deletes._STORES[store_key]
    row = dict((field, "") for field in store["fields"])
    row[store["id_field"]] = record_id
    store["write"]([row], ws_dir)


PREVIEW_CASES = [
    ("/api/progress/mails/preview-delete", "mails", "M001",
     "progress.mailDeleteFailed"),
    ("/api/progress/interviews/preview-delete", "interviews", "I001",
     "progress.interviewDeleteFailed"),
    ("/api/progress/contacts/preview-delete", "contacts", "C001",
     "progress.contactDeleteFailed"),
    ("/api/progress/talks/preview-delete", "talks", "T001",
     "progress.talkDeleteFailed"),
    ("/api/progress/offers/preview-delete", "offers", "O001",
     "progress.offerDeleteFailed"),
]


@pytest.mark.parametrize("url,store_key,record_id,error_code", PREVIEW_CASES)
def test_each_store_preview_endpoint(client, tmp_path, outside, url, store_key,
                                     record_id, error_code):
    """五张从表：预览 200 给令牌；找不到 → 400 + 稳定错误码。"""
    ws_dir = str(tmp_path / WS)
    _seed_store(ws_dir, store_key, record_id)

    res = client.get(url, params={"ws": WS, "id": record_id})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["token"]
    assert record_id in data["summary"]

    res = client.get(url, params={"ws": WS, "id": "X999"})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == error_code
    assert "找不到" in body["error_params"]["reason"]


def test_preview_mail_delete_does_not_touch_the_csv(client, tmp_path, outside):
    ws_dir = str(tmp_path / WS)
    tracker.write_mails([_mail_row(),
                         _mail_row(subject="笔试通知", mail_id="M002")], ws_dir)
    path = os.path.join(ws_dir, "05_投递追踪", "mails.csv")
    with open(path, "rb") as handle:
        before = handle.read()

    res = client.get("/api/progress/mails/preview-delete",
                     params={"ws": WS, "id": "M001"})

    assert res.status_code == 200
    data = res.json()
    assert "M001" in data["summary"]
    assert any("M001" in line for line in data["diff"])
    with open(path, "rb") as handle:
        assert handle.read() == before


def test_old_mail_delete_endpoint_is_gone(client, tmp_path):
    """旧直删撤除（防复活）：路径不再接受 DELETE，数据原样。"""
    ws_dir = str(tmp_path / WS)
    tracker.write_mails([_mail_row()], ws_dir)

    res = client.request("DELETE", "/api/progress/mails/M001", params={"ws": WS})

    assert res.status_code in (404, 405)
    assert len(tracker.read_mails(ws_dir)) == 1


def test_preview_application_delete_lists_unbind(client, tmp_path, outside):
    """投递端点：差异表列明将解绑的关联记录；预览不落盘。"""
    ws_dir = str(tmp_path / WS)
    tracker.write_rows([_app_row()], ws_dir)
    tracker.write_mails([_mail_row(link="A001")], ws_dir)

    res = client.get("/api/applications/preview-delete",
                     params={"ws": WS, "id": "A001"})

    assert res.status_code == 200
    data = res.json()
    assert "解绑" in data["summary"]
    assert any("M001" in line for line in data["diff"])
    assert len(tracker.read_mails(ws_dir)) == 1

    res = client.get("/api/applications/preview-delete",
                     params={"ws": WS, "id": "A999"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "app.deleteFailed"


def test_apply_token_lands_delete_with_trace(client, tmp_path, outside):
    """端到端：预览令牌 → 唯一落盘通道 → 行删了、留痕在工作区之外。"""
    ws_dir = str(tmp_path / WS)
    tracker.write_mails([_mail_row(),
                         _mail_row(subject="笔试通知", mail_id="M002")], ws_dir)
    token = client.get("/api/progress/mails/preview-delete",
                       params={"ws": WS, "id": "M001"}).json()["token"]

    res = client.post("/api/approvals/apply", json={"token": token})

    assert res.status_code == 200
    body = res.json()
    assert body["written"] == 1
    assert body["trace"]
    assert not os.path.abspath(body["trace"]).startswith(
        os.path.abspath(ws_dir) + os.sep)
    assert [row["邮件id"] for row in tracker.read_mails(ws_dir)] == ["M002"]
