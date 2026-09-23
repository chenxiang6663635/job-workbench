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

超时口径（2026-09-14 基线升到 3.12 后收紧）：连接直接用
`IMAP4_SSL(host, port, timeout=SOCKET_TIMEOUT)`——该参数经
`socket.create_connection` 落到 socket 上，**整段会话（connect / login / select /
fetch）共用同一个超时**，不再需要先前那一步「先探一条 TCP 再建连」的 3.8 妥协
（issue #50 S1 的代价：一次会话两条连接）。
"""

from __future__ import annotations

import datetime
import imaplib
import logging
import re
import socket
import ssl
from jobws_core import tls_policy
from email import message_from_bytes
from email.header import decode_header
# 正文 / ICS 的抽取与截断已下沉到领域包（批 9）：按原名再导出，调用方不受影响。
from jobws_core.mail_text import (MAX_BODY_CHARS, extract_body, extract_calendar,
                                  smart_truncate)

logger = logging.getLogger(__name__)

BODY_CHUNK_BYTES = 512 * 1024  # 单封拉取上限（审计 P0-4）：分段 BODY.PEEK[]<0.N>；内存上界 = limit × 此值

DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
# 默认只搜最近 30 天：几千封的邮箱里「最近 20 封」常常全是广告，
# 按时间窗在服务端搜索，才能把「翻列表找招聘邮件」变成「拉回来再看」
DEFAULT_SINCE_DAYS = 30

# IMAP 日期字面量用的英文月份（不用 strftime，理由见 _imap_since）
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
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


def _clean_message_id(raw):
    """规范化 Message-ID：去 `<>`（头字段包围符不属于 ID 本体）并 strip。

    深链（Gmail 的 rfc822msgid 搜索）要求不带尖括号的原始值；
    mails.csv 的「消息id」列存的就是这里出来的规范值。
    """
    text = (raw or "").strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text


def _ssl_context():
    """显式 TLS 上下文：默认严格校验（系统证书库 + 主机名）。

    策略本体在 `tools/tls_policy.py`——与三处 HTTP 出网（provider / resume /
    jobs）共用同一份判定（issue #59），本函数只做「领域错误类型」的适配：
    默认严格 → 证书库不可用时**默认拒绝连接** → 仅当 `JOBWS_IMAP_TLS=insecure`
    时显式降级（降级必须由用户主动配置，风险写在错误消息里）。

    为什么不走解释器默认：Python ≤3.11 的 imaplib 默认上下文**不校验服务器
    证书**，授权码在传输层可被中间人截获（issue #50 S2）。
    """
    try:
        return tls_policy.outbound_ssl_context("IMAP 拉取", tls_policy.IMAP_ENV_VAR)
    except tls_policy.TlsPolicyError as exc:
        # 调用方（routers/imap.py、CLI）统一按 ImapFetchError 处理，
        # 所以这里把策略异常换成带邮件语境的错误类型。
        raise ImapFetchError(str(exc))


def _connect(host, port):
    """建立会话：connect 与后续命令共用一个超时。

    `timeout=` 由 imaplib 交给 `socket.create_connection`，落在 socket 上——
    因此 login / select / fetch 全程沿用，不再需要连接后单独 `settimeout()`，
    也不需要 3.8 时代的探测连接（见模块 docstring 的超时口径）。
    TLS 校验策略见 `_ssl_context`。
    """
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=SOCKET_TIMEOUT,
                                 ssl_context=_ssl_context())
    except ssl.SSLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            # 与「地址写错」是两回事：证书不被信任可能是自签名，也可能是劫持——
            # 两条路的答案都不是关校验，所以消息里明确不给降级出口
            raise ImapFetchError(
                "证书校验失败：系统证书库不信任 %s 的证书（可能自签名，也可能被"
                "劫持）。不要为它关闭校验。" % host)
        raise ImapFetchError(
            "TLS 握手失败：%s（检查服务器地址与端口，SSL 端口通常为 993）" % exc)
    except socket.timeout:
        # 坏地址 / 被丢包的服务器：必须落在「15 秒内给人话」这条承诺上，
        # 而不是等到系统 TCP 超时（原先由探测连接保证，现在由 timeout= 保证）
        raise ImapFetchError("连接超时：%s:%s 在 %d 秒内无响应" % (host, port, SOCKET_TIMEOUT))
    except OSError as exc:
        raise ImapFetchError("无法连接 %s:%s：%s" % (host, port, exc))
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


def _imap_since(days):
    """IMAP SINCE 的日期字面量（dd-Mon-yyyy，如 13-Aug-2026）。

    不能用 strftime("%d-%b-%Y")：Windows 的 %b 跟随系统 locale，
    中文环境下会输出「13-8月-2026」这种非法月份，服务器直接报错。
    """
    try:
        days = max(1, int(days))
    except (TypeError, ValueError):
        days = DEFAULT_SINCE_DAYS
    d = datetime.date.today() - datetime.timedelta(days=days)
    return "%02d-%s-%04d" % (d.day, _MONTHS[d.month - 1], d.year)


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
        except Exception as exc:
            # 登出失败不影响调用方拿到的结果（连接已用完）；按「禁静默吞错」
            # 留一条日志，IST/服务器端异常时会体现在后端日志里。
            logger.warning("IMAP logout 失败：%s", exc)


def _fetch_recent(conn, folder, since_days, limit):
    """在已登录连接上取最近 limit 封（最新在前）——只读命令，保证同 fetch_messages。"""
    try:
        typ, data = conn.select(folder or DEFAULT_FOLDER, readonly=True)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError("打开文件夹失败：%s" % exc)
    if typ != "OK":
        raise ImapFetchError("打开文件夹失败：%s" % (data,))

    # 时间窗在服务端过滤（SINCE 是 ASCII 安全的条件）——只取「最近 N 封」防广告淹没。
    criteria = ["SINCE", _imap_since(since_days)] if since_days else ["ALL"]
    try:
        # UID SEARCH（不是 SEARCH）：拿到的是稳定 UID。
        # 序号（sequence number）在会话期间会因邮箱变化重排，
        # 用序号去 FETCH 有取到另一封邮件的风险。
        typ, data = conn.uid("SEARCH", *criteria)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError("检索邮件失败：%s" % exc)
    if typ != "OK":
        raise ImapFetchError("检索邮件失败：%s" % (data,))

    uids = data[0].split() if data and data[0] else []
    recent = uids[-limit:]  # 升序（旧→新）
    if not recent:
        return []

    # 批量 FETCH 一次取回（逐封要 N 个网络来回）；显式请求 UID——顺序对齐依赖服务器实现。
    seq = ",".join(uid.decode("ascii", errors="replace") for uid in recent)
    try:
        typ, fetched = conn.uid(
            "FETCH", seq, "(UID BODY.PEEK[]<0.%d>)" % BODY_CHUNK_BYTES)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError("读取邮件失败：%s" % exc)
    if typ != "OK":
        raise ImapFetchError("读取邮件失败：%s" % (fetched,))

    raw_by_uid = {}
    for item in fetched:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        match = re.search(rb"UID (\d+)", item[0])
        if match:
            raw_by_uid[match.group(1).decode("ascii")] = item[1]

    messages = []
    for uid in reversed(recent):  # 最新在前
        raw = raw_by_uid.get(uid.decode("ascii", errors="replace"))
        if raw is None:
            continue
        msg = message_from_bytes(raw)
        messages.append({
            "uid": uid.decode("ascii", errors="replace"),
            # Message-ID（批 4.5）：BODY.PEEK[] 已含 headers——供 mails 去重与 Gmail 深链。
            "messageId": _clean_message_id(msg.get("Message-ID")),
            "subject": _decode_mime_header(msg.get("Subject")),
            "from": _decode_mime_header(msg.get("From")),
            "date": (msg.get("Date") or "").strip(),
            "body": extract_body(msg),
            # 会议邀请的 ICS 原文（无则为空串）：解析优先级高于正文正则
            "calendar": extract_calendar(msg),
            # 分段拉取标注：raw 顶到上限即视为截断（大附件尾部被切，头与 ICS 在前段）
            "truncated": len(raw) >= BODY_CHUNK_BYTES,
        })
    return messages


def fetch_messages(host, user, password, port=DEFAULT_PORT, folder=DEFAULT_FOLDER,
                   limit=DEFAULT_LIMIT, since_days=DEFAULT_SINCE_DAYS):
    """只读拉取最近 `since_days` 天内的邮件（最新在前，最多 `limit` 封）。

    `since_days=0` 表示不限时间（取最近 limit 封）。
    返回 [{"uid", "messageId", "subject", "from", "date", "body", "calendar"}]——
    `calendar` 是会议邀请的 ICS 原文（无则空串），解析优先级高于正文正则。
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
        return _fetch_recent(conn, folder, since_days, limit)
    except socket.timeout:
        raise ImapFetchError("操作超时：%s 在 %d 秒内没有响应" % (host, SOCKET_TIMEOUT))
    except ssl.SSLError as exc:
        raise ImapFetchError("TLS 连接异常：%s" % exc)
    except OSError as exc:
        raise ImapFetchError("网络异常：%s" % exc)
    finally:
        try:
            conn.logout()
        except Exception as exc:
            # 同 test_connection：登出失败不影响结果，但留日志。
            logger.warning("IMAP logout 失败：%s", exc)
