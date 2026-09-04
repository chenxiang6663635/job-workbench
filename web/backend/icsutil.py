# -*- coding: utf-8 -*-
"""ICS 日程导出（RFC 5545 子集），纯标准库手写。

只生成面试日程需要的部分：VCALENDAR 裹若干 VEVENT，每个事件带一个
提前提醒的 VALARM。不引入 icalendar 之类的依赖——这个体量自己写更可控。

两个容易踩的点：
1. 行尾必须 CRLF（RFC 5545 要求），用 \\n 生成的文件部分日历客户端不认。
2. 长行需按 75 字节折叠（fold），且中文不能从中间截断，否则乱码。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

CRLF = "\r\n"

# 面试时间的常见写法：2026-09-05 14:00 / 2026-09-05T14:00 / 2026-09-05
DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?$"
)


def parse_when(value):
    """解析面试时间，返回 (datetime, 是否含具体时刻)。无法解析返回 None。"""
    raw = (value or "").strip()
    m = DATETIME_RE.match(raw)
    if not m:
        return None
    year, month, day, hour, minute = m.groups()
    try:
        if hour is None:
            return datetime(int(year), int(month), int(day)), False
        return (datetime(int(year), int(month), int(day), int(hour), int(minute)), True)
    except ValueError:
        return None


def _escape(text):
    """RFC 5545 文本转义：反斜杠、分号、逗号、换行。"""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\")
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\r\n", "\n").replace("\n", "\\n")
    return s


def _fold(line):
    """按 75 字节折叠长行，续行以单个空格开头。

    按 UTF-8 字节计数但不在多字节字符中间断开——从字符逐个累加，
    保证断点是完整字符。
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    out = []
    current = ""
    current_bytes = 0
    for ch in line:
        size = len(ch.encode("utf-8"))
        if current_bytes + size > 73:       # 预留续行首空格
            out.append(current)
            current = ""
            current_bytes = 0
        current += ch
        current_bytes += size
    if current:
        out.append(current)
    return CRLF.join([" " + part if i > 0 else part for i, part in enumerate(out)])


def _stamp(dt):
    """本地时间（floating time），不绑时区——面试时间是用户本机的约定时间。"""
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(events, calendar_name="求职面试日程", reminder_minutes=60):
    """生成 ICS 文本。

    events：字典列表，键为 uid / title / start / end / location / description。
    start/end 为 datetime；end 缺省时按 start + 1 小时。
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//job-workbench//Interview Schedule//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:%s" % _escape(calendar_name),
    ]

    for ev in events:
        start = ev.get("start")
        if start is None:
            continue
        end = ev.get("end") or (start + timedelta(hours=1))
        lines.append("BEGIN:VEVENT")
        lines.append("UID:%s" % _escape(ev.get("uid") or _stamp(start)))
        lines.append("DTSTAMP:%s" % _stamp(datetime.now()))
        lines.append("DTSTART:%s" % _stamp(start))
        lines.append("DTEND:%s" % _stamp(end))
        lines.append("SUMMARY:%s" % _escape(ev.get("title") or "面试"))
        if ev.get("location"):
            lines.append("LOCATION:%s" % _escape(ev["location"]))
        if ev.get("description"):
            lines.append("DESCRIPTION:%s" % _escape(ev["description"]))

        # 提前提醒
        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-PT%dM" % int(reminder_minutes))
        lines.append("ACTION:DISPLAY")
        lines.append("DESCRIPTION:%s" % _escape(
            "面试提醒：%s" % (ev.get("title") or "面试")))
        lines.append("END:VALARM")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return CRLF.join(_fold(line) for line in lines) + CRLF


def events_from_interviews(interviews):
    """面试记录 → ICS 事件。没有时间的跳过（日程必须有确定时间）。"""
    events = []
    for row in interviews:
        parsed = parse_when(row.get("面试时间", ""))
        if not parsed:
            continue
        start, has_time = parsed
        # 只有日期没有时刻的，按当天 10:00 占位（避免变成全天事件丢失提醒）
        if not has_time:
            start = start.replace(hour=10, minute=0)

        company = (row.get("公司") or "").strip()
        role = (row.get("岗位") or "").strip()
        round_name = (row.get("轮次") or "").strip()
        title = "%s %s %s" % (company, role, round_name) if company else round_name

        parts = []
        if row.get("面试官"):
            parts.append("面试官：%s" % row["面试官"])
        if row.get("形式"):
            parts.append("形式：%s" % row["形式"])
        if row.get("关联记录"):
            parts.append("关联记录：%s" % row["关联记录"])
        if row.get("复盘与改进"):
            parts.append("上次复盘：%s" % row["复盘与改进"])

        events.append({
            "uid": "interview-%s@job-workbench" % (row.get("面试id") or ""),
            "title": title.strip() or "面试",
            "start": start,
            "end": start + timedelta(hours=1),
            "location": "",
            "description": "\n".join(parts),
        })
    return events
