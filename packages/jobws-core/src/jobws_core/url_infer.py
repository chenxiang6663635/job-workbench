# -*- coding: utf-8 -*-
"""从岗位链接里做**本地**推断（零依赖、纯函数、不联网）。

用途：在「新增投递」表单粘贴岗位页 URL 时，自动补全「链接」并尽力识别「来源」；
识别不出来就留空，由用户自选。

**公司 / 岗位不做推断**：从 URL 猜一家公司的正式中文名（`tcl` → `TCL`？
`TCL 空调事业部`？）必然靠不住——半吊子的预填比不填更糟，用户还得先去改它。
这个取舍是刻意的：推断层只做能解释、能被用户一眼复核的事。

口径：
1. 只认**能解释**的映射：域名后缀 → 来源枚举值；推断不出的域名返回空来源
   （招聘平台里没有对应枚举值的站点——BOSS / 智联等——不猜「其他」）；
2. URL 规范化：补 `https://` 前缀（从地址栏复制的常缺 scheme）；
3. 非 URL 返回 `ok=False` 与人话说明——它是预填助手，不是校验器，
   绝不阻拦用户手填任何值。

用法（Web 端点 / 前端粘贴回调共用同一实现）：

    infer_from_url("www.nowcoder.com/jobs/123")
    -> {"ok": True, "链接": "https://www.nowcoder.com/jobs/123",
        "来源": "牛客", "说明": [...]}
"""

import re

# 域名 → 来源。仅收能明确识别的站点；对应不上枚举值的平台不猜（见模块注释）。
_SOURCE_BY_DOMAIN = (
    ("nowcoder.com", "牛客"),
    ("yingjiesheng.com", "应届生求职网"),
)

# 学校域名后缀 → 学校就业网
_SCHOOL_SUFFIXES = (".edu.cn",)

# 企业校招页的常见子域前缀（careers.tcl.com / xyzp.xxx.com）→ 企业校招官网
_CAMPUS_SUBDOMAINS = ("careers.", "campus.", "jobs.", "job.", "xyzp.", "recruit.")

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _host_of(url):
    """取 host（小写、去 userinfo 与端口），无 scheme 时返回空串。"""
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    host = host.split("@")[-1]
    host = host.split(":")[0]
    return host


def infer_from_url(raw):
    """从粘贴的链接推断可预填的值（纯函数，不做任何 IO）。

    返回 {"ok": bool, "链接": str, "来源": str, "说明": [str]}：
    - `ok=False` 时「链接」为空、说明给出原因；
    - `来源` 为空表示"不猜"，由用户在下拉里选。
    """
    text = (raw or "").strip()
    if not text:
        return {"ok": False, "链接": "", "来源": "", "说明": ["链接为空"]}

    if not _SCHEME_RE.match(text):
        text = "https://" + text

    host = _host_of(text)
    if not host or "." not in host or " " in text:
        return {"ok": False, "链接": "", "来源": "",
                "说明": ["看起来不是一条 URL（缺少域名）"]}

    notes = []
    source = ""
    for domain, name in _SOURCE_BY_DOMAIN:
        if host == domain or host.endswith("." + domain):
            source = name
            notes.append("域名 %s → 来源「%s」" % (domain, name))
            break
    if not source:
        for suffix in _SCHOOL_SUFFIXES:
            if host.endswith(suffix):
                source = "学校就业网"
                notes.append("学校域名（%s）→ 来源「学校就业网」" % suffix)
                break
    if not source:
        for prefix in _CAMPUS_SUBDOMAINS:
            if host.startswith(prefix):
                source = "企业校招官网"
                notes.append("招聘子域（%s）→ 来源「企业校招官网」" % prefix)
                break
    if not source:
        notes.append("域名不在已知映射里，来源留空请手选")

    notes.append("公司与岗位无法从链接可靠推断，请手动填写")
    return {"ok": True, "链接": text, "来源": source, "说明": notes}
