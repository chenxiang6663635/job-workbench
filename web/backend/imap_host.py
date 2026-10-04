# -*- coding: utf-8 -*-
"""IMAP host 的形状校验（issue #50 A1）：保存前与使用前走同一道关。

2026-10-04（#203 收口子任务 C）自 `routers/imap.py` 原样拆出：形状判定与路由
编排零耦合，拆走让 imap.py 回到规模预算内。**行为不变**——原来的长注释是资产
（它们解释了「为什么是三个 code」与「为什么必须 NFKC 归一化」），一并搬来、
逐字保留。
"""

from __future__ import annotations

import socket
import unicodedata

from apierror import ApiError

# DNS 名字的通用上限（RFC 1035：253 个字符）
MAX_HOST_LEN = 253


def is_ipv6_literal(host):
    """是不是 IPv6 字面量——含冒号但**不是** host:port。

    认三种写法：`[::1]`、裸 `::1`，以及带作用域标识的 `fe80::1%eth0`
    （`inet_pton` 不认 `%eth0`，剥掉再判——否则合法地址会被误报成
    "端口请填另一栏"）。
    """
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    candidate = candidate.split("%", 1)[0]
    try:
        socket.inet_pton(socket.AF_INET6, candidate)
        return True
    except (OSError, ValueError):
        return False


def check_host_shape(host):
    """使用前的 host 形状校验（issue #50 A1），返回原值。

    为什么是"使用前"而不只是"保存时"：保存校验是后加的，老配置里可能已经存着
    坏值；而且留空 host 时推断出来的值也该走同一道关。坏值最终都会在 `_connect`
    里变成"连不上 993 端口"——那句话对用户没有任何指向性，真正的原因（把
    `https://` 或 `host:port` 整段粘了进来）必须在**换得出正确说法的地方**报出来。

    分三个 code 而不是一个通用 code：三种形状问题的**出路不一样**（去掉协议头 /
    端口填另一栏 / 只填主机名），合成一句话等于把可操作的指引磨成一句废话，
    英文界面也只能渲染成同一段含糊文案。

    形状判定先做 **NFKC 归一化**：中文输入法下 `imap.qq.com：993`（全角冒号）
    是一敲就出来的形态，ASCII 判定看不住它，结果就退回到"连接期一句连不上"。
    归一化**只用于判定**，落盘与响应里仍是用户输入的原值。
    """
    probe = unicodedata.normalize("NFKC", host)
    if len(probe) > MAX_HOST_LEN:
        raise ApiError(422, "imap.hostTooLong",
                       "服务器地址过长（%d 字符，上限 %d）：只填主机名，不要带路径"
                       % (len(probe), MAX_HOST_LEN),
                       length=len(probe))
    if "://" in probe:
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不要带协议头：去掉 http:// 或 https://，"
                       "只填主机名（如 imap.qq.com）")
    if "/" in probe:
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不能含斜杠：只填主机名，路径不要写进来")
    if any(ch.isspace() for ch in probe):
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不能含空格：请检查是否多粘了一段")
    if ":" in probe and not is_ipv6_literal(probe):
        raise ApiError(422, "imap.hostPortInline",
                       "端口请填在「端口」栏：地址里不要写成 host:port"
                       "（例如 imap.qq.com:993 应拆成两栏）")
    return host
