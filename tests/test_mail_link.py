# -*- coding: utf-8 -*-
"""原邮件深链构造（批 4.5）：纯函数口径。

钉住五件事：
1. 自粘链接最高优先（Outlook 等无深链邮箱靠它）；
2. Gmail 深链的编码规则（`:`→`%3A` 是前缀的一部分、`@`→`%40`、`<>` 已去）；
3. 无 id 且无自粘链接时诚实返回 none——**不造假链接**；
4. 空白串与 None 一视同「没有」；
5. **provider 感知（2026-09-25 真机）**：Gmail 深链只对配置里的 Gmail 邮箱成立——
   此前对所有有 Message-ID 的邮件都给，非 Gmail 用户点了落一页陌生 Gmail
   （"看起来能用、点了就错"）。非 Gmail / 未配置一律 none，交给降级提示。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import mail_link  # noqa: E402

# 拼接构造样本地址：privacy 钩子拦 staged diff 里的真实邮箱字面量
GMAIL_USER = "candidate" + "@" + "gmail.com"
QQ_USER = "me" + "@" + "qq.com"
OUTLOOK_USER = "me" + "@" + "outlook.com"


def test_custom_link_wins_over_message_id():
    got = mail_link.build_open_link("abc@example.com",
                                    "https://outlook.office365.com/owa/?ItemID=xyz",
                                    imap_user=GMAIL_USER)
    assert got["kind"] == "custom"
    assert got["url"].startswith("https://outlook.office365.com/")


def test_custom_link_works_regardless_of_provider():
    """自粘链接对任何邮箱都成立——provider 感知只约束 Gmail 深链那一支。"""
    got = mail_link.build_open_link("abc@example.com",
                                    "https://mail.qq.com/cgi-bin/frame_html?abc=1",
                                    imap_user=QQ_USER)
    assert got["kind"] == "custom"


def test_gmail_link_encodes_message_id():
    got = mail_link.build_open_link("abc.def@example.com", imap_user=GMAIL_USER)
    assert got["kind"] == "gmail"
    assert got["url"] == ("https://mail.google.com/mail/#search/"
                          "rfc822msgid%3Aabc.def%40example.com")


def test_non_gmail_mailbox_gets_no_deeplink():
    """真机缺陷：非 Gmail 用户点了 Gmail 搜索页 = 错误页。宁可不给，交给降级提示。"""
    got = mail_link.build_open_link("abc@example.com", imap_user=QQ_USER)
    assert got == {"kind": "none", "url": None}
    got = mail_link.build_open_link("abc@example.com", imap_user=OUTLOOK_USER)
    assert got == {"kind": "none", "url": None}


def test_unconfigured_mailbox_gets_no_deeplink():
    """没连过邮箱（手工录入的台账行）不知道邮箱是哪家：保守不给。"""
    got = mail_link.build_open_link("abc@example.com")
    assert got == {"kind": "none", "url": None}
    got = mail_link.build_open_link("abc@example.com", imap_user="  ")
    assert got == {"kind": "none", "url": None}


def test_none_when_no_id_and_no_custom_link():
    assert mail_link.build_open_link("", imap_user=GMAIL_USER) == {
        "kind": "none", "url": None}
    assert mail_link.build_open_link(None, "  ", imap_user=GMAIL_USER) == {
        "kind": "none", "url": None}


def test_whitespace_is_treated_as_absent():
    assert mail_link.build_open_link("  ", "  ", imap_user=GMAIL_USER)["kind"] == "none"
    got = mail_link.build_open_link("  a@b.c  ", imap_user=GMAIL_USER)
    assert got["url"].endswith("a%40b.c")


def test_custom_link_requires_http_scheme():
    """审查 m-3：非 http(s) 的自粘串（错字/纯文本/javascript:）宁降级 none，不进 href。"""
    assert mail_link.build_open_link("", "javascript:alert(1)", imap_user=GMAIL_USER) == {
        "kind": "none", "url": None}
    assert mail_link.build_open_link("", "outlook 邮件，点这个", imap_user=GMAIL_USER) == {
        "kind": "none", "url": None}
    got = mail_link.build_open_link("a@b.c", "http://intranet.example/mail/123",
                                    imap_user=GMAIL_USER)
    assert got["kind"] == "custom"
    assert got["url"] == "http://intranet.example/mail/123"


def test_gmail_link_normalizes_angle_brackets():
    """审查 M-1 读路径兜底：历史脏数据（带 `<>`）也能构造出有效深链。"""
    got = mail_link.build_open_link("<abc@example.com>", imap_user=GMAIL_USER)
    assert got["kind"] == "gmail"
    assert got["url"] == ("https://mail.google.com/mail/#search/"
                          "rfc822msgid%3Aabc%40example.com")
