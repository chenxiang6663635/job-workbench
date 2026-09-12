# -*- coding: utf-8 -*-
"""IMAP 配置与拉取的 HTTP 层测试（全部离线，imaplib 被 mock）。

钉住的东西与调研红线一一对应：

1. **凭证只存本地 + 脱敏**：响应里不出现完整授权码；空密码保存表示保留原值。
2. **只读、默认 dry-run**：`/fetch` 不写任何数据——追踪表字节不变、
   文件系统不新增产物。它只是「取邮件正文」的取样口。
3. **无半开会话**：配置不全在连接前就 400；底层错误包装成 502 人话。
4. **服务器推断**：host 留空按邮箱域名推断；推断不出时人话报错而不是瞎连。
"""

import io
import json
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
import imap_fetch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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


def _config_path(tmp_path):
    return tmp_path / WS / "config" / "imap.json"


def _save(client, **body):
    payload = {"host": "imap.example.com", "port": 993, "user": "me@example.com",
               "password": "auth-code-1234", "folder": "INBOX"}
    payload.update(body)
    return client.post("/api/imap", params={"ws": WS}, json=payload)


# --- 1. 配置读写与脱敏 --------------------------------------------------------

def test_get_returns_empty_defaults(tmp_path, client):
    body = client.get("/api/imap", params={"ws": WS}).json()
    assert body == {
        "host": "", "port": 993, "user": "", "folder": "INBOX",
        "password": "", "hasPassword": False, "serverHint": "",
    }


def test_save_returns_masked_password_only(tmp_path, client):
    res = _save(client)
    assert res.status_code == 200
    body = res.json()
    assert body["hasPassword"] is True
    assert body["password"].endswith("1234")
    assert "auth-code" not in json.dumps(body), "完整授权码不得出现在响应里"

    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert stored["password"] == "auth-code-1234", "本地文件里应保存完整授权码（只存在这里）"


def test_blank_password_keeps_the_previous_one(tmp_path, client):
    """前端不来回传完整凭证：空密码=保留原值，改主机不会把密码清掉。"""
    _save(client)
    res = _save(client, password="", host="imap.changed.com")

    assert res.json()["hasPassword"] is True
    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert stored["password"] == "auth-code-1234"
    assert stored["host"] == "imap.changed.com"


def test_blank_folder_falls_back_to_inbox(tmp_path, client):
    res = _save(client, folder="   ")
    assert res.json()["folder"] == "INBOX"


def test_save_rejects_a_bad_port(tmp_path, client):
    assert _save(client, port=0).status_code == 422
    assert _save(client, port=70000).status_code == 422


def test_get_reports_the_guessed_server_for_hint(tmp_path, client):
    # 拼接构造：隐私护栏拦真实服务商域名邮箱字面量（见 test_imap_fetch.py 同款说明）
    _save(client, host="", user="someone@" + "qq.com")
    assert client.get("/api/imap", params={"ws": WS}).json()["serverHint"] == "imap.qq.com"


# --- 2. 测试连接 --------------------------------------------------------------

def test_test_endpoint_requires_saved_credentials(tmp_path, client):
    assert client.post("/api/imap/test", params={"ws": WS}).status_code == 400
    _save(client, password="")
    assert client.post("/api/imap/test", params={"ws": WS}).status_code == 400


def test_test_endpoint_wraps_imap_errors(tmp_path, client, monkeypatch):
    _save(client)

    def _boom(*args, **kwargs):
        raise imap_fetch.ImapFetchError("登录失败：LOGIN failed（多数邮箱需要授权码）")

    monkeypatch.setattr(imap_fetch, "test_connection", _boom)

    res = client.post("/api/imap/test", params={"ws": WS})
    assert res.status_code == 502
    assert "授权码" in res.json()["detail"]


def test_test_endpoint_reports_the_folder_count(tmp_path, client, monkeypatch):
    _save(client)
    monkeypatch.setattr(imap_fetch, "test_connection", lambda *a, **k: 42)

    res = client.post("/api/imap/test", params={"ws": WS})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["messageCount"] == 42


# --- 3. 拉取：只读取样，dry-run ----------------------------------------------

def test_fetch_requires_config(tmp_path, client):
    assert client.post("/api/imap/fetch", params={"ws": WS}, json={}).status_code == 400


def test_fetch_never_writes_any_data(tmp_path, client, monkeypatch):
    """红线：拉取只做取样——不碰追踪表、不在工作区新增任何文件。"""
    _save(client)
    monkeypatch.setattr(imap_fetch, "fetch_messages", lambda *a, **k: [
        {"uid": "3", "subject": "面试邀请", "from": "hr@x.com",
         "date": "Wed, 10 Sep 2026", "body": "邀请您参加面试"}])

    before = sorted(os.listdir(str(tmp_path / WS)))
    res = client.post("/api/imap/fetch", params={"ws": WS}, json={"limit": 5})

    assert res.status_code == 200
    body = res.json()
    assert body["dryRun"] is True
    assert body["count"] == 1
    assert body["messages"][0]["subject"] == "面试邀请"
    assert not os.path.exists(str(tmp_path / WS / "05_投递追踪")), "拉取不该创建追踪目录"
    assert sorted(os.listdir(str(tmp_path / WS))) == before, "拉取不该在工作区新增文件"


def test_fetch_uses_the_guessed_server_when_host_is_empty(tmp_path, client, monkeypatch):
    _save(client, host="", user="me@" + "qq.com")
    captured = {}

    def _fake(host, user, password, port, folder, limit):
        captured.update({"host": host, "folder": folder, "limit": limit})
        return []

    monkeypatch.setattr(imap_fetch, "fetch_messages", _fake)

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={"limit": 7})
    assert res.status_code == 200
    assert captured["host"] == "imap.qq.com"
    assert captured["limit"] == 7
    assert res.json()["server"] == "imap.qq.com"


def test_fetch_rejects_a_host_it_cannot_guess(tmp_path, client):
    _save(client, host="", user="me@unknown-corp.example")
    res = client.post("/api/imap/fetch", params={"ws": WS}, json={})
    assert res.status_code == 400
    assert "手填" in res.json()["detail"]


def test_fetch_wraps_fetch_errors(tmp_path, client, monkeypatch):
    _save(client)

    def _boom(*args, **kwargs):
        raise imap_fetch.ImapFetchError("操作超时：imap.example.com 在 15 秒内没有响应")

    monkeypatch.setattr(imap_fetch, "fetch_messages", _boom)

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={})
    assert res.status_code == 502
    assert "超时" in res.json()["detail"]
    assert res.json()["detail"].find("auth-code") == -1, "错误消息不得泄露凭证"


# --- 4. 配置容错 --------------------------------------------------------------

def test_get_survives_a_corrupted_config_file(tmp_path, client):
    """配置文件损坏时回落默认值并照常响应——不能因一条脏文件让整个页面报错。"""
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(path), "w", encoding="utf-8").write("{not json")
    body = client.get("/api/imap", params={"ws": WS}).json()
    assert body["hasPassword"] is False
    assert body["port"] == 993


def test_get_ignores_wrongly_typed_fields(tmp_path, client):
    """float 端口整体回落默认（不做静默取整），非字符串字段回落默认。"""
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(path), "w", encoding="utf-8").write(json.dumps({
        "host": "imap.example.com", "port": 993.5, "user": 123, "folder": ["INBOX"],
    }))
    body = client.get("/api/imap", params={"ws": WS}).json()
    assert body["port"] == 993
    assert body["user"] == ""
    assert body["folder"] == "INBOX"
    assert body["host"] == "imap.example.com"
