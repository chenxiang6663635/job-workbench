# -*- coding: utf-8 -*-
"""IMAP 配置与拉取的 HTTP 层测试（全部离线，imaplib 被 mock）。

钉住的东西与调研红线一一对应：

1. **凭证只存本地 + 脱敏**：响应里不出现完整授权码；空密码保存表示保留原值。
   桌面版授权码存 Windows 凭据管理器、配置文件只留引用 `auth_ref`（源码 / CLI
   形态为显式明文回退）——解析、惰性迁移与写失败回退见文件末尾第 5 节。
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
from routers import imap  # noqa: E402

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
        # conftest 把默认形态钉在明文回退（不碰真机凭据管理器）——storage 如实报它
        "storage": "plaintext",
    }


def test_save_returns_masked_password_only(tmp_path, client):
    res = _save(client)
    assert res.status_code == 200
    body = res.json()
    assert body["hasPassword"] is True
    assert body["password"].endswith("1234")
    assert "auth-code" not in json.dumps(body), "完整授权码不得出现在响应里"

    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert stored["password"] == "auth-code-1234", (
        "明文回退形态下授权码仍住在配置文件里（测试默认形态，见 conftest）；"
        "credman 形态的「只留引用」由第 5 节的假 store 用例钉住")


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


# --- 2b. host 形状校验（issue #50 A1）----------------------------------------
# 判据：坏地址要在**使用前**被拦住。拖到连接期的代价不是"多一个错"，而是错得
# 看不懂——用户看到的是"连不上 993 端口"，而真正的原因是他把 https:// 也贴了进来。

def test_save_rejects_a_host_with_a_scheme(tmp_path, client):
    res = _save(client, host="https://imap.example.com")
    assert res.status_code == 422
    body = res.json()
    assert body["error_code"] == "imap.hostMalformed"
    assert "协议" in body["detail"]


def test_save_rejects_a_host_with_a_slash(tmp_path, client):
    res = _save(client, host="imap.example.com/path")
    assert res.status_code == 422
    assert res.json()["error_code"] == "imap.hostMalformed"


def test_save_rejects_a_host_with_whitespace(tmp_path, client):
    res = _save(client, host="imap example.com")
    assert res.status_code == 422
    assert res.json()["error_code"] == "imap.hostMalformed"


def test_save_rejects_host_and_port_written_together(tmp_path, client):
    """`host:port` 连写要直接指出「端口填端口栏」，而不是拖到连接期。"""
    res = _save(client, host="imap.example.com:993")
    assert res.status_code == 422
    assert res.json()["error_code"] == "imap.hostPortInline"


def test_save_rejects_an_over_long_host(tmp_path, client):
    host = ("a" * 250) + ".example.com"
    res = _save(client, host=host)
    assert res.status_code == 422
    body = res.json()
    assert body["error_code"] == "imap.hostTooLong"
    assert body["error_params"]["length"] == len(host)


def test_save_accepts_an_ipv6_literal(tmp_path, client):
    """IPv6 字面量**含冒号但不是** host:port —— 不能误伤。"""
    assert _save(client, host="[::1]").status_code == 200


def test_save_still_allows_an_empty_host(tmp_path, client):
    """留空是合法输入（表示"按邮箱域名推断"）——校验不能把这条路堵死。"""
    assert _save(client, host="").status_code == 200


def test_save_rejects_a_full_width_colon(tmp_path, client):
    """全角冒号也是 host:port 连写（独立审查 MINOR-1）。

    中文输入法下 `imap.qq.com：993` 是一敲就出来的形态。ASCII 判定看不住它，
    结果就退回到本批要消灭的那件事：连接期一句"连不上 993 端口"，看不出原因。
    """
    res = _save(client, host="imap.qq.com：993")
    assert res.status_code == 422
    assert res.json()["error_code"] == "imap.hostPortInline"


def test_save_rejects_full_width_slash_and_space(tmp_path, client):
    """全角斜杠 / 全角空格同理——按 NFKC 归一化后再判定形状。"""
    assert _save(client, host="imap.qq.com／path").json()["error_code"] == "imap.hostMalformed"
    assert _save(client, host="imap　qq.com").json()["error_code"] == "imap.hostMalformed"


def test_save_accepts_an_ipv6_zone_id(tmp_path, client):
    """带作用域标识的 link-local 地址是合法 IPv6（独立审查 MINOR-3）：
    不能因为含 `%`/冒号就被判成 host:port。"""
    assert _save(client, host="fe80::1%eth0").status_code == 200


def test_fetch_rejects_a_stored_host_with_a_scheme(tmp_path, client, monkeypatch):
    """老配置里已经存了坏值：使用时也要拦住，且**不发起连接**。"""
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(path), "w", encoding="utf-8").write(json.dumps({
        "host": "https://imap.example.com", "port": 993,
        "user": "me@example.com", "password": "auth-code-1234", "folder": "INBOX"}))
    called = []
    monkeypatch.setattr(imap_fetch, "fetch_messages",
                        lambda *a, **k: called.append(1) or [])

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={})

    assert res.status_code == 422
    assert res.json()["error_code"] == "imap.hostMalformed"
    assert called == [], "形状不合法时不该发起连接"


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

    def _fake(host, user, password, port, folder, limit, since_days):
        captured.update({"host": host, "folder": folder, "limit": limit,
                         "since_days": since_days})
        return []

    monkeypatch.setattr(imap_fetch, "fetch_messages", _fake)

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={"limit": 7})
    assert res.status_code == 200
    assert captured["host"] == "imap.qq.com"
    assert captured["limit"] == 7
    assert captured["since_days"] == 30, "不传时默认最近 30 天"
    assert res.json()["server"] == "imap.qq.com"


def test_fetch_passes_the_time_window(tmp_path, client, monkeypatch):
    _save(client)
    captured = {}

    def _fake(host, user, password, port, folder, limit, since_days):
        captured["since_days"] = since_days
        return []

    monkeypatch.setattr(imap_fetch, "fetch_messages", _fake)

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={"since_days": 7})
    assert res.status_code == 200
    assert captured["since_days"] == 7
    assert res.json()["sinceDays"] == 7


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


# --- 5. 凭据 at-rest：引用 / 惰性迁移 / 失败回退（issue #203）------------------
# 桌面版形态下授权码住 Windows 凭据管理器，配置文件只留引用 `auth_ref`；
# 源码 / CLI 形态是显式明文回退（conftest 的 autouse fixture 已把测试默认钉在
# plaintext——**绝不碰真机凭据管理器**）。这里用假 store 做跨平台行为验证。


class _FakeCredStore:
    """假凭据管理器：dict 存储 + 两个可编程开关（写失败 / 读不到）。

    不 import test_credentials.py 的私有件：两个测试文件各钉各的契约，
    共享测试工具会让"改一处、两处变绿"的静默耦合漏进来。
    """

    kind = "credman"

    def __init__(self):
        self.stored = {}
        self.fail_set = False
        self.get_returns_none = False

    def available(self):
        return True

    def get(self, ref):
        if self.get_returns_none:
            return None
        return self.stored.get(ref)

    def set(self, ref, secret):
        if self.fail_set:
            return False
        self.stored[ref] = secret
        return True

    def delete(self, ref):
        self.stored.pop(ref, None)
        return True


@pytest.fixture()
def fake_store(monkeypatch):
    """把凭据存储钉到假 store 上（`select_store` 每次现取，所以打桩模块属性即可；
    每次调用都返回同一实例）。"""
    store = _FakeCredStore()
    monkeypatch.setattr(imap.credentials, "select_store", lambda: store)
    return store


def test_save_stores_the_secret_in_the_credential_manager(tmp_path, client, fake_store):
    """保存即入凭据管理器：配置文件里只剩引用，密文不再落盘。"""
    res = _save(client)

    assert res.status_code == 200
    body = res.json()
    assert body["storage"] == "credman"
    assert body["hasPassword"] is True
    assert body["password"].endswith("1234")
    assert "auth-code" not in json.dumps(body), "完整授权码不得出现在响应里"

    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert "password" not in stored, "密文已进凭据管理器，配置文件里不该再留一份"
    assert stored["auth_ref"].startswith("job-workbench/")
    assert fake_store.stored[stored["auth_ref"]] == "auth-code-1234"


def test_get_lazily_migrates_a_legacy_plaintext_password(tmp_path, client, fake_store):
    """读时惰性迁移：老配置里的明文搬进系统存储，文件当场改写（否则每次读都重复迁移）。"""
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(path), "w", encoding="utf-8").write(json.dumps({
        "host": "imap.example.com", "port": 993, "user": "me@example.com",
        "password": "auth-code-1234", "folder": "INBOX"}))

    body = client.get("/api/imap", params={"ws": WS}).json()

    assert body["storage"] == "credman"
    assert body["hasPassword"] is True
    assert body["password"].endswith("1234")
    stored = json.loads(io.open(str(path), encoding="utf-8").read())
    assert "password" not in stored, "迁移后明文不得留在文件里"
    assert fake_store.stored[stored["auth_ref"]] == "auth-code-1234"


def test_save_with_blank_password_also_migrates_a_legacy_plaintext(tmp_path, client, fake_store):
    """传空密码（保留原值）也要顺手迁移——迁移结果由同一次持锁原子写落盘。"""
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(path), "w", encoding="utf-8").write(json.dumps({
        "host": "imap.example.com", "port": 993, "user": "me@example.com",
        "password": "auth-code-1234", "folder": "INBOX"}))

    res = _save(client, password="", host="imap.changed.com")

    assert res.status_code == 200
    assert res.json()["storage"] == "credman"
    stored = json.loads(io.open(str(path), encoding="utf-8").read())
    assert "password" not in stored
    assert stored["host"] == "imap.changed.com"
    assert fake_store.stored[stored["auth_ref"]] == "auth-code-1234"


def test_save_keeps_plaintext_when_the_store_write_fails(tmp_path, client, fake_store):
    """写失败保留明文（数据丢失 > 可用性降级）：响应如实报 plaintext。"""
    fake_store.fail_set = True

    res = _save(client)

    assert res.status_code == 200
    assert res.json()["storage"] == "plaintext"
    assert res.json()["hasPassword"] is True
    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert stored["password"] == "auth-code-1234"
    assert "auth_ref" not in stored, "写失败不得留下指向空条目的引用"


def test_ref_without_stored_secret_is_409_on_use_but_200_on_read(tmp_path, client, fake_store):
    """「引用在手但取不到」≠「没配置」：使用时 409 指路「重新保存」，读取仍 200 展示现状。"""
    _save(client)
    fake_store.get_returns_none = True

    res = client.post("/api/imap/test", params={"ws": WS})
    assert res.status_code == 409
    assert res.json()["error_code"] == "imap.credentialUnavailable"
    assert "重新保存" in res.json()["detail"]

    res = client.post("/api/imap/fetch", params={"ws": WS}, json={})
    assert res.status_code == 409
    assert res.json()["error_code"] == "imap.credentialUnavailable"

    body = client.get("/api/imap", params={"ws": WS}).json()
    assert body["hasPassword"] is False
    assert body["storage"] == "credman", "引用还在——形态仍是 credman（不是没配过）"
    assert body["password"] == ""


def test_rotation_reuses_the_same_ref(tmp_path, client, fake_store):
    """轮换（改授权码）复用同一引用：凭据管理器里不留指向旧密文的孤儿条目。"""
    _save(client)
    first = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())["auth_ref"]

    _save(client, password="auth-code-5678")

    second = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())["auth_ref"]
    assert second == first
    assert fake_store.stored == {first: "auth-code-5678"}, "只应有这一条凭据"


# --- 6. 「清除即删」端点（#203 遗留，DELETE /api/imap/credential）------------------


def test_delete_credential_clears_plaintext_and_keeps_the_rest(tmp_path, client):
    _save(client, host="imap.changed.com")
    res = client.delete("/api/imap/credential", params={"ws": WS})
    assert res.status_code == 200
    body = res.json()
    assert body["hasPassword"] is False and body["password"] == ""
    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert "password" not in stored and "auth_ref" not in stored
    assert stored["host"] == "imap.changed.com", "清除凭据不该动其它字段"


def test_delete_credential_is_idempotent_and_never_creates_a_file(tmp_path, client):
    res = client.delete("/api/imap/credential", params={"ws": WS})
    assert res.status_code == 200 and res.json()["hasPassword"] is False
    assert not _config_path(tmp_path).exists(), "清除不该凭空创建配置文件"
    assert client.delete("/api/imap/credential", params={"ws": WS}).status_code == 200


def test_delete_credential_removes_the_credman_entry(tmp_path, client, fake_store):
    _save(client)
    ref = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())["auth_ref"]
    assert fake_store.stored[ref] == "auth-code-1234"
    res = client.delete("/api/imap/credential", params={"ws": WS})
    assert res.json()["hasPassword"] is False
    assert ref not in fake_store.stored, "系统存储里的条目要一并删除"
    stored = json.loads(io.open(str(_config_path(tmp_path)), encoding="utf-8").read())
    assert "auth_ref" not in stored and "password" not in stored
