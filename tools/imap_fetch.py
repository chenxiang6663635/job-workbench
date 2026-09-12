# -*- coding: utf-8 -*-
"""只读 IMAP 拉取：登录邮箱、取最近邮件、提取正文文本。

供 Web 路由（`web/backend/routers/imap.py`）与测试共用。设计边界（四条）：

1. **只读**：`select(readonly=True)`、fetch 用 `BODY.PEEK[]`（不置已读），
   全程不发信、不标注、不删除、不移动。
2. **无凭证落盘**：本模块不读写任何配置文件——凭证由调用方传入，
   存储归路由层（只存工作区本地 config/）。
3. **无后台连接**：纯函数式的「连接 → 取样 → 登出」，不存在定时器 / 轮询 /
   连接复用。什么时候连，完全由调用方的显式请求决定。
4. **纯标准库**：imaplib / email / html.parser，零第三方依赖。

错误口径：网络与协议异常统一包成 `ImapFetchError`（人话消息，绝不含凭证），
由调用方决定 HTTP 状态码。

Python 3.8 兼容说明：不传 `imaplib.IMAP4_SSL(timeout=...)`（3.9+ 才有）；
socket 超时在连接建立后由 `conn.sock.settimeout()` 覆盖后续命令。
"""

from __future__ import annotations

import imaplib
import re
import socket
import ssl
from email import message_from_bytes
from email.header import decode_header
from html.parser import HTMLParser

DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
# 单封邮件正文截断上限：列表预览用，防止把超大邮件整个打进响应
MAX_BODY_CHARS = 4000
SOCKET_TIMEOUT = 15

# 常见邮箱 IMAP 服务器推断表（用户可在配置里覆盖；未知域名返回空串让用户手填）
SERVER_GUESSES = {
    "qq.com": "imap.qq.com",
    "foxmail.com": "imap.qq.com",
    "163.com": "imap.163.com",
    "126.com": "imap.126.com",
    "yeah.net": "imap.yeah.net",
    "gmail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "aliyun.com": "imap.aliyun.com",
    "sina.com": "imap.sina.com",
    "sohu.com": "imap.sohu.com",
}


class ImapFetchError(Exception):
    """拉取失败的用户可读原因。消息里不包含凭证。"""


def guess_server(email_addr):
    """按邮箱域名推断 IMAP 服务器；未知域名返回空串（由用户手填）。"""
    if not email_addr or "@" not in email_addr:
        return ""
    domain = email_addr.rsplit("@", 1)[1].strip().lower()
    return SERVER_GUESSES.get(domain, "")


def _decode_mime_header(raw):
    """解码可能含 RFC 2047 编码词的主题 / 发件人。"""
    if not raw:
        return ""
    try:
        parts = []
        for text, charset in decode_header(raw):
            if isinstance(text, bytes):
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(text)
        return "".join(parts).strip()
    except Exception:
        return raw if isinstance(raw, str) else ""


class _HtmlTextExtractor(HTMLParser):
    """尽力而为的 HTML → 纯文本：跳过 script/style，块级标签折算换行。"""

    _BLOCK_TAGS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        HTMLParser.__init__(self)
        self._skip_depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self):
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def _html_to_text(html_text):
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html_text)
    except Exception:
        # 畸形 HTML 上解析器已尽力；真出错时退回粗剥标签
        return re.sub(r"<[^>]+>", " ", html_text)
    return parser.text()


def _part_text(part):
    """取单个 MIME part 的解码文本；无法解码时返回空串而非抛错。"""
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeError):
        return payload.decode("utf-8", errors="replace")


def extract_body(msg):
    """从 email.message.Message 提取正文纯文本。

    优先 text/plain；只有 HTML 时剥标签；两者都无则返回空串。
    超过 MAX_BODY_CHARS 截断并标注——列表预览不需要全文。
    """
    plain_parts = []
    html_parts = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        # 跳过附件（如 .txt 附件）：它的内容不是邮件正文，混进来会污染解析素材
        disposition = (part.get("Content-Disposition") or "").lower()
        if disposition.startswith("attachment"):
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain":
            plain_parts.append(_part_text(part))
        elif ctype == "text/html":
            html_parts.append(_part_text(part))

    if plain_parts:
        text = "\n".join(p.strip() for p in plain_parts if p.strip())
    elif html_parts:
        text = "\n".join(_html_to_text(h) for h in html_parts if h.strip())
    else:
        text = ""

    text = text.strip()
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n…（正文过长，已截断）"
    return text


def _probe_tcp(host, port):
    """带超时的 TCP 可达性探测。

    3.8 的 imaplib 不接受 timeout 参数（3.9+ 才有），若不做这一步，
    连接不可达主机时 `connect()` 可能在系统默认 TCP 超时前一直阻塞。
    """
    try:
        probe = socket.create_connection((host, port), timeout=SOCKET_TIMEOUT)
        probe.close()
    except socket.timeout:
        raise ImapFetchError("连接超时：%s:%s 在 %d 秒内无响应" % (host, port, SOCKET_TIMEOUT))
    except OSError as exc:
        raise ImapFetchError("无法连接 %s:%s：%s" % (host, port, exc))


def _connect(host, port):
    """建立会话。3.8 兼容：不传 imaplib 的 timeout 参数（3.9+ 才有）。

    SSL 上下文沿用解释器默认（3.8–3.11 为不校验系统证书库的宽松上下文，
    3.12 起改为系统证书校验）——不显式 `create_default_context()`，因为它在
    本机 Windows 上会触发证书库加载崩溃（与 provider.py 同一环境 bug，见其注释）。
    """
    _probe_tcp(host, port)
    try:
        conn = imaplib.IMAP4_SSL(host, port)
    except ssl.SSLError as exc:
        raise ImapFetchError(
            "TLS 握手失败：%s（检查服务器地址与端口，SSL 端口通常为 993）" % exc)
    except (socket.timeout, OSError) as exc:
        raise ImapFetchError("无法连接 %s:%s：%s" % (host, port, exc))
    # 连接建立后设 socket 超时，覆盖 login / select / fetch 全程
    sock = getattr(conn, "sock", None)
    if sock is not None:
        try:
            sock.settimeout(SOCKET_TIMEOUT)
        except Exception:
            pass
    return conn


def _check_credentials(host, user, password):
    """连接前的必需项校验；返回规范化后的 (host, user)。

    在建立任何连接**之前**拦住凭证缺失——不给服务器留半开会话。
    """
    host = (host or "").strip()
    user = (user or "").strip()
    if not host:
        raise ImapFetchError("服务器地址为空：可以在配置里手填，或填邮箱后按域名自动推断")
    if not user:
        raise ImapFetchError("邮箱地址为空")
    if not password:
        raise ImapFetchError("授权码为空：多数邮箱需要「IMAP 授权码」而不是登录密码")
    return host, user


def _check_port(port):
    """端口容错：非法值回落到默认 993。"""
    try:
        return int(port)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def _login(conn, user, password):
    """登录并统一错误口径（消息不含密码）。"""
    try:
        conn.login(user, password)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError(
            "登录失败：%s（多数邮箱的 IMAP 需要单独开启并使用授权码，"
            "不是网页登录密码）" % exc)


def test_connection(host, user, password, port=DEFAULT_PORT, folder=DEFAULT_FOLDER):
    """连接 → 登录 → 只读打开文件夹 → 登出；返回该文件夹邮件总数。

    与 fetch_messages 同一套只读纪律，且不读取任何邮件内容——
    供「测试连接」按钮验证凭证与服务器可用性。
    """
    host, user = _check_credentials(host, user, password)
    port = _check_port(port)

    conn = _connect(host, port)
    try:
        _login(conn, user, password)
        try:
            typ, data = conn.select(folder or DEFAULT_FOLDER, readonly=True)
        except imaplib.IMAP4.error as exc:
            raise ImapFetchError("打开文件夹失败：%s" % exc)
        if typ != "OK":
            raise ImapFetchError("打开文件夹失败：%s" % (data,))
        count = 0
        if data and data[0]:
            try:
                count = int(data[0])
            except (TypeError, ValueError):
                count = 0
        return count
    except socket.timeout:
        raise ImapFetchError("操作超时：%s 在 %d 秒内没有响应" % (host, SOCKET_TIMEOUT))
    except ssl.SSLError as exc:
        raise ImapFetchError("TLS 连接异常：%s" % exc)
    except OSError as exc:
        raise ImapFetchError("网络异常：%s" % exc)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def fetch_messages(host, user, password, port=DEFAULT_PORT, folder=DEFAULT_FOLDER,
                   limit=DEFAULT_LIMIT):
    """只读拉取最近 `limit` 封邮件，最新在前。

    返回 [{"uid", "subject", "from", "date", "body"}]。
    只读保证：`select(readonly=True)` + `BODY.PEEK[]`，且不执行任何
    STORE / COPY / EXPUNGE 类命令；每次调用独立连接、结束即 logout。
    """
    host, user = _check_credentials(host, user, password)

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    port = _check_port(port)

    conn = _connect(host, port)
    try:
        _login(conn, user, password)

        try:
            typ, data = conn.select(folder or DEFAULT_FOLDER, readonly=True)
        except imaplib.IMAP4.error as exc:
            raise ImapFetchError("打开文件夹失败：%s" % exc)
        if typ != "OK":
            raise ImapFetchError("打开文件夹失败：%s" % (data,))

        try:
            # UID SEARCH（不是 SEARCH）：拿到的是稳定 UID。
            # 序号（sequence number）在会话期间会因邮箱变化重排，
            # 用序号去 FETCH 有取到另一封邮件的风险。
            typ, data = conn.uid("SEARCH", "ALL")
        except imaplib.IMAP4.error as exc:
            raise ImapFetchError("检索邮件失败：%s" % exc)
        if typ != "OK":
            raise ImapFetchError("检索邮件失败：%s" % (data,))

        uids = data[0].split() if data and data[0] else []
        messages = []
        for uid in reversed(uids[-limit:]):
            try:
                # UID FETCH + BODY.PEEK[]：按稳定 UID 读取，且不置 \Seen
                typ, fetched = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            except imaplib.IMAP4.error as exc:
                raise ImapFetchError("读取邮件失败：%s" % exc)
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            msg = message_from_bytes(fetched[0][1])
            messages.append({
                "uid": uid.decode("ascii", errors="replace"),
                "subject": _decode_mime_header(msg.get("Subject")),
                "from": _decode_mime_header(msg.get("From")),
                "date": (msg.get("Date") or "").strip(),
                "body": extract_body(msg),
            })
        return messages
    except socket.timeout:
        raise ImapFetchError("操作超时：%s 在 %d 秒内没有响应" % (host, SOCKET_TIMEOUT))
    except ssl.SSLError as exc:
        raise ImapFetchError("TLS 连接异常：%s" % exc)
    except OSError as exc:
        raise ImapFetchError("网络异常：%s" % exc)
    finally:
        try:
            conn.logout()
        except Exception:
            pass
