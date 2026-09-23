# -*- coding: utf-8 -*-
"""会议链接识别：URL 提取 + 白名单匹配（批 9）。

业界没有权威的通用正则库，各平台 join-link 的稳定特征是**域名 + 路径前缀**
（Zoom `/j/{id}`、Meet `meet.google.com/{xxx-xxxx-xxx}`、Teams
`/l/meetup-join/…`、Webex `j.php?MTID=…`、腾讯会议 `/dm/{id}`），
所以这里用白名单而不是 `https?://` 通配——正文里绝大多数 URL 不是会议入口。

拆成独立模块的理由（规模预算 300 行）：`mail_ics`（ICS 里的 URL 属性）与
`mail_facts`（正文按行找链接）都要用它，放谁那里都会变成环。
"""

import re

_URL_RE = re.compile(r"""https?://[^\s<>"'（）()【】\[\]，。；、]+""", re.IGNORECASE)

# 域名后缀 → 允许的路径前缀（空元组 = 只认域名，不限制路径）
MEETING_HOSTS = (
    ("zoom.us", ("/j/", "/w/", "/my/")),
    ("meet.google.com", ("/",)),
    ("teams.microsoft.com", ("/l/meetup-join/", "/meet/")),
    ("teams.live.com", ("/meet/",)),
    ("webex.com", ("/j.php", "/meet/", "/webappng/")),
    ("meeting.tencent.com", ("/dm/", "/j/")),
)

# URL 尾部的标点不能算进链接（中文正文里常见「链接：https://…。」）
TRAILING_PUNCT = ".,;:)]}>,，。；：、）】》"


def find_urls(text):
    """按出现顺序取出文本里的 URL（去尾部标点、保留查询串）。"""
    return [url.rstrip(TRAILING_PUNCT) for url in _URL_RE.findall(text or "")]


def host_path(url):
    """URL → (host, path)（host 小写、去端口；非法 URL 返回空串）。"""
    rest = url.split("://", 1)[1] if "://" in url else (url or "")
    host = rest.split("/", 1)[0].split("?", 1)[0].lower()
    path = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
    path = path.split("?", 1)[0]
    if "@" in host:                    # 去掉可能存在的 userinfo
        host = host.rsplit("@", 1)[1]
    host = host.split(":", 1)[0]       # 去掉端口
    return host, path


def is_meeting_url(url):
    """是否属于白名单内的会议入口（域名后缀 + 路径前缀双重判定）。"""
    host, path = host_path(url)
    if not host:
        return False
    for suffix, prefixes in MEETING_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            if not prefixes or any(path.startswith(p) for p in prefixes):
                return True
    return False
