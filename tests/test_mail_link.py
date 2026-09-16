# -*- coding: utf-8 -*-
"""原邮件深链构造（批 4.5）：纯函数口径。

钉住四件事：
1. 自粘链接最高优先（Outlook 等无深链邮箱靠它）；
2. Gmail 深链的编码规则（`:`→`%3A` 是前缀的一部分、`@`→`%40`、`<>` 已去）；
3. 无 id 且无自粘链接时诚实返回 none——**不造假链接**；
4. 空白串与 None 一视同「没有」。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import mail_link  # noqa: E402


def test_custom_link_wins_over_message_id():
    got = mail_link.build_open_link("abc@example.com",
                                    "https://outlook.office365.com/owa/?ItemID=xyz")
    assert got["kind"] == "custom"
    assert got["url"].startswith("https://outlook.office365.com/")


def test_gmail_link_encodes_message_id():
    got = mail_link.build_open_link("abc.def@example.com")
    assert got["kind"] == "gmail"
    assert got["url"] == ("https://mail.google.com/mail/#search/"
                          "rfc822msgid%3Aabc.def%40example.com")


def test_none_when_no_id_and_no_custom_link():
    assert mail_link.build_open_link("") == {"kind": "none", "url": None}
    assert mail_link.build_open_link(None, "  ") == {"kind": "none", "url": None}


def test_whitespace_is_treated_as_absent():
    assert mail_link.build_open_link("  ", "  ")["kind"] == "none"
    got = mail_link.build_open_link("  a@b.c  ")
    assert got["url"].endswith("a%40b.c")
