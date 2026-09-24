# -*- coding: utf-8 -*-
"""IMAP 会话层：连接、TLS 上下文、登录（含 IMAP `ID` 声明）、只读打开文件夹、列文件夹。

2026-09-24「邮箱配置体验」批从 `tools/imap_fetch.py` 下沉到这里：那边只剩
「取样与解析」，会话纪律（只读、超时口径、TLS 策略、身份声明）集中一处，可独立测试。

三段背景都是真踩过的坑：

- **超时**：`IMAP4_SSL(..., timeout=N)` 由 imaplib 交给 `socket.create_connection`
  落在 socket 上，整段会话（connect / login / select / fetch）共用同一个超时；
- **TLS**：Python ≤3.11 的 imaplib 默认上下文**不校验服务器证书**，授权码在传输层
  可被中间人截获——所以显式建严格上下文（策略本体在 `jobws_core.tls_policy`）；
- **IMAP `ID`（RFC 2971）**：163 / 126 / yeah.net 要求客户端在 `SELECT` **之前**
  声明身份，否则服务端直接回 `Unsafe Login`。对方没声明 `ID` 能力就不发；发失败
  只留一条日志——身份声明是「让对方愿意放行」，不该变成新的失败点。

错误类型沿用 `ImapFetchError` 这个名字：Web 路由、CLI 与既有测试都按它捕获，
改名等于把整条链路的改名风险摊给调用方。
"""

from __future__ import annotations

import imaplib
import logging
import re
import socket
import ssl

from jobws_core import mail_providers, tls_policy

logger = logging.getLogger(__name__)

DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
SOCKET_TIMEOUT = 15


class ImapFetchError(Exception):
    """拉取失败的用户可读原因（消息里不包含凭证）。

    可选 `code` 是我们的错误码（如 `imap.unsafeLogin` / `imap.authFailed`），
    归不出种类时为 None——调用方据此决定给用户的下一步，而不是照抄服务端原文。
    """

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def ssl_context():
    """显式 TLS 上下文：默认严格校验（系统证书库 + 主机名）。

    默认严格 → 证书库不可用时**默认拒绝连接** → 仅当 `JOBWS_IMAP_TLS=insecure`
    时显式降级（降级必须由用户主动配置，风险写在错误消息里）。
    """
    try:
        return tls_policy.outbound_ssl_context("IMAP 拉取", tls_policy.IMAP_ENV_VAR)
    except tls_policy.TlsPolicyError as exc:
        # 调用方统一按 ImapFetchError 处理，故此处做类型转译
        raise ImapFetchError(str(exc))


def connect(host, port, timeout=SOCKET_TIMEOUT):
    """建立会话；`timeout` 落在 socket 上，全程沿用。"""
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=timeout,
                                 ssl_context=ssl_context())
    except ssl.SSLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            # 与「地址写错」是两回事：证书不被信任可能是自签名也可能是劫持，两条路的
            # 答案都不是关校验——所以消息里明确不给降级出口
            raise ImapFetchError(
                "证书校验失败：系统证书库不信任 %s 的证书（可能自签名，也可能被"
                "劫持）。不要为它关闭校验。" % host)
        raise ImapFetchError(
            "TLS 握手失败：%s（检查服务器地址与端口，SSL 端口通常为 993）" % exc)
    except socket.timeout:
        # 坏地址 / 丢包的服务器：要落在「15 秒内给人话」上，而不是等系统 TCP 超时
        raise ImapFetchError("连接超时：%s:%s 在 %d 秒内无响应" % (host, port, timeout))
    except OSError as exc:
        raise ImapFetchError("无法连接 %s:%s：%s" % (host, port, exc))
    return conn


def send_id(conn, version=""):
    """声明客户端身份（RFC 2971）；不支持或失败都返回 False，且**不抛错**。

    只在服务器声明了 `ID` 能力时发送——对着不支持的服务器发未知命令，
    轻则被忽略，重则让会话进入异常状态，没必要冒这个险。
    """
    capabilities = getattr(conn, "capabilities", ()) or ()
    normalised = set()
    for item in capabilities:
        if isinstance(item, bytes):
            item = item.decode("ascii", errors="replace")
        normalised.add(str(item).upper())
    if "ID" not in normalised:
        return False

    try:
        conn._simple_command("ID", mail_providers.id_payload(version))
        return True
    except Exception as exc:  # noqa: BLE001 —— 身份声明失败不许影响拉取
        logger.info("IMAP ID 声明失败（继续使用既有会话）：%s", exc)
        return False


def login(conn, user, password, version=""):
    """登录，统一错误口径（消息不含密码），随后立即声明身份。

    `ID` 紧跟 login：它对 `SELECT` 是前置条件（163 系），而这是唯一一处
    「登录完成、尚未开文件夹」的时机。
    """
    try:
        conn.login(user, password)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError(
            "登录失败：%s（多数邮箱的 IMAP 需要单独开启并使用授权码，"
            "不是网页登录密码）" % exc,
            code=mail_providers.classify_login_error(exc))
    send_id(conn, version)
    return conn


def select_readonly(conn, folder):
    """只读打开文件夹（`readonly=True` 是红线，不随任何重构松动）。"""
    try:
        typ, data = conn.select(folder or DEFAULT_FOLDER, readonly=True)
    except imaplib.IMAP4.error as exc:
        raise ImapFetchError("打开文件夹失败：%s" % exc)
    if typ != "OK":
        raise ImapFetchError("打开文件夹失败：%s" % (data,))
    return data


def list_folders(conn):
    """列出可选文件夹名（只读 `LIST`）；失败或解析不出时返回空列表。

    这是「测试连接」之后的锦上添花：列不出来界面就退回自由输入，
    所以不抛错、只留一条 info 日志。
    """
    try:
        typ, data = conn.list()
    except (imaplib.IMAP4.error, OSError) as exc:
        logger.info("列出文件夹失败（退回自由输入）：%s", exc)
        return []
    if typ != "OK" or not data:
        return []

    names = []
    for item in data:
        if isinstance(item, tuple) and item:
            item = item[0]
        if not item:
            continue
        text = (item.decode("utf-8", errors="replace")
                if isinstance(item, bytes) else str(item))
        # 形如 `(\HasNoChildren) "/" "INBOX"`：取末尾那个被引号包住的显示名
        match = re.search(r'"([^"]*)"\s*$', text.strip())
        if not match:
            continue
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)
    return names


def logout(conn):
    """登出；失败不影响结果（连接已用完），但按「禁静默吞错」留一条日志。"""
    try:
        conn.logout()
    except Exception as exc:  # noqa: BLE001 —— 登出失败不该改变任何结论
        logger.warning("IMAP logout 失败：%s", exc)


def probe_folders(host, user, password, port=DEFAULT_PORT):
    """连一次 → 登录（含 ID 声明）→ 只读 `LIST` → 登出；返回文件夹名列表。

    会话级编排（与 `select_readonly` 同层，不含业务判断）：凭证是否齐全由调用方
    先校验。列不出文件夹由 `list_folders` 退化成空列表——那不是失败，是"没有候选"。
    参数顺序与 `imap_fetch.test_connection` 一致，调用方不用记两套。
    """
    conn = connect(host, port)
    try:
        login(conn, user, password)
        return list_folders(conn)
    except socket.timeout:
        raise ImapFetchError("操作超时：%s 在 %d 秒内没有响应" % (host, SOCKET_TIMEOUT))
    except ssl.SSLError as exc:
        raise ImapFetchError("TLS 连接异常：%s" % exc)
    except OSError as exc:
        raise ImapFetchError("网络异常：%s" % exc)
    finally:
        logout(conn)
