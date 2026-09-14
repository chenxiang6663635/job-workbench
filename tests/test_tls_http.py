# -*- coding: utf-8 -*-
"""出网请求的统一入口（`web/backend/tls_http.py`）：策略 + 稳定 error_code。

三个调用点（provider 连通性测试 / JD 抓取 / 简历改写）共用一套判定，所以这里
钉住四件事：

1. **证书库不可用 → `sys.certStoreUnavailable`**（不是 500、不是 ASN1 原文）；
2. **证书不被信任 → `sys.certUntrusted` 且带 host 参数**——"证书不被信任"与
   "连不上"是两回事：前者可能是自签名、也可能是被劫持，两条路的答案都不是
   关校验，所以文案里不给降级出口（与 IMAP 侧同一口径）；
3. **非证书类的连接错误原样抛出**，由各调用点保留自己的连接文案
   （provider.connectUnreachable / job.fetchUnreachable 已经在用户面前露过脸，
   不该因为这次改造换一套说法）；
4. **接线**：策略给出的上下文必须真的传进 `urlopen`——否则"统一了策略"是空话。
"""

import os
import ssl
import sys
import urllib.error
import urllib.request

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import tls_http  # noqa: E402
import tls_policy  # noqa: E402
from apierror import ApiError  # noqa: E402


class _BrokenStore:
    @staticmethod
    def boom(cafile=None):
        # 签名收下 cafile：回退路径会以 `create_default_context(cafile=…)` 调替身，
        # 无参签名会 TypeError 冒泡、绕过"拒绝"这条底线（独立审查 MINOR-4）。
        raise ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data")


def _req(url="https://example.com/v1/models"):
    return urllib.request.Request(url, headers={"Authorization": "Bearer sk-test"})


def test_broken_store_becomes_actionable_api_error(monkeypatch):
    """证书库损坏、连随包 CA 也不可用：502 + 稳定 code，detail 里带着排查指引。"""
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStore.boom)
    monkeypatch.setattr(tls_policy, "_builtin_ca_file", lambda: None)
    monkeypatch.delenv("JOBWS_HTTP_TLS", raising=False)

    with pytest.raises(ApiError) as ei:
        tls_http.open_url(_req(), timeout=5, purpose="Provider 连通性测试")

    assert ei.value.status_code == 502
    assert ei.value.code == "sys.certStoreUnavailable"
    assert "certmgr.msc" in ei.value.detail, "detail 是调试与 issue 用的原文，要能定位"


def test_broken_store_falls_back_to_bundled_ca(monkeypatch):
    """证书库损坏但随包 CA 可用：出网照常，且传给 urlopen 的上下文仍是严格的。

    兼容性批新增的第二条路。替身只在 `cafile is None` 时抛错、`cafile` 分支交给
    真实现加载随包 cacert.pem——所以断言的是真实回退产物。非证书类连接错误按口径
    原样抛出，这里顺势用它当"请求已抵达 urlopen"的信号。
    """
    real = ssl.create_default_context

    def store_broken(cafile=None):
        if cafile is None:
            raise ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data")
        return real(cafile=cafile)

    monkeypatch.setattr(ssl, "create_default_context", store_broken)
    monkeypatch.delenv("JOBWS_HTTP_TLS", raising=False)
    captured = {}

    def fake_urlopen(req, timeout=None, context=None):
        captured["context"] = context
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.URLError):
        tls_http.open_url(_req(), timeout=5, purpose="Provider 连通性测试")

    ctx = captured["context"]
    assert ctx is not None, "策略给的上下文必须真的传进 urlopen"
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_untrusted_certificate_gets_its_own_code_and_host(monkeypatch):
    """证书不被信任：独立 code + host 参数，且不提供降级出口。

    urllib 把 TLS 错误包成 `URLError(reason=SSLCertVerificationError(...))`，
    必须按 reason 判定，否则会被当成普通"连不上"。
    """
    monkeypatch.setattr(ssl, "create_default_context",
                        lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))

    def _boom(req, timeout=None, context=None):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    with pytest.raises(ApiError) as ei:
        tls_http.open_url(_req("https://self-signed.example/x"),
                          timeout=5, purpose="JD 抓取")

    assert ei.value.code == "sys.certUntrusted"
    assert ei.value.params["host"] == "self-signed.example"


def test_direct_ssl_error_is_also_translated(monkeypatch):
    """少数路径直接抛 SSLCertVerificationError（没包 URLError）——同样要翻译。

    若只认 URLError，这类失败会退化成各调用点的泛化兜底（"抓取失败：…"），
    用户拿不到"证书不被信任、不要关校验"这句关键判断。
    """
    monkeypatch.setattr(ssl, "create_default_context",
                        lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))

    def _boom(req, timeout=None, context=None):
        raise ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    with pytest.raises(ApiError) as ei:
        tls_http.open_url(_req("https://expired.example/x"), timeout=5, purpose="JD 抓取")

    assert ei.value.code == "sys.certUntrusted"
    assert ei.value.params["host"] == "expired.example"


def test_plain_unreachable_keeps_callers_own_wording(monkeypatch):
    """普通连接失败不在这里翻译：原样抛出，调用点的既有文案继续生效。"""
    monkeypatch.setattr(ssl, "create_default_context",
                        lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))

    def _boom(req, timeout=None, context=None):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    with pytest.raises(urllib.error.URLError):
        tls_http.open_url(_req(), timeout=5, purpose="简历改写")


def test_policy_context_is_actually_passed_to_urlopen(monkeypatch):
    """接线：上下文来自 tls_policy，且真的传给了 urlopen。

    没有这条，三个调用点各自 `urlopen(req, timeout=...)` 也能"看起来对"，
    而校验其实没生效——issue #59 的正是这种沉默失效。
    """
    sentinel = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(tls_policy, "outbound_ssl_context",
                        lambda purpose, env_var: sentinel)
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake(req, timeout=None, context=None):
        captured["context"] = context
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake)

    with tls_http.open_url(_req(), timeout=7, purpose="Provider 连通性测试") as resp:
        assert resp is not None

    assert captured["context"] is sentinel
    assert captured["timeout"] == 7
