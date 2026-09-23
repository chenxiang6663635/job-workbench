# -*- coding: utf-8 -*-
"""ICS（iCalendar）最小解析：把会议邀请的结构化字段取出来（批 9）。

**为什么是自研而不是引入 `icalendar`**：仓内纪律是「不为小数据引入重依赖」，
而这里只需要 RFC 5545 的一小片——VEVENT 的 `DTSTART`/`SUMMARY`/`LOCATION`/
`URL`/`UID`/`RRULE` 与 RFC 7986 的 `CONFERENCE`。需要展开 `RRULE`（重复会议
逐场次）时再评估引入 `icalendar`（BSD-2）。

**已知边界（刻意不做）**：

- `RRULE` 不展开：只把 `recurring` 标出来，由事实卡片提示用户回原邮件确认；
- 时区只做**墙上时间**：`TZID` 只作标签保留，不做换算（换算需要时区库与用户
  时区设定）；`Z` 结尾按 UTC 记录并由调用方标注。
"""

import re

from .mail_links import find_urls

# URL 属性：标准 URL、RFC 7986 的 CONFERENCE，以及各厂商私有扩展
_URL_PROPERTIES = ("URL", "CONFERENCE", "X-GOOGLE-CONFERENCE",
                   "X-MICROSOFT-SKYPETEAMSMEETINGURL")

_DT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$")


def unfold(text):
    """RFC 5545 折行还原：换行后跟空格或 Tab 的行属于上一行的续行。

    **必须先做这一步再解析**：长 URL 常被折在半截，直接按行取值会拿到断链。
    """
    lines = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
            continue
        lines.append(raw)
    return lines


def split_property(line):
    """`NAME;PARAM=..:VALUE` → (NAME, params, VALUE)；非属性行返回空 name。"""
    head, sep, value = line.partition(":")
    if not sep:
        return "", {}, ""
    name, _, param_str = head.partition(";")
    params = {}
    for chunk in (param_str.split(";") if param_str else []):
        key, _, val = chunk.partition("=")
        if key.strip():
            params[key.strip().upper()] = val.strip().strip('"')
    return name.strip().upper(), params, value


def unescape(value):
    """ICS TEXT 值的转义还原（只处理最常见的三种）。"""
    return (value or "").replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")


def ics_datetime(value):
    """ICS 日期时间 → (墙上时间 "YYYY-MM-DD HH:MM", 是否 UTC)；不认识的形状返回 None。"""
    m = _DT_RE.match((value or "").strip())
    if not m:
        return None
    y, mo, d, h, mi, _s, z = m.groups()
    return "%s-%s-%s %s:%s" % (y, mo, d, h, mi), bool(z)


def _url_value(value):
    urls = find_urls(value)
    return urls[0] if urls else ""


def parse_ics(text):
    """最小 VEVENT 解析：返回事件列表（不展开 RRULE、不做时区换算）。

    每个事件：{start, startUtc, summary, location, urls, recurring, uid, rawStart}
      - `start` 是墙上时间（TZID 只作标签）；
      - `urls` 收集标准与厂商私有的会议 URL 属性值（已去尾部标点）；
      - `rawStart` 保留原始属性行，作为事实的出处。
    """
    events = []
    current = None
    for line in unfold(text):
        name, _params, value = split_property(line)
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {"start": "", "startUtc": False, "summary": "", "location": "",
                       "urls": [], "recurring": False, "uid": "", "rawStart": line}
            continue
        if name == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        if name == "DTSTART":
            parsed = ics_datetime(value)
            if parsed:
                current["start"], current["startUtc"] = parsed
                current["rawStart"] = line
        elif name == "SUMMARY":
            current["summary"] = unescape(value).strip()
        elif name == "LOCATION":
            current["location"] = unescape(value).strip()
        elif name == "UID":
            current["uid"] = value.strip()
        elif name == "RRULE":
            current["recurring"] = True
        elif name in _URL_PROPERTIES:
            url = _url_value(value)
            if url:
                current["urls"].append(url)
    return events
