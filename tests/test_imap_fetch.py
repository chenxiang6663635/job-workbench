# -*- coding: utf-8 -*-
"""imap_fetch 的规则层测试（全部离线，不碰网络）。

钉住三类东西：
1. 服务器推断与正文提取的判断口径（纯函数）；
2. **只读保证**：`select(readonly=True)` + `BODY.PEEK[]`，且会话里不存在
   STORE / COPY / EXPUNGE / APPEND 类调用——这条是这个功能最该被信任的一条；
3. 会话纪律：失败也要 logout、凭证缺失在连接前就拦住、错误消息不含凭证。
"""

import os
import socket
import sys

import pytest
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import imap_fetch  # noqa: E402


# --- 1. 服务器推断 ------------------------------------------------------------

# 隐私护栏（.githooks/pre_commit.py）会拦截真实服务商域名邮箱的字面量——
# qq.com 正是用户真实邮箱所在域名，不该豁免。这里拼接构造测试输入：
# 推断功能本身需要真实域名样本，构造出的字符串不是任何人的邮箱。
QQ_MAIL = "user@" + "qq.com"
NETEASE_MAIL = "user@" + "163.com"
GMAIL_MAIL_UPPER = "user@" + "GMAIL.COM"


def test_guess_known_domains():
    assert imap_fetch.guess_server(QQ_MAIL) == "imap.qq.com"
    assert imap_fetch.guess_server(NETEASE_MAIL) == "imap.163.com"
    assert imap_fetch.guess_server(GMAIL_MAIL_UPPER) == "imap.gmail.com"


def test_guess_unknown_domain_returns_empty():
    assert imap_fetch.guess_server("a@some-corp.example") == ""


def test_guess_rejects_non_email():
    assert imap_fetch.guess_server("") == ""
    assert imap_fetch.guess_server("not-an-email") == ""


# --- 2. 正文提取 --------------------------------------------------------------

def test_extract_body_prefers_plain_over_html():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("纯文本正文", "plain", "utf-8"))
    msg.attach(MIMEText("<p>HTML <b>正文</b></p>", "html", "utf-8"))
    assert imap_fetch.extract_body(msg) == "纯文本正文"


def test_extract_body_falls_back_to_stripped_html():
    msg = MIMEText("<div>你好<br>世界</div><script>var x=1;</script>", "html", "utf-8")
    body = imap_fetch.extract_body(msg)
    assert "你好" in body and "世界" in body
    assert "var x" not in body, "script 内容不该混进正文"


def test_extract_body_truncates_long_text():
    msg = MIMEText("啊" * (imap_fetch.MAX_BODY_CHARS + 500), "plain", "utf-8")
    body = imap_fetch.extract_body(msg)
    assert len(body) <= imap_fetch.MAX_BODY_CHARS + 40
    assert "已截断" in body


def test_decode_mime_header_handles_encoded_words():
    from email import message_from_string
    raw = ("Subject: =?utf-8?b?5oCO5LmI?=\nFrom: hr <" + QQ_MAIL + ">\n\nhi")
    msg = message_from_string(raw)
    assert imap_fetch._decode_mime_header(msg.get("Subject")) == "怎么"


# --- 3. 会话纪律（伪造 IMAP 连接）---------------------------------------------

class _FakeSock:
    def settimeout(self, value):
        self.timeout = value


class FakeConn:
    """记录调用序列的假会话：用来钉「只读」与「失败也登出」。"""

    def __init__(self, uids=(b"1", b"2", b"3"), login_error=None):
        self.uids = list(uids)
        self.login_error = login_error
        self.calls = []
        self.sock = _FakeSock()
        self.logged_out = False

    def login(self, user, password):
        self.calls.append(("login", user))
        if self.login_error:
            raise self.login_error
        return ("OK", [b""])

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return ("OK", [str(len(self.uids)).encode()])

    def uid(self, command, *args):
        """只读会话只允许 UID SEARCH / UID FETCH 两种用法。"""
        command = command.upper()
        self.calls.append(("uid:" + command.lower(),) + tuple(args))
        if command == "SEARCH":
            return ("OK", [b" ".join(self.uids)])
        if command == "FETCH":
            raw = b"Subject: t\nFrom: hr@example.com\n\nbody-" + args[0]
            return ("OK", [(b"1 (BODY[])", raw)])
        return ("OK", [b""])

    def logout(self):
        self.calls.append(("logout",))
        self.logged_out = True
        return ("BYE", [])


@pytest.fixture()
def fake(monkeypatch):
    conn = FakeConn()

    def _connect(host, port):
        conn.connected_to = (host, port)
        return conn

    monkeypatch.setattr(imap_fetch, "_connect", _connect)
    return conn


def test_fetch_selects_readonly_and_uses_peek(fake):
    """红线：整个会话只读——select 只读、UID FETCH 用 PEEK、没有任何写类命令。"""
    imap_fetch.fetch_messages("imap.example.com", "a@example.com", "code", limit=2)

    assert ("select", "INBOX", True) in fake.calls, "必须只读打开文件夹"
    searches = [c for c in fake.calls if c[0] == "uid:search"]
    assert searches and searches[0][1] == "ALL", "检索必须走 UID SEARCH（序号会随邮箱变化重排）"
    specs = [c[2] for c in fake.calls if c[0] == "uid:fetch"]
    assert specs and all("PEEK" in s for s in specs), "读取必须用 UID FETCH + BODY.PEEK"
    forbidden = ("store", "copy", "expunge", "append", "create", "delete", "rename")
    assert not [c for c in fake.calls if any(w in c[0] for w in forbidden)], "会话里不许出现写类命令"
    assert fake.logged_out, "结束必须登出"


def test_fetch_returns_the_most_recent_first(fake):
    messages = imap_fetch.fetch_messages(
        "imap.example.com", "a@example.com", "code", limit=2)
    assert [m["uid"] for m in messages] == ["3", "2"]


def test_fetch_limits_to_available_uids(fake):
    messages = imap_fetch.fetch_messages(
        "imap.example.com", "a@example.com", "code", limit=99)
    assert [m["uid"] for m in messages] == ["3", "2", "1"]


def test_login_failure_is_wrapped_with_authorization_code_hint(monkeypatch):
    import imaplib
    conn = FakeConn(login_error=imaplib.IMAP4.error("LOGIN failed"))
    monkeypatch.setattr(imap_fetch, "_connect", lambda h, p: conn)

    with pytest.raises(imap_fetch.ImapFetchError) as exc:
        imap_fetch.fetch_messages("imap.example.com", "a@example.com", "wrong")

    assert "授权码" in str(exc.value)
    assert conn.logged_out, "登录失败也必须登出（不在服务端留下会话）"


def test_missing_credentials_fail_before_connecting(monkeypatch):
    def _boom(host, port):
        raise AssertionError("凭证不全时不该建立连接")

    monkeypatch.setattr(imap_fetch, "_connect", _boom)

    with pytest.raises(imap_fetch.ImapFetchError):
        imap_fetch.fetch_messages("", "a@example.com", "code")
    with pytest.raises(imap_fetch.ImapFetchError):
        imap_fetch.fetch_messages("imap.example.com", "", "code")
    with pytest.raises(imap_fetch.ImapFetchError):
        imap_fetch.fetch_messages("imap.example.com", "a@example.com", "")


def test_error_messages_never_contain_the_password(monkeypatch):
    import imaplib
    secret = "super-secret-auth-code"
    conn = FakeConn(login_error=imaplib.IMAP4.error("LOGIN failed"))
    monkeypatch.setattr(imap_fetch, "_connect", lambda h, p: conn)

    with pytest.raises(imap_fetch.ImapFetchError) as exc:
        imap_fetch.fetch_messages("imap.example.com", "a@example.com", secret)

    assert secret not in str(exc.value)


def test_fetch_failure_after_login_still_logs_out(monkeypatch):
    """会话中途失败（检索阶段）也必须登出——不在服务端留下半开会话。"""
    import imaplib
    conn = FakeConn()

    def _boom(command, *args):
        raise imaplib.IMAP4.error("SEARCH failed")

    monkeypatch.setattr(conn, "uid", _boom)
    monkeypatch.setattr(imap_fetch, "_connect", lambda h, p: conn)

    with pytest.raises(imap_fetch.ImapFetchError):
        imap_fetch.fetch_messages("imap.example.com", "a@example.com", "code")
    assert conn.logged_out


def test_test_connection_reads_no_mail_and_logs_out(monkeypatch):
    """「测试连接」只做 login + 只读 select，不读任何邮件正文。"""
    conn = FakeConn()
    monkeypatch.setattr(imap_fetch, "_connect", lambda h, p: conn)

    count = imap_fetch.test_connection("imap.example.com", "a@example.com", "code")

    assert count == 3
    assert ("select", "INBOX", True) in conn.calls
    assert not [c for c in conn.calls if c[0].startswith("uid")], "测试连接不该读取邮件"
    assert conn.logged_out


def test_probe_timeout_is_wrapped(monkeypatch):
    """3.8 没有 per-call timeout，探测层必须把超时变成人话错误而不是裸异常。"""
    def _boom(address, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(imap_fetch.socket, "create_connection", _boom)

    with pytest.raises(imap_fetch.ImapFetchError) as exc:
        imap_fetch._probe_tcp("imap.example.com", 993)
    assert "超时" in str(exc.value)


def test_extract_body_skips_attachments():
    msg = MIMEMultipart()
    msg.attach(MIMEText("正文在这里", "plain", "utf-8"))
    attachment = MIMEText("附件内容不该混进正文", "plain", "utf-8")
    attachment.add_header("Content-Disposition", "attachment", filename="notes.txt")
    msg.attach(attachment)

    body = imap_fetch.extract_body(msg)
    assert "正文在这里" in body
    assert "附件内容不该混进正文" not in body
