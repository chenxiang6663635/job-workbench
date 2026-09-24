# -*- coding: utf-8 -*-
"""邮箱配置的两个只读端点（全部离线：连接层被 mock）。

为什么单开一个薄路由而不是往 `routers/imap.py` 里塞：那个文件登记 304 行、
只许变小（`tools/size_allowlist.txt`），而这两件事都不属于「配置读写 / 拉取」。

钉住三件事：

1. **预设清单是纯数据**：不读工作区、不连网、不含任何凭证字段，
   前端拿它画下拉；Outlook 这类已知不可用的服务商必须带原因（不让用户填一个必错的框）。
2. **文件夹候选只在用户点击时连一次**：凭证不全在连接前就 400（不留半开会话）；
   列不出来是 502 人话，不是 500。
3. **只读**：候选来自 `LIST`，不碰任何邮件正文。
"""

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


def _save(client, **body):
    payload = {"host": "imap.example.com", "port": 993, "user": "me@example.com",
               "password": "auth-code-1234", "folder": "INBOX"}
    payload.update(body)
    return client.post("/api/imap", params={"ws": WS}, json=payload)


# --- 1. 预设清单（纯数据）------------------------------------------------------

def test_providers_endpoint_returns_the_preset_list(client):
    body = client.get("/api/mail/providers").json()

    assert body["count"] == len(body["items"])
    assert body["count"] >= 9, "国内主流 + 国际主流都要在表里"

    by_id = {item["id"]: item for item in body["items"]}
    for expected in ("qq", "netease163", "netease126", "yeah", "gmail",
                     "outlook", "aliyun", "sina", "sohu"):
        assert expected in by_id, "预设缺失：%s" % expected


def test_provider_items_carry_what_the_picker_needs(client):
    items = client.get("/api/mail/providers").json()["items"]

    for item in items:
        for key in ("id", "labelKey", "domains", "host", "port",
                    "requiresAppPassword", "authHintKey", "imapIdRequired"):
            assert key in item, "%s 缺字段 %s" % (item.get("id"), key)
        assert item["domains"], item["id"]
        assert isinstance(item["port"], int)


def test_unsupported_provider_is_flagged_with_a_reason(client):
    """Outlook 个人账号 2024-09 起停用基本认证：宁可说清，也不给一个填了就错的框。"""
    by_id = {item["id"]: item for item in client.get("/api/mail/providers").json()["items"]}
    outlook = by_id["outlook"]
    assert outlook["unsupported"] is True
    assert outlook["unsupportedReasonKey"]


def test_netease_presets_declare_the_imap_id_requirement(client):
    """163 / 126 / yeah.net 不发 IMAP ID 会拿到 Unsafe Login——这条要在预设里就可见。"""
    by_id = {item["id"]: item for item in client.get("/api/mail/providers").json()["items"]}
    for provider_id in ("netease163", "netease126", "yeah"):
        assert by_id[provider_id]["imapIdRequired"] is True
    assert by_id["qq"]["imapIdRequired"] is False


def test_providers_endpoint_exposes_no_credentials(client):
    """纯数据端点：不许出现任何凭证字段（防御将来误加）。"""
    res = client.get("/api/mail/providers")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["items"], "清单不能为空"
    text = repr(body)
    for forbidden in ("password", "api_key", "apiKey"):
        assert forbidden not in text, forbidden


def test_providers_endpoint_needs_no_workspace(client):
    """它不读工作区，所以不带 ws 也该 200（前端在未选工作区时也要画下拉）。"""
    assert client.get("/api/mail/providers").status_code == 200


# --- 2. 文件夹候选 -------------------------------------------------------------

def test_folders_requires_an_email_first(client):
    res = client.post("/api/mail/folders", params={"ws": WS})
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "imap.needEmail"


def test_folders_requires_a_password(client):
    _save(client, user="me@example.com", password="")
    res = client.post("/api/mail/folders", params={"ws": WS})
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "imap.needPassword"


def test_folders_returns_candidates(client, monkeypatch):
    _save(client)
    monkeypatch.setattr(imap_fetch, "probe_folders",
                        lambda host, user, password, port: ["INBOX", "Archive"])

    body = client.post("/api/mail/folders", params={"ws": WS}).json()

    assert body["folders"] == ["INBOX", "Archive"]
    assert body["count"] == 2
    assert body["server"] == "imap.example.com"


def test_folders_failure_is_wrapped_as_a_readable_error(client, monkeypatch):
    _save(client)

    def _boom(host, user, password, port):
        raise imap_fetch.ImapFetchError("登录失败：授权码不对")

    monkeypatch.setattr(imap_fetch, "probe_folders", _boom)

    res = client.post("/api/mail/folders", params={"ws": WS})
    assert res.status_code == 502, res.text
    assert res.json()["error_code"] == "imap.foldersFailed"


def test_folders_never_touches_mail(client, monkeypatch):
    """候选来自 LIST：不许出现任何取正文的动作。"""
    _save(client)
    calls = []

    def _probe(host, user, password, port):
        calls.append((user, host, port))
        return []

    monkeypatch.setattr(imap_fetch, "probe_folders", _probe)
    monkeypatch.setattr(imap_fetch, "fetch_messages",
                        lambda *a, **k: pytest.fail("列文件夹不该读邮件"))

    assert client.post("/api/mail/folders", params={"ws": WS}).status_code == 200
    assert calls == [("me@example.com", "imap.example.com", 993)]


def test_folders_surfaces_the_classified_login_code(client, monkeypatch):
    """163 系的 `Unsafe Login` 有自己的错误码：界面要给的下一条指引与"列文件夹失败"不同，
    不能被 catch-all 的 `imap.foldersFailed` 吞掉。"""
    _save(client)

    def _boom(host, user, password, port):
        raise imap_fetch.ImapFetchError("登录失败：Unsafe Login, please contact kefu",
                                        code="imap.unsafeLogin")

    monkeypatch.setattr(imap_fetch, "probe_folders", _boom)

    res = client.post("/api/mail/folders", params={"ws": WS})
    assert res.status_code == 502, res.text
    assert res.json()["error_code"] == "imap.unsafeLogin"
