# -*- coding: utf-8 -*-
"""邮箱服务商预设表与登录错误分类：纯数据 + 纯函数（无网络、无 I/O）。

为什么单独一层：Thunderbird autoconfig / ISPDB 那套字段（host / port /
socketType / authentication / username 模板）只回答「服务器在哪」，**不回答
「为什么连不上」**。ISPDB 里 163 的条目完全正确，但用户照它填网页密码必然失败 ——
163 / 126 / yeah.net 要的是**客户端授权码**，且必须在 `SELECT` 之前发 IMAP `ID`
（RFC 2971），否则服务端直接回 `Unsafe Login`。所以本模块在那些字段之外补三列：
`requiresAppPassword` / `authHintKey` / `docUrl`，再加一个 `imapIdRequired`。

分层：本模块只有数据与纯判定，**不建立任何连接**（会话在 `tools/imap_session.py`），
所以可以离线单测（`tests/test_mail_providers.py`）。

两条刻意的取舍：

- `domains` 走**精确匹配**，不做后缀匹配 —— `evil-qq.com` 不该被当成 QQ 邮箱；
- `docUrl` 允许为空 —— 没核实过的「官方指引」宁可空着，也不造一个看起来对的链接。
"""

from __future__ import annotations

# 网易系（163 / 126 / yeah.net）共用同一份官方规则页：客户端授权码的使用规则
# 由网易统一说明（关闭授权码会连带关闭 IMAP，客户端随即报「密码错误」）。
_NETEASE_AUTH_DOC = "https://help.163.com/14/0924/09/A6T8DMQS00754KNP.html"

# 预设表：一条 = 一个服务商。字段含义见模块 docstring。
MAIL_PROVIDERS = [
    {
        "id": "qq",
        "labelKey": "mailProvider.qq",
        "domains": ["qq.com", "foxmail.com"],
        "host": "imap.qq.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintQq",
        "docUrl": "https://help.mail.qq.com/detail/106/985",
        "imapIdRequired": False,
    },
    {
        "id": "netease163",
        "labelKey": "mailProvider.netease163",
        "domains": ["163.com"],
        "host": "imap.163.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintNetease",
        "docUrl": _NETEASE_AUTH_DOC,
        "imapIdRequired": True,
    },
    {
        "id": "netease126",
        "labelKey": "mailProvider.netease126",
        "domains": ["126.com"],
        "host": "imap.126.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintNetease",
        "docUrl": _NETEASE_AUTH_DOC,
        "imapIdRequired": True,
    },
    {
        "id": "yeah",
        "labelKey": "mailProvider.yeah",
        "domains": ["yeah.net"],
        "host": "imap.yeah.net",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintNetease",
        "docUrl": _NETEASE_AUTH_DOC,
        "imapIdRequired": True,
    },
    {
        "id": "gmail",
        "labelKey": "mailProvider.gmail",
        "domains": ["gmail.com"],
        "host": "imap.gmail.com",
        "port": 993,
        # Gmail 不接受账户密码：先开两步验证，再生成「应用专用密码」。
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintGmail",
        "docUrl": "https://learn.microsoft.com/zh-cn/exchange/mailbox-migration/"
                  "migrating-imap-mailboxes/prepare-gmail-or-g-suite-accounts",
        "imapIdRequired": False,
    },
    {
        "id": "outlook",
        "labelKey": "mailProvider.outlook",
        "domains": ["outlook.com", "hotmail.com", "live.com"],
        "host": "outlook.office365.com",
        "port": 993,
        # 诚实标注：2024-09-16 起 Outlook.com 个人账号停用基本认证，第三方 IMAP
        # 必须 OAuth2；本工作台只有「用户名 + 密码/授权码」，所以**连不上**。
        # 与其让用户在这里填一个永远失败的框，不如直接说清原因（见 hint 文案）。
        "requiresAppPassword": False,
        "authHintKey": "mailProvider.hintOutlook",
        "docUrl": "https://prod.support.services.microsoft.com/zh-cn/office/"
                  "outlook-com-%E7%9A%84-pop-imap-%E5%92%8C-smtp-%E8%AE%BE%E7%BD%AE-"
                  "d088b986-291d-42b8-9564-9c414e2aa040",
        "imapIdRequired": False,
        "unsupported": True,
        "unsupportedReasonKey": "mailProvider.unsupportedOutlook",
    },
    {
        "id": "aliyun",
        "labelKey": "mailProvider.aliyun",
        "domains": ["aliyun.com"],
        "host": "imap.aliyun.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintGeneric",
        "docUrl": "",
        "imapIdRequired": False,
    },
    {
        "id": "sina",
        "labelKey": "mailProvider.sina",
        "domains": ["sina.com"],
        "host": "imap.sina.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintGeneric",
        "docUrl": "",
        "imapIdRequired": False,
    },
    {
        "id": "sohu",
        "labelKey": "mailProvider.sohu",
        "domains": ["sohu.com"],
        "host": "imap.sohu.com",
        "port": 993,
        "requiresAppPassword": True,
        "authHintKey": "mailProvider.hintGeneric",
        "docUrl": "",
        "imapIdRequired": False,
    },
]


def _domain_of(email_addr):
    """取规范化域名；不是一个「邮箱形状」的输入返回空串。"""
    if not email_addr or "@" not in email_addr:
        return ""
    return email_addr.rsplit("@", 1)[1].strip().lower()


def find_provider(email_addr):
    """按域名找预设；未知域名返回 None（由用户手填服务器）。"""
    domain = _domain_of(email_addr)
    if not domain:
        return None
    for entry in MAIL_PROVIDERS:
        if domain in entry["domains"]:
            return entry
    return None


def guess_server(email_addr):
    """按邮箱域名推断 IMAP 服务器；未知域名返回空串（保持旧口径不变）。

    这条行为被 2026-09-22 之前的 `SERVER_GUESSES` 固定过，`tests/test_imap_fetch.py`
    的既有断言仍然有效——抽取不许改口径，只许换存放位置。
    """
    entry = find_provider(email_addr)
    return entry["host"] if entry else ""


def id_payload(version=""):
    """IMAP `ID` 命令的载荷（RFC 2971）。

    163 / 126 / yeah.net 要求客户端在 `SELECT` 之前声明身份，否则回 `Unsafe Login`。
    载荷只声明客户端名与版本，不含任何用户信息。
    """
    pairs = [("name", "job-workbench"), ("vendor", "job-workbench")]
    if version:
        pairs.append(("version", str(version)))
    return "(" + " ".join('"%s" "%s"' % (key, value) for key, value in pairs) + ")"


# 归类登录失败：给调用方一个稳定的错误码，而不是把服务端原文抛给用户。
# `Unsafe Login` 必须单独成类——它的下一步（开 IMAP / 换授权码 / 客户端声明身份）
# 和「密码打错了」完全不同。
_UNSAFE_LOGIN_MARKERS = ("unsafe login",)
_AUTH_FAILURE_MARKERS = (
    "authenticationfailed",
    "authentication failed",
    "invalid credentials",
    "login failed",
    "login aborted",
)


def classify_login_error(exc):
    """把登录/选择文件夹的异常归成错误码；归不出种类时返回 None。

    注意 163 关闭授权码后服务端回的就是「密码错误」——所以 `imap.authFailed`
    的文案必须同时提到「授权码可能已被关闭或服务未开启」，不能只说密码错了。
    """
    text = str(exc or "").lower()
    if not text:
        return None
    if any(marker in text for marker in _UNSAFE_LOGIN_MARKERS):
        return "imap.unsafeLogin"
    if any(marker in text for marker in _AUTH_FAILURE_MARKERS):
        return "imap.authFailed"
    return None
