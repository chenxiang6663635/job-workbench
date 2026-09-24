# -*- coding: utf-8 -*-
"""imap_session 的会话层测试（全部离线：用假会话，不碰网络）。

钉住四件事：

1. **IMAP `ID`（RFC 2971）**：只在服务器声明 `ID` 能力时发；发失败只留日志、
   绝不让整次拉取失败。163 / 126 / yeah.net 要求客户端先声明身份，否则 `SELECT`
   直接回 `Unsafe Login`——所以还有一条时序断言：**ID 必须在 SELECT 之前**。
2. **只读**：`select_readonly` 必须带 `readonly=True`——这条红线不因为抽取而松动。
3. **错误口径**：协议错误统一包成 `ImapFetchError`（既有调用方与测试都按这个类型捕获）。
4. **文件夹候选**：`list_folders` 解析出可读名字；列不出来时返回空列表
   （界面少一组候选，不是功能失效）。
"""

import imaplib
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))


def _session():
    """惰性取模块：实现尚未落地时让测试**失败**（而不是整文件收集期报错）。"""
    try:
        import imap_session
    except ImportError as exc:
        pytest.fail("imap_session 尚未实现：%s" % exc)
    return imap_session


class StubConn:
    """记录调用序列的假会话；`capabilities` 决定要不要发 ID。"""

    def __init__(self, capabilities=(), login_error=None, list_data=None,
                 select_result=("OK", [b"3"])):
        self.capabilities = tuple(capabilities)
        self.login_error = login_error
        self.list_data = list_data
        self.select_result = select_result
        self.calls = []

    def login(self, user, password):
        self.calls.append(("login", user))
        if self.login_error:
            raise self.login_error
        return ("OK", [b""])

    def _simple_command(self, name, *args):
        self.calls.append(("id", name) + tuple(args))
        return ("OK", [b""])

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return self.select_result

    def list(self):
        self.calls.append(("list",))
        return ("OK", self.list_data or [])

    def logout(self):
        self.calls.append(("logout",))
        return ("BYE", [])


# --- 1. IMAP ID ---------------------------------------------------------------

def test_send_id_is_skipped_when_server_lacks_the_capability():
    session = _session()
    conn = StubConn(capabilities=("IMAP4REV1",))
    assert session.send_id(conn) is False
    assert not [call for call in conn.calls if call[0] == "id"]


def test_send_id_declares_identity_when_supported():
    session = _session()
    conn = StubConn(capabilities=("ID", "IMAP4REV1"))
    assert session.send_id(conn, version="9.9.9") is True
    sent = [call for call in conn.calls if call[0] == "id"]
    assert sent and "9.9.9" in str(sent[0])


def test_send_id_failure_never_breaks_the_session():
    """身份声明是「让对方愿意放行」，不该成为新的失败点。"""
    session = _session()
    conn = StubConn(capabilities=("ID",))

    def _boom(name, *args):
        raise imaplib.IMAP4.error("ID rejected")

    conn._simple_command = _boom
    assert session.send_id(conn) is False


def test_login_declares_identity_right_after_authenticating():
    session = _session()
    conn = StubConn(capabilities=("ID",))
    session.login(conn, "a@example.com", "code")
    assert [call[0] for call in conn.calls] == ["login", "id"]


def test_identity_is_declared_before_opening_the_folder():
    """163 的真实约束：ID 必须在 SELECT 之前，否则 Unsafe Login。"""
    session = _session()
    conn = StubConn(capabilities=("ID",))
    session.login(conn, "a@example.com", "code")
    session.select_readonly(conn, "INBOX")
    kinds = [call[0] for call in conn.calls]
    assert kinds.index("id") < kinds.index("select")


def test_login_failure_is_wrapped_without_the_password():
    session = _session()
    conn = StubConn(login_error=imaplib.IMAP4.error("LOGIN failed"))
    with pytest.raises(session.ImapFetchError) as exc:
        session.login(conn, "a@example.com", "super-secret")
    assert "授权码" in str(exc.value)
    assert "super-secret" not in str(exc.value)


def test_login_failure_carries_a_classified_code():
    """Unsafe Login 的下一步和「密码打错了」完全不同，必须能区分。"""
    session = _session()
    conn = StubConn(login_error=imaplib.IMAP4.error("Unsafe Login, contact kefu"))
    with pytest.raises(session.ImapFetchError) as exc:
        session.login(conn, "a@example.com", "code")
    assert exc.value.code == "imap.unsafeLogin"


def test_plain_auth_failure_gets_the_auth_code():
    session = _session()
    conn = StubConn(login_error=imaplib.IMAP4.error("[AUTHENTICATIONFAILED] nope"))
    with pytest.raises(session.ImapFetchError) as exc:
        session.login(conn, "a@example.com", "code")
    assert exc.value.code == "imap.authFailed"


# --- 2. 只读打开文件夹 ---------------------------------------------------------

def test_select_readonly_opens_the_folder_read_only():
    session = _session()
    conn = StubConn()
    session.select_readonly(conn, "INBOX")
    assert ("select", "INBOX", True) in conn.calls


def test_select_readonly_falls_back_to_inbox():
    session = _session()
    conn = StubConn()
    session.select_readonly(conn, "")
    assert ("select", session.DEFAULT_FOLDER, True) in conn.calls


def test_select_readonly_wraps_protocol_errors():
    session = _session()
    conn = StubConn()

    def _boom(folder, readonly=False):
        raise imaplib.IMAP4.error("SELECT failed")

    conn.select = _boom
    with pytest.raises(session.ImapFetchError):
        session.select_readonly(conn, "INBOX")


def test_select_readonly_wraps_non_ok_status():
    session = _session()
    conn = StubConn(select_result=("NO", [b"nope"]))
    with pytest.raises(session.ImapFetchError):
        session.select_readonly(conn, "INBOX")


# --- 3. 文件夹候选 -------------------------------------------------------------

def test_list_folders_parses_display_names():
    session = _session()
    conn = StubConn(list_data=[
        b'(\\HasNoChildren) "/" "INBOX"',
        b'(\\HasChildren) "/" "Archive"',
        b'(\\HasNoChildren) "/" "INBOX"',
    ])
    assert session.list_folders(conn) == ["INBOX", "Archive"]


def test_list_folders_returns_empty_list_when_listing_fails():
    session = _session()
    conn = StubConn()

    def _boom():
        raise imaplib.IMAP4.error("LIST failed")

    conn.list = _boom
    assert session.list_folders(conn) == []


def test_list_folders_skips_unparsable_entries():
    session = _session()
    conn = StubConn(list_data=[b"NIL", b'(\\HasNoChildren) "/" "INBOX"'])
    assert session.list_folders(conn) == ["INBOX"]


# --- 4. 一次会话拿文件夹候选（probe_folders）-----------------------------------

def test_probe_folders_connects_logs_in_lists_and_logs_out(monkeypatch):
    session = _session()
    conn = StubConn(capabilities=("ID",),
                    list_data=[b'(\\HasNoChildren) "/" "INBOX"'])
    monkeypatch.setattr(session, "connect", lambda host, port: conn)

    names = session.probe_folders("imap.example.com", "a@example.com", "code", 993)

    assert names == ["INBOX"]
    kinds = [call[0] for call in conn.calls]
    assert kinds[0] == "login"
    assert "list" in kinds
    assert kinds[-1] == "logout", "连完必须登出（不留半开会话）"
    assert "select" not in kinds, "列文件夹不该打开文件夹、更不该读邮件"


def test_probe_folders_propagates_connect_failure(monkeypatch):
    session = _session()

    def _boom(host, port):
        raise session.ImapFetchError("连接超时：imap.example.com:993 在 15 秒内无响应")

    monkeypatch.setattr(session, "connect", _boom)
    with pytest.raises(session.ImapFetchError):
        session.probe_folders("imap.example.com", "a@example.com", "code", 993)
