# -*- coding: utf-8 -*-
"""招聘邮件里的**日期与时长解析**（纯函数、无 I/O）。

从 `mail_facts` 拆出来（2026-09-24：那边随「截止 / 链接有效期」涨到 380 行、超了
逻辑型 300 行的规模预算）。分界：这边只回答"这一行说的是哪一天、有多确定"，
**不管它属于哪一类事实**（时间 / 截止 / 链接有效期由 `mail_facts` 判）。

## 基准（谁算"今天"）

- **绝对日期**（ISO / 「2026年9月25日」/「9月25日」）不依赖基准；
- **相对日**（今天 / 明天 / 本周X / 下周X）以**解析时那天**为基准；
- **时长表达**（N 天内 / N 小时内 / N 个工作日内）以**邮件发出的那天**为基准——
  三天前收到的邮件写「3 天内」，今天再看应当已经过期；按今天算会得出"还有 3 天"
  的反向结论。

## 已知边界（刻意不做）

- 「本周X」按自然周（周一为起点）计算，**可能算出已经过去的日期**——那正是
  「已过期」的信号，照给（把握 low，值供人核对）；
- 无前缀的「周五」不解析（起算点随人而异，宁可漏也不猜）；
- 工作日只跳周末、**不跳法定节假日**（那需要日历数据）。
"""

import datetime
import re

from .status_parse import DATE_CN_RE, DATE_ISO_RE

# 「2026年9月25日」这种全量中文日期（与 status_parse 的短式「9月25日」区分）
DATE_CN_FULL_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)(?!\d)")
_REL_DAYS = (("大后天", 3), ("后天", 2), ("明天", 1), ("今天", 0))
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
THIS_WEEKDAY_RE = re.compile(r"本\s*周\s*([一二三四五六日天])")
NEXT_WEEKDAY_RE = re.compile(r"下\s*周\s*([一二三四五六日天])")


def with_clock(value, line):
    """给日期补上同一行里的钟点（"2026-09-25" + "14:00"）。"""
    t = TIME_RE.search(line)
    if t:
        value += " %02d:%02d" % (int(t.group(1)), int(t.group(2)))
    return value


def coerce_date(value):
    """收敛成 date：接受 date / datetime / 'YYYY-MM-DD[ HH:MM]' / 'YYYY/M/D'。"""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", (value or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def add_workdays(start, n):
    """从 start 起算 n 个工作日（跳过周六周日；法定节假日不跳）。"""
    day, added = start, 0
    while added < n:
        day += datetime.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day


def find_absolute(line, ref):
    """绝对日期 / 相对日 → (日期, 把握, 说明)；都没有时返回三个空串。

    把握：写出年份的（ISO / 中文全量）为 high；缺年份、相对日为 low（须人工核对）。
    """
    m = DATE_ISO_RE.search(line)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups()), "high", ""
    m = DATE_CN_FULL_RE.search(line)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups()), "high", ""
    m = DATE_CN_RE.search(line)
    if m:
        mo, d = (int(x) for x in m.groups())
        return ("%04d-%02d-%02d" % (ref.year, mo, d), "low",
                "原文没有年份，按 %d 年记，请确认" % ref.year)
    rel = next(((n, delta) for n, delta in _REL_DAYS if n in line), None)
    if rel:
        day = ref + datetime.timedelta(days=rel[1])
        return day.isoformat(), "low", "相对日期，按 %s 计算，请确认" % ref.isoformat()
    m = THIS_WEEKDAY_RE.search(line)
    if m:
        # 本周X = 本周（周一为起点）的第 X 天；可能算出已过去的日期，
        # 那正是「已过期」的信号，照给，由人核对
        day = ref - datetime.timedelta(days=ref.weekday()) \
            + datetime.timedelta(days=_WEEKDAYS[m.group(1)])
        return (day.isoformat(), "low",
                "相对日期（本周，周一为起点），按 %s 计算，请确认" % ref.isoformat())
    m = NEXT_WEEKDAY_RE.search(line)
    if m:
        # 下周一 = 下一个自然周的周一（今天所在周为「本周」）
        day = ref + datetime.timedelta(days=7 - ref.weekday() + _WEEKDAYS[m.group(1)])
        return day.isoformat(), "low", "相对日期，按 %s 计算，请确认" % ref.isoformat()
    return "", "", ""


def duration_date(token, ref, mail_date):
    """时长表达 → (日期, 把握, 说明)；基准是**邮件发出的那天**。

    `token` 是调用方（`mail_facts`）用 `_DURATION_RE` 匹配到的结果——语气判定
    （"这句话是不是要你做点什么"）不在这一层，这里只管算。
    """
    n, unit = int(token.group(1)), token.group(2)
    base = mail_date or ref
    if unit == "小时":
        day = base + datetime.timedelta(days=n // 24)
    elif unit == "工作日":
        day = add_workdays(base, n)
    else:
        day = base + datetime.timedelta(days=n)
    basis = ("邮件日期 %s" % mail_date.isoformat()) if mail_date \
        else "%s（未取到邮件日期）" % ref.isoformat()
    note = "「%s」按%s起算，请确认" % (token.group(0), basis)
    if day < ref:
        note += "（已过期）"
    if unit == "工作日":
        note += "；工作日跳过周末，未跳法定节假日"
    return day.isoformat(), "low", note
