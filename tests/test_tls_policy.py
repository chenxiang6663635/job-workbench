# -*- coding: utf-8 -*-
"""出网 TLS 策略唯一实现（`tools/tls_policy.py`）的判定口径。

issue #59 的来源：provider 的连通性测试曾在**有意关闭证书校验**的连接上发送
`Authorization: Bearer <api_key>`（目标还是用户自己填的公网地址）；resume / jobs
两处出网则没传上下文，证书库损坏的机器上直接抛 `ASN1: NOT_ENOUGH_DATA` 原文。
IMAP 侧（issue #50 S2）已经落实过「默认严格 → 失败即拒绝 → 仅显式降级」的策略，
本模块把它收成唯一实现，三处 HTTP 出网与 IMAP 共用。

这里钉住五条口径：

1. **证书库正常 → 严格上下文**（校验主机名 + 验证证书），且**绝不主动降级**——
   哪怕环境变量已经写着 insecure，正常机器也不该把校验关掉；
2. **证书库损坏 + 显式 `insecure` → 降级**：用户的明确选择优先于自动兜底（连自签
   证书的服务器时，内置 CA 一样验不过，覆盖掉显式意图只会让人更困惑）；
3. **证书库损坏且未显式降级 → 回退随包 CA（certifi）**，且回退得到的上下文**仍是
   严格校验**——它不是"关掉校验的另一条路"；
4. **回退也不可用 → 默认拒绝**，消息里有 `certmgr.msc` 排查指引、显式降级变量名，
   以及"是哪条功能在出网"（purpose）——用户看到的必须是「怎么办」而不是 ASN1 原文；
5. **降级后的上下文确实是 CERT_NONE + check_hostname=False**——否则"降级"是假的，
   用户以为跳过了校验、实际仍然失败（或反过来）。
"""

import os
import ssl
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import tls_policy  # noqa: E402


class _BrokenStore:
    """模拟 Windows 证书库损坏：create_default_context 直接抛 ASN1 错误。

    本机（Windows）证书库确实有损坏条目，真调用会在测试里直接崩，所以所有
    用例都用哨兵/异常替身，不碰真实证书库。
    """

    @staticmethod
    def boom():
        raise ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data")


@pytest.fixture
def no_builtin_ca(monkeypatch):
    """让「随包 CA」这条路也不可用。

    测**底线**（拒绝 / 显式降级）的用例要用：本机与 CI 都装着 certifi，不挡掉的话
    回退会成功，用例就滑到另一条分支上去了。
    """
    monkeypatch.setattr(tls_policy, "_builtin_ca_file", lambda: None)


def test_strict_by_default(monkeypatch):
    """证书库正常：返回严格上下文，主机名与证书都要校验。"""
    sentinel = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(ssl, "create_default_context", lambda: sentinel)

    ctx = tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    assert ctx is sentinel
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_healthy_store_never_downgrades_even_with_flag(monkeypatch):
    """证书库正常时，环境变量写着 insecure 也不降级。

    降级是给"证书库不可用"的机器的出路，不是一种常规模式——正常机器上它必须
    完全无效，否则用户随手设一个环境变量就能让所有出网失去校验。
    """
    sentinel = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(ssl, "create_default_context", lambda: sentinel)
    monkeypatch.setenv("JOBWS_HTTP_TLS", "insecure")

    assert tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS") is sentinel


def test_broken_store_message_names_purpose_and_way_out(monkeypatch, no_builtin_ca):
    """证书库损坏、连回退也不可用且未显式降级：拒绝，并给出可操作的出路与"是谁在出网"。"""
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStore.boom)
    monkeypatch.delenv("JOBWS_HTTP_TLS", raising=False)

    with pytest.raises(tls_policy.TlsPolicyError) as ei:
        tls_policy.outbound_ssl_context("简历改写", "JOBWS_HTTP_TLS")

    msg = str(ei.value)
    assert "certmgr.msc" in msg, "必须给出排查指引，否则用户只看到 ASN1 原文"
    assert "JOBWS_HTTP_TLS" in msg, "必须说明显式降级要设哪个变量"
    assert "简历改写" in msg, "必须说明是哪条功能失败了"


def test_downgrade_requires_the_insecure_word(monkeypatch, no_builtin_ca):
    """只有 `insecure` 能降级；其它"看着像真"的值一律不降级。"""
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStore.boom)

    for value in ("true", "1", "yes", "0", "insecurely", "disable"):
        monkeypatch.setenv("JOBWS_HTTP_TLS", value)
        with pytest.raises(tls_policy.TlsPolicyError):
            tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")


class _BrokenStoreOtherError:
    """证书库故障抛成**非** SSLError 的形态（独立审查 MINOR-1）。

    `ssl.SSLError` 是 `OSError` 的子类，但 `create_default_context()` 在更外层
    也可能抛裸 `OSError`（证书库枚举/文件访问失败）。若只认 `SSLError`，这类
    故障既不降级、也拿不到出路文案 —— 正好是 #59 想消除的"用户看到原文"。
    """

    @staticmethod
    def boom():
        raise OSError("cannot enumerate the certificate store")


def test_non_sslerror_store_failure_still_gives_way_out(monkeypatch, no_builtin_ca):
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStoreOtherError.boom)
    monkeypatch.delenv("JOBWS_HTTP_TLS", raising=False)

    with pytest.raises(tls_policy.TlsPolicyError) as ei:
        tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    msg = str(ei.value)
    assert "certmgr.msc" in msg
    assert "JOBWS_HTTP_TLS" in msg


def test_non_sslerror_store_failure_can_still_be_downgraded(monkeypatch):
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStoreOtherError.boom)
    monkeypatch.setenv("JOBWS_HTTP_TLS", "insecure")

    ctx = tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_downgrade_context_really_skips_verification(monkeypatch):
    """显式 insecure：返回的上下文确实不校验（主机名与证书都不校验）。

    大小写与首尾空格容忍（沿用 IMAP 侧既有行为）——它是人手敲的环境变量。
    """
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStore.boom)
    monkeypatch.setenv("JOBWS_HTTP_TLS", " Insecure ")

    ctx = tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


# --- 口径第 3 条：随包 CA 回退（2026-09-14 兼容性批）------------------------


def test_falls_back_to_bundled_ca_when_store_is_broken(monkeypatch):
    """证书库坏 → 先用系统库（失败）、再用随包 CA 建上下文。"""
    sentinel = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    seen = []

    def fake_create_default_context(cafile=None):
        seen.append(cafile)
        if cafile is None:
            raise ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data")
        return sentinel

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)
    monkeypatch.setattr(tls_policy, "_builtin_ca_file", lambda: "/bundled/cacert.pem")
    monkeypatch.delenv("JOBWS_HTTP_TLS", raising=False)

    ctx = tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    assert ctx is sentinel
    assert seen == [None, "/bundled/cacert.pem"], "应先用系统库、再回退随包 CA"


def test_bundled_ca_fallback_is_strict_not_a_downgrade():
    """回退得到的上下文必须仍是严格校验——它不是"关掉校验的另一条路"。

    这一条用**真实 certifi**（不替身）：真的读一遍随包的 cacert.pem，证明"回退"
    不是纸面承诺。
    """
    ctx = tls_policy._context_from_builtin_ca()
    assert ctx is not None, "本机与 CI 都应装上 certifi（requirements.txt 已声明）"
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_explicit_insecure_wins_over_bundled_ca(monkeypatch):
    """显式 insecure 优先于随包 CA：用户明说跳过校验时，别替他"安全升级"。

    连自签证书的服务器时内置 CA 一样验不过——覆盖显式意图只会让失败更难解释。
    这里把 `_builtin_ca_file` 设成 fail-fast，就是在钉"根本没去动回退"。
    """
    monkeypatch.setattr(ssl, "create_default_context", _BrokenStore.boom)
    monkeypatch.setattr(tls_policy, "_builtin_ca_file",
                        lambda: pytest.fail("显式降级时不该去碰随包 CA"))
    monkeypatch.setenv("JOBWS_HTTP_TLS", "insecure")

    ctx = tls_policy.outbound_ssl_context("Provider 连通性测试", "JOBWS_HTTP_TLS")

    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_bundled_ca_itself_broken_returns_none(monkeypatch):
    """随包 CA 路径存在、但加载失败 → 返回 None（由调用方继续走拒绝）。"""
    def boom(cafile=None):
        raise ssl.SSLError("bundled cacert.pem unreadable")

    monkeypatch.setattr(ssl, "create_default_context", boom)
    monkeypatch.setattr(tls_policy, "_builtin_ca_file", lambda: "/x/cacert.pem")

    assert tls_policy._context_from_builtin_ca() is None
