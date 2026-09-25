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

注意：客户端**无法从 Message-ID 判断这封邮件来自哪家邮箱**——但**配置里
写着用户连的是哪家**（2026-09-25 真机修复）：Gmail 深链只对配置的 Gmail
邮箱构造，其余邮箱一律降级 none。此前"对所有有 Message-ID 的邮件都给
Gmail 链接"的做法，对非 Gmail 用户就是「看起来能用、点了就错」的陷阱。
"""

import urllib.parse

# Gmail 搜索页深链前缀：rfc822msgid 的冒号在 URL 路径里编码为 %3A。
GMAIL_SEARCH_PREFIX = "https://mail.google.com/mail/#search/rfc822msgid%3A"


def build_open_link(message_id, webmail_link="", imap_user=""):
    """按「消息id / 用户自粘链接」构造打开原邮件的链接。

    返回 ``{"kind": "custom"|"gmail"|"none", "url": str|None}``：

    - custom：用户在「webmail链接」列粘贴过的链接（最高优先，任何邮箱）；
    - gmail：由规范 Message-ID 构造的 Gmail 搜索深链——**仅当配置的邮箱是
      Gmail**（`imap_user` 以 @gmail.com 结尾）；
    - none：无可用深链——前端降级为「打开邮箱 + 复制主题搜索」提示。

    `imap_user` 是工作区 IMAP 配置里的邮箱地址：非 Gmail / 未配置（手工录入
    的台账行不知道邮箱是哪家）一律不给 Gmail 深链——宁可少给，不给点了
    就错的链接；要直达链接可以自粘（custom 分支对任何邮箱开放）。
    """
    custom = (webmail_link or "").strip()
    # 只接受 http(s) 链接：错字、纯文本乃至 javascript: 一律降级 none——宁可让
    # 用户走「复制主题搜索」，也不把可能失效/危险的东西塞进 <a href>（审查 m-3）。
    if custom and (custom.startswith("http://") or custom.startswith("https://")):
        return {"kind": "custom", "url": custom}
    # provider 感知（2026-09-25 真机）：深链只对 Gmail 邮箱成立。
    if not (imap_user or "").strip().lower().endswith("@gmail.com"):
        return {"kind": "none", "url": None}
    mid = (message_id or "").strip()
    if len(mid) >= 2 and mid.startswith("<") and mid.endswith(">"):
        mid = mid[1:-1].strip()  # 读路径兜底历史脏数据，与 tracker.normalize_message_id 同口径
    if not mid:
        return {"kind": "none", "url": None}
    return {"kind": "gmail", "url": GMAIL_SEARCH_PREFIX + urllib.parse.quote(mid, safe="")}
