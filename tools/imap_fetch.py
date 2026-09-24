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

import imap_session
# mail_providers：服务器推断的预设表已下沉到领域包；tls_policy 仅在既有测试的
# 打桩路径上还需要存在（`tests/test_imap_fetch.py` 会 monkeypatch
# `imap_fetch.tls_policy._builtin_ca_file`），实现本身已搬到 imap_session。
from jobws_core import mail_providers, tls_policy  # noqa: F401
from email import message_from_bytes
from email.header import decode_header
# 正文 / ICS 的抽取与截断已下沉到领域包（批 9）：按原名再导出，调用方不受影响。
from jobws_core.mail_text import (MAX_BODY_CHARS, extract_body, extract_calendar,
                                  smart_truncate)

logger = logging.getLogger(__name__)

BODY_CHUNK_BYTES = 512 * 1024  # 单封拉取上限（审计 P0-4）：分段 BODY.PEEK[]<0.N>；内存上界 = limit × 此值

# 端口 / 文件夹 / 超时的默认值与会话层同源（那边是唯一真源）
DEFAULT_PORT = imap_session.DEFAULT_PORT
DEFAULT_FOLDER = imap_session.DEFAULT_FOLDER
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
# 时间窗天数上限：再大既没意义（邮箱里没有 10 年前的招聘邮件），又会溢出成 500
MAX_SINCE_DAYS = 3650
# 默认只搜最近 30 天：几千封的邮箱里「最近 20 封」常常全是广告，服务端按时间窗
# 搜索才能把「翻列表找招聘邮件」变成「拉回来再看」
DEFAULT_SINCE_DAYS = 30

# IMAP 日期字面量用的英文月份（不用 strftime，理由见 _imap_since）
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SOCKET_TIMEOUT = imap_session.SOCKET_TIMEOUT

# 服务商预设表与服务器推断已下沉到 `jobws_core/mail_providers.py`（本批）：
# 那边多了「要不要授权码 / 要不要先发 IMAP ID / 官方指引」几列。
# 这里保留同名入口，只为不让既有调用方（routers/imap.py、CLI）与既有测试断链。
guess_server = mail_providers.guess_server

# 会话层入口：错误类型与动作再从会话模块导出一次，调用方按原名使用。
# `probe_folders` 也在其中——设置页的文件夹候选下拉按需调它（用户点开才连一次）。
ImapFetchError = imap_session.ImapFetchError
probe_folders = imap_session.probe_folders


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


# TLS 上下文与会话建立下沉到 imap_session；保留别名是因为既有测试直接打桩这两处
# （`tests/test_imap_fetch.py` 替换 `imap_fetch._connect`，并直接调 `_ssl_context`）。
_ssl_context = imap_session.ssl_context
_connect = imap_session.connect


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
    # 上限兜底：`date - timedelta(10**8)` 的 OverflowError 会绕过 ImapFetchError 成 500
    days = min(days, MAX_SINCE_DAYS)
    d = datetime.date.today() - datetime.timedelta(days=days)
    return "%02d-%s-%04d" % (d.day, _MONTHS[d.month - 1], d.year)


_login = imap_session.login


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
        data = imap_session.select_readonly(conn, folder)
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
            # 登出失败不影响结果（连接已用完），但按「禁静默吞错」留一条日志
            logger.warning("IMAP logout 失败：%s", exc)


def _fetch_recent(conn, folder, since_days, limit):
    """在已登录连接上取最近 limit 封（最新在前）——只读命令，保证同 fetch_messages。"""
    imap_session.select_readonly(conn, folder)

    # 时间窗在服务端过滤（SINCE 是 ASCII 安全的条件）——只取「最近 N 封」防广告淹没。
    criteria = ["SINCE", _imap_since(since_days)] if since_days else ["ALL"]
    try:
        # UID SEARCH（不是 SEARCH）：拿到的是稳定 UID——序号会在会话期间因邮箱变化重排，
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
