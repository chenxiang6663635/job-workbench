# -*- coding: utf-8 -*-
"""出网目标守卫：只让 http(s) 指向**公网**地址（CodeQL `py/full-ssrf`）。

为什么需要（缺陷单 #2）：`POST /api/jobs/fetch-jd` 把用户粘贴的链接交给服务端
去取，而此前只校验 `startswith("http://"|"https://")`。于是
`http://169.254.169.254/latest/meta-data/`（云元数据）、`http://127.0.0.1:<port>/`
（本机自己的 API）都能被当成"JD 链接"取回来——SSRF 的标准形状。

为什么放 core 而不是 web：任何"取用户给的 URL"的入口（Web / 将来 CLI / MCP）
都该走同一道闸（四端同源）。这里是**纯判据**，除 DNS 解析外没有副作用。

三条边界说明（不装作比实际更强）：

1. 检查在**发请求前**做，解析与真正连接之间仍有 TOCTOU 窗口（DNS rebinding）——
   彻底解法是把解析结果 pin 到连接上（自建 socket），成本远大于本工具的威胁模型
   （本地单用户）；与 S2 的 TOCTOU 同一口径：如实说明，不假装消除。
2. 只判**地址**，不判内容：公网地址也能返回恶意 HTML，那是解析侧的事。
3. 端口不设限（JD 页面可能在非标端口），地址段才是 SSRF 的关键面。
"""

from __future__ import print_function

import ipaddress
import socket
import urllib.parse

# 只允许的协议：http(s)。file / ftp / gopher 这些协议本身就是 SSRF 的经典载荷。
ALLOWED_SCHEMES = ("http", "https")

# 拒绝原因（稳定标识，供前端/日志分类；不要改成会变的中文）
REASON_SCHEME = "scheme"          # 非 http(s)
REASON_URL = "url"                # URL 本身畸形（端口非数字/越界、方括号未闭合）
REASON_HOST = "host"              # 取不到主机名
REASON_CREDENTIALS = "credentials"  # 带 userinfo（可伪造 hostname 的观感）
REASON_ADDRESS = "address"        # 解析结果落在内网/本机/保留段
REASON_RESOLVE = "resolve"        # 解析失败

DEFAULT_PORTS = {"http": 80, "https": 443}

# `ipaddress` 的标志位**不覆盖**的保留段，显式列出（比依赖标准库版本更可预测）：
# - 100.64.0.0/10   RFC 6598 运营商级 NAT（`is_private` 在 3.12 上不认它）
# - 192.0.0.0/24    IETF 协议保留
# - 198.18.0.0/15   基准测试
# - 2002::/16       6to4（内嵌 IPv4，可指向内网）
_EXTRA_BLOCKED = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("2002::/16"),
)


class OutboundBlocked(RuntimeError):
    """目标被守卫拒绝。`reason` / `host` 都是**可渲染**的稳定值。"""

    def __init__(self, reason, host="", url=""):
        self.reason = reason
        self.host = host or ""
        self.url = url or ""
        super(OutboundBlocked, self).__init__(
            "出网目标被拒绝（%s）：%s" % (reason, self.host or "(无主机名)"))


def blocked_address(ip):
    """这个 IP 是否属于"不该由服务端去连"的段。

    覆盖：回环 / 私网（含 10/8、172.16/12、192.168/16、100.64/10）/ 链路本地
    （169.254/16，云元数据就在这里）/ 组播 / 保留 / 未指定；IPv6 另含唯一本地
    （fc00::/7）与 IPv4 映射地址（`::ffff:127.0.0.1` 这类）。
    """
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_private or ip.is_link_local \
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return any(ip in net for net in _EXTRA_BLOCKED if net.version == ip.version)


def _parse_ip(text):
    """字面量 IP 解析（去 IPv6 方括号）；不是字面量返回 None。"""
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def host_is(url, host):
    """URL 的**主机名**是否恰为 host（CodeQL `py/incomplete-url-substring-*`）。

    为什么不能写 `host in url`：子串可以出现在路径或查询里，于是
    `https://gateway.example.com/?u=dashscope.aliyuncs.com` 会被判成"就是那台主机"。
    判定要按**主机名字段相等**，与 `assert_public_url` 用同一个 `urlsplit`。
    """
    try:
        return (urllib.parse.urlsplit(url or "").hostname or "").lower() == host.lower()
    except ValueError:
        return False


def assert_public_url(url, resolve=True):
    """`url` 指向公网 http(s) 就放行并返回主机名，否则抛 `OutboundBlocked`。

    `resolve=False` 只做字面量与协议判定（单测/离线场景用）；
    生产路径必须保持默认的 `True` —— 只有解析过才知道 `localhost`、`*.internal`
    这些"名字看起来无辜"的目标连到哪。
    """
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        # `.hostname` / `.port` 是**惰性求值**的：畸形方括号与 `:abc` / 越界端口
        # 在这一步才抛 ValueError（第一版守卫踩过：`http://a.com:abc/` 直接 500）。
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").strip()
        port = parts.port
    except ValueError:
        raise OutboundBlocked(REASON_URL, url=url)

    if scheme not in ALLOWED_SCHEMES:
        raise OutboundBlocked(REASON_SCHEME, url=url)
    if not host:
        raise OutboundBlocked(REASON_HOST, url=url)
    # `http://example.com@127.0.0.1/`：userinfo 让真实目标看起来像前面的域名
    if parts.username or parts.password:
        raise OutboundBlocked(REASON_CREDENTIALS, host=host, url=url)

    literal = _parse_ip(host)
    if literal is not None:
        if blocked_address(literal):
            raise OutboundBlocked(REASON_ADDRESS, host=host, url=url)
        return host

    # 卫生检查：空白 / 控制字符不该出现在主机名里，也不该被带进解析器
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in host):
        raise OutboundBlocked(REASON_URL, host=host, url=url)

    # 归一成 IDNA（ASCII）形式，**并用这个结果去解析**。
    # 这里不假装"非 ASCII 更安全"：解析器本来就会把 `ａpple.com` 折成 `apple.com`；
    # 我们能做的是让**守卫与解析器看同一份结果**，而不是 encode 一下就把原文丢掉。
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        raise OutboundBlocked(REASON_HOST, host=host, url=url)
    if not host:
        raise OutboundBlocked(REASON_HOST, url=url)

    if not resolve:
        return host

    port = port or DEFAULT_PORTS[scheme]
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        raise OutboundBlocked(REASON_RESOLVE, host=host, url=url)
    if not infos:
        raise OutboundBlocked(REASON_RESOLVE, host=host, url=url)

    # **每一个**解析结果都要过闸：多 A 记录 / DNS 轮询不能靠"只看第一个"绕过
    for info in infos:
        addr = info[4][0]
        ip = _parse_ip(addr.split("%", 1)[0])   # 去掉 IPv6 scope id
        if ip is None or blocked_address(ip):
            raise OutboundBlocked(REASON_ADDRESS, host=host, url=url)
    return host
