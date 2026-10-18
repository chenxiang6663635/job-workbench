# -*- coding: utf-8 -*-
"""出网目标守卫（CodeQL `py/full-ssrf` #2）：只允许指向**公网**地址的 http(s) URL。

`POST /api/jobs/fetch-jd` 收用户给的链接、由服务端去取——这是 SSRF 的标准形状。
此前只校验 `startswith("http://"|"https://")`，于是 `http://169.254.169.254/`
（云元数据）与 `http://127.0.0.1:8765/`（本机 API）都能被当成"JD 链接"取回来。

这里钉六条：
1. 非 http(s) 的 scheme 一律拒（file / ftp / gopher / javascript）；
2. 字面量就是本机 / 内网 / 链路本地 / 保留 / 未指定地址 → 拒；
3. 主机名**解析结果**落在上述地址 → 拒（`localhost`、`*.internal` 这类靠解析的绕法）；
4. 解析出多个地址时**任一**命中即拒（多 A 记录 / DNS 轮询不能只查第一个）；
5. URL 带 userinfo（`http://公网域名@127.0.0.1/`）一律拒——hostname 解析与浏览器
   语义不一致时最容易被骗的一类；
6. 真·公网地址放行（不给真实网络：mock `socket.getaddrinfo`）。
"""

import socket

import pytest

from jobws_core import outbound


def _fake_resolve(monkeypatch, *ips):
    """把 getaddrinfo 打桩成给定地址列表（不碰真实 DNS）。"""
    infos = []
    for ip in ips:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        infos.append((family, socket.SOCK_STREAM, 6, "", (ip, 443)))
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *a, **kw: infos)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com:70/_x",
    "javascript:alert(1)",
])
def test_rejects_non_http_scheme(url):
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url(url)
    assert ei.value.reason == "scheme"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x",          # 回环
    "http://127.1.2.3/x",          # 回环整段
    "http://localhost/x",          # 名字形态的回环
    "http://0.0.0.0/x",            # 未指定
    "http://10.0.0.5/x",           # 私网 A
    "http://172.16.3.4/x",         # 私网 B
    "http://192.168.1.9/x",        # 私网 C
    "http://169.254.169.254/latest/meta-data/",   # 链路本地（云元数据）
    "http://100.64.0.1/x",         # 运营商级 NAT
    "http://[::1]/x",              # IPv6 回环
    "http://[fd00::1]/x",          # IPv6 唯一本地
    "http://[fe80::1]/x",          # IPv6 链路本地
])
def test_rejects_local_and_internal_addresses(url, monkeypatch):
    # localhost 走解析；其余是字面量（即便不打桩也必须拒）
    _fake_resolve(monkeypatch, "127.0.0.1")
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url(url)
    assert ei.value.reason in ("address", "resolve")


def test_rejects_hostname_that_resolves_to_private(monkeypatch):
    """靠解析绕：名字看起来公网，A 记录指向内网。"""
    _fake_resolve(monkeypatch, "10.0.0.5")
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url("https://evil.example.com/jd")
    assert ei.value.reason == "address"


def test_rejects_when_any_resolved_address_is_private(monkeypatch):
    """多个 A 记录里**任一**命中即拒——不能只看第一个（DNS 轮询可绕过）。"""
    _fake_resolve(monkeypatch, "93.184.216.34", "192.168.0.10")
    with pytest.raises(outbound.OutboundBlocked):
        outbound.assert_public_url("https://mixed.example.com/jd")


def test_rejects_userinfo_that_hides_the_real_host():
    """`http://公网域名@127.0.0.1/`：肉眼像公网，实际连的是 127.0.0.1。"""
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url("http://example.com@127.0.0.1:8080/x")
    assert ei.value.reason == "credentials"


@pytest.mark.parametrize("url", [
    "http://exa mple.com/",     # 空格
    "http://exa\x00mple.com/",  # NUL
])
def test_host_with_whitespace_or_control_chars_is_rejected(url):
    """空白/控制字符不该出现在主机名里，也不该被带进解析器（卫生问题）。"""
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url(url, resolve=False)
    assert ei.value.reason == "url"


def test_tab_and_newlines_are_stripped_by_the_url_parser():
    """`urlsplit` 会**剥掉** tab / CR / LF（WHATWG 行为，与浏览器一致）。

    这不是漏洞——实际连接的就是剥离后的主机，但值得钉住，否则"空白字符被拒"
    会被误读成"含制表符的 URL 会被拒"（第一版测试正是这么以为的）。
    """
    assert outbound.assert_public_url("http://exa\tmple.com/",
                                      resolve=False) == "example.com"


def test_fullwidth_host_is_resolved_via_its_ascii_form(monkeypatch):
    """全角/IDN 主机：**用归一后的 ASCII 形式去解析**，而不是只 encode 一下丢掉。

    审查指出第一版注释宣称"非 ASCII 容易被仿冒"却没有落地——现在解析器与守卫
    看的是同一个归一结果（`ａpple.com` → `apple.com`），过闸的就是真正要连接的地址。
    """
    seen = {}

    def fake_resolve(host, port, **kwargs):
        seen["host"] = host
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(outbound.socket, "getaddrinfo", fake_resolve)

    outbound.assert_public_url("http://\uff41pple.com/jd")

    assert seen["host"] == "apple.com", "解析用的是原始全角形式：%r" % (seen["host"],)


def test_accepts_public_host(monkeypatch):
    _fake_resolve(monkeypatch, "93.184.216.34")
    host = outbound.assert_public_url("https://jobs.example.com/p/1")
    assert host == "jobs.example.com"


@pytest.mark.parametrize("url", [
    "http://a.com:abc/x",      # 端口不是数字
    "http://a.com:99999/x",    # 端口越界
    "http://[::1/x",           # 方括号没闭合
])
def test_malformed_url_is_blocked_not_crashing(url, monkeypatch):
    """畸形 URL 必须走"拒绝"，不能抛 ValueError（那会变成 500 而不是可读的 422）。

    `urlsplit(...).port` 对 `:abc` 与越界端口抛 ValueError；生产路径（resolve=True）
    一定会摸到它——第一版守卫正是踩在这里（自查发现：`http://a.com:abc/` 直接 500）。
    """
    _fake_resolve(monkeypatch, "93.184.216.34")
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url(url)
    assert ei.value.reason == "url"


def test_blocked_carries_host_for_the_user_facing_message(monkeypatch):
    """拒绝要能渲染成人话：带 host 与 reason（前端 `err.job.urlBlocked` 用）。"""
    _fake_resolve(monkeypatch, "169.254.169.254")
    with pytest.raises(outbound.OutboundBlocked) as ei:
        outbound.assert_public_url("http://meta.example.com/latest")
    assert ei.value.host == "meta.example.com"
    assert ei.value.reason == "address"
