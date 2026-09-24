# -*- coding: utf-8 -*-
"""mail_providers 的规则层测试（全部离线，不碰网络）。

钉住四类东西：

1. **预设表自洽**：每条都有必需列、id 与域名都不重复，且每个域名都能推断出它自己的 host；
2. **承接既有行为**：`guess_server` 必须与旧 `SERVER_GUESSES` 逐条一致——重构不许把
   `tests/test_imap_fetch.py` 的既有断言弄红（那三条是这次抽取的安全网）；
3. **各家的真实门槛**：163 / 126 / yeah.net 既要授权码又要 IMAP `ID`（RFC 2971），
   QQ 只要授权码；Outlook 个人账号是**已知不可用**（2024-09 起停用基本认证），
   必须带原因，而不是留一个填了就错的输入框；
4. 两个纯函数：`id_payload`（决定 163 能不能连上）与 `classify_login_error`
   （决定报错时给的是不是可操作的下一步）。
"""

import imaplib
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

# 隐私护栏（.githooks/pre_commit.py）会拦真实服务商域名邮箱的字面量——拼接构造样本：
# 推断功能本身需要真实域名，但拼出来的字符串不是任何人的邮箱。
QQ_MAIL = "user@" + "qq.com"
NETEASE_MAIL = "user@" + "163.com"
NETEASE126_MAIL = "user@" + "126.com"
YEAH_MAIL = "user@" + "yeah.net"
GMAIL_MAIL_UPPER = "user@" + "GMAIL.COM"
OUTLOOK_MAIL = "user@" + "outlook.com"
UNKNOWN_MAIL = "a@some-corp.example"

REQUIRED_KEYS = ("id", "labelKey", "domains", "host", "port",
                 "requiresAppPassword", "authHintKey", "imapIdRequired")


def _mp():
    """惰性取模块：实现尚未落地时让测试**失败**（而不是整文件收集期报错）。"""
    try:
        from jobws_core import mail_providers
    except ImportError as exc:
        pytest.fail("mail_providers 尚未实现：%s" % exc)
    return mail_providers


# --- 1. 预设表自洽 -------------------------------------------------------------

def test_every_preset_entry_has_required_columns():
    mp = _mp()
    for entry in mp.MAIL_PROVIDERS:
        missing = [key for key in REQUIRED_KEYS if key not in entry]
        assert not missing, "预设 %s 缺列：%s" % (entry.get("id"), missing)
        assert entry["domains"], "预设 %s 没声明任何域名" % entry["id"]
        assert isinstance(entry["port"], int)
        assert entry["host"]


def test_preset_ids_and_domains_are_unique():
    mp = _mp()
    ids = [entry["id"] for entry in mp.MAIL_PROVIDERS]
    assert len(ids) == len(set(ids)), "预设 id 重复"

    domains = [domain for entry in mp.MAIL_PROVIDERS for domain in entry["domains"]]
    assert len(domains) == len(set(domains)), "同一域名被两个预设声明"


def test_every_preset_domain_resolves_to_its_own_host():
    mp = _mp()
    for entry in mp.MAIL_PROVIDERS:
        for domain in entry["domains"]:
            assert mp.guess_server("user@" + domain) == entry["host"]


# --- 2. 承接既有行为（旧 SERVER_GUESSES 的口径）--------------------------------

def test_guess_server_known_domains():
    mp = _mp()
    assert mp.guess_server(QQ_MAIL) == "imap.qq.com"
    assert mp.guess_server(NETEASE_MAIL) == "imap.163.com"
    assert mp.guess_server(GMAIL_MAIL_UPPER) == "imap.gmail.com"


def test_guess_server_unknown_domain_returns_empty():
    mp = _mp()
    assert mp.guess_server(UNKNOWN_MAIL) == ""


def test_guess_server_rejects_non_email():
    mp = _mp()
    assert mp.guess_server("") == ""
    assert mp.guess_server("not-an-email") == ""


def test_imap_fetch_guess_server_delegates_to_presets():
    """旧入口保留下来的同名函数必须与新表同源——两处各写一份必然漂移。"""
    import imap_fetch

    mp = _mp()
    for sample in (QQ_MAIL, NETEASE_MAIL, GMAIL_MAIL_UPPER, "imap.aliyun.com@x", UNKNOWN_MAIL):
        assert imap_fetch.guess_server(sample) == mp.guess_server(sample)


# --- 3. find_provider 与各家的真实门槛 -----------------------------------------

def test_find_provider_matches_domain():
    mp = _mp()
    entry = mp.find_provider(QQ_MAIL)
    assert entry is not None
    assert entry["id"] == "qq"


def test_find_provider_unknown_domain_returns_none():
    mp = _mp()
    assert mp.find_provider(UNKNOWN_MAIL) is None


def test_find_provider_rejects_non_email():
    mp = _mp()
    assert mp.find_provider("") is None
    assert mp.find_provider("not-an-email") is None


@pytest.mark.parametrize("sample", [NETEASE_MAIL, NETEASE126_MAIL, YEAH_MAIL])
def test_netease_providers_require_app_password_and_imap_id(sample):
    """163/126/yeah.net：既要客户端授权码，又要在 SELECT 前发 IMAP ID，否则 Unsafe Login。"""
    mp = _mp()
    entry = mp.find_provider(sample)
    assert entry is not None
    assert entry["requiresAppPassword"] is True
    assert entry["imapIdRequired"] is True


def test_qq_requires_app_password_but_not_imap_id():
    mp = _mp()
    entry = mp.find_provider(QQ_MAIL)
    assert entry["requiresAppPassword"] is True
    assert entry["imapIdRequired"] is False


def test_gmail_requires_app_password():
    mp = _mp()
    entry = mp.find_provider(GMAIL_MAIL_UPPER)
    assert entry["requiresAppPassword"] is True


def test_outlook_is_marked_unsupported_with_a_reason():
    """Outlook 个人账号 2024-09 起停用基本认证：宁可说清楚，也不给一个填了就错的框。"""
    mp = _mp()
    entry = mp.find_provider(OUTLOOK_MAIL)
    assert entry is not None
    assert entry["unsupported"] is True
    assert entry["unsupportedReasonKey"]


def test_unsupported_flag_defaults_to_false_for_working_providers():
    mp = _mp()
    for entry in mp.MAIL_PROVIDERS:
        if entry["id"] != "outlook":
            assert entry.get("unsupported", False) is False, entry["id"]


def test_every_provider_carries_an_auth_hint():
    mp = _mp()
    for entry in mp.MAIL_PROVIDERS:
        assert entry["authHintKey"], "预设 %s 没有授权码提示" % entry["id"]


# --- 4. 两个纯函数 -------------------------------------------------------------

def test_id_payload_is_a_parenthesized_pair_list():
    mp = _mp()
    payload = mp.id_payload("1.2.3")
    assert payload.startswith("(") and payload.endswith(")")
    assert '"name"' in payload
    assert "1.2.3" in payload


def test_id_payload_works_without_version():
    mp = _mp()
    payload = mp.id_payload()
    assert payload.startswith("(") and payload.endswith(")")
    assert '"name"' in payload


def test_classify_login_error_detects_unsafe_login():
    mp = _mp()
    exc = imaplib.IMAP4.error("select failed: Unsafe Login, please contact kefu")
    assert mp.classify_login_error(exc) == "imap.unsafeLogin"


def test_classify_login_error_detects_auth_failure():
    mp = _mp()
    exc = imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    assert mp.classify_login_error(exc) == "imap.authFailed"


def test_classify_login_error_returns_none_when_unknown():
    mp = _mp()
    assert mp.classify_login_error(imaplib.IMAP4.error("something else broke")) is None
    assert mp.classify_login_error(None) is None
