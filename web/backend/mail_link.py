# -*- coding: utf-8 -*-
"""原邮件深链构造（批 4.5）：纯函数，可单测——路由与测试复用同一份口径。

能力边界（2026-09-16 逐家核实，详见批 4.5 调研文档）：

- **Gmail**：`rfc822msgid:` 是官方搜索运算符，由规范 Message-ID 可构造搜索页
  深链（多一次点击、需已登录 Gmail；社区实践来源，Gmail 若调整界面以实测为准）。
  编码规则：去 `<>`；`:` 编为 `%3A`、`@` 编为 `%40`；省略 `/u/{n}` 以脱离
  账号索引（`/u/0` 只指第一个登录账号）。
- **Outlook**：官方深链要 webmail 专属 ItemID（IMAP 拿不到），搜索型 URL
  微软官方确认不可行——只能由用户在「webmail链接」列粘贴。
- **QQ / 163 / 企业微信 / 飞书 / iCloud**：无可用深链（多轮检索无果的保守
  判断），诚实降级为「打开邮箱 + 复制主题搜索」，**不造可能失效的假链接**。

注意一个天然限制：**客户端无法从 Message-ID 判断用户的邮箱是哪家**——
所以 kind 只表达"链接怎么来"（自粘 / 由 Message-ID 构造），前端文案需
写明「若你用 Gmail」（见 i18n）；这不是缺陷，是诚实。
"""

import urllib.parse

# Gmail 搜索页深链前缀：rfc822msgid 的冒号在 URL 路径里编码为 %3A。
GMAIL_SEARCH_PREFIX = "https://mail.google.com/mail/#search/rfc822msgid%3A"


def build_open_link(message_id, webmail_link=""):
    """按「消息id / 用户自粘链接」构造打开原邮件的链接。

    返回 ``{"kind": "custom"|"gmail"|"none", "url": str|None}``：

    - custom：用户在「webmail链接」列粘贴过的链接（最高优先，任何邮箱）；
    - gmail：由规范 Message-ID 构造的 Gmail 搜索深链；
    - none：无可用深链——前端降级为「打开邮箱 + 复制主题搜索」提示。
    """
    custom = (webmail_link or "").strip()
    if custom:
        return {"kind": "custom", "url": custom}
    mid = (message_id or "").strip()
    if not mid:
        return {"kind": "none", "url": None}
    return {"kind": "gmail", "url": GMAIL_SEARCH_PREFIX + urllib.parse.quote(mid, safe="")}
