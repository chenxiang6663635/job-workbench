# -*- coding: utf-8 -*-
"""mail_dates 纯函数直测（2026-10-08 审计 1.2 的测试盲区项）。

这个模块的自述里有两处**反向结论**陷阱，本文件逐条钉住：

1. 时长表达（"3 天内"）的基准是**邮件发出的那天**，不是"今天"——三天前收到的邮件
   写"3 天内"，今天再看应当已过期；按今天算会得出"还有 3 天"的反向结论；
2. `coerce_date` 必须认 RFC 5322（IMAP `Date` 头的唯一真实形态）——此前只认 ISO，
   每封邮件的时长基准都静默退化成"今天"（2026-09-25 真机）。

另有两条**已知边界（刻意不做）**同样上锁：无前缀「周五」不解析；工作日只跳周末、
不跳法定节假日。
"""
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "packages", "jobws-core", "src"))

from jobws_core import mail_dates  # noqa: E402

REF = date(2026, 10, 9)          # 周五


# --- coerce_date -------------------------------------------------------------

def test_coerce_date_accepts_rfc5322_mail_header():
    """RFC 5322 是唯一真实入口：不认它，每封邮件的时长基准都会静默退化成
    「今天」——那正是 2026-09-25 真机反向结论的根因。"""
    assert mail_dates.coerce_date(
        "Mon, 25 Sep 2026 10:30:00 +0800") == date(2026, 9, 25)


def test_coerce_date_accepts_date_datetime_and_iso_forms():
    assert mail_dates.coerce_date(date(2026, 9, 25)) == date(2026, 9, 25)
    assert mail_dates.coerce_date(datetime(2026, 9, 25, 10, 30)) == date(2026, 9, 25)
    assert mail_dates.coerce_date("2026-09-25") == date(2026, 9, 25)
    assert mail_dates.coerce_date("2026-09-25 14:00") == date(2026, 9, 25)
    assert mail_dates.coerce_date("2026/9/5") == date(2026, 9, 5)


def test_coerce_date_rejects_invalid_or_empty():
    assert mail_dates.coerce_date("") is None
    assert mail_dates.coerce_date(None) is None
    assert mail_dates.coerce_date("不是日期") is None
    assert mail_dates.coerce_date("2026-02-31") is None       # 日历非法，不是格式合法


# --- add_workdays ------------------------------------------------------------

def test_add_workdays_skips_weekend():
    friday = date(2026, 10, 9)
    assert mail_dates.add_workdays(friday, 0) == friday                 # 0 个 = 原地
    assert mail_dates.add_workdays(friday, 1) == date(2026, 10, 12)     # 跨周末到周一
    assert mail_dates.add_workdays(date(2026, 10, 10), 1) == date(2026, 10, 12)  # 周六起算


def test_add_workdays_counts_only_weekdays_across_weeks():
    # 周三 + 5 个工作日：周四、周五、下周一、二、三
    assert mail_dates.add_workdays(date(2026, 10, 7), 5) == date(2026, 10, 14)


# --- find_absolute -----------------------------------------------------------

def test_find_absolute_iso_and_cn_full_are_high_confidence():
    assert mail_dates.find_absolute("2026-09-25 截止", REF) == ("2026-09-25", "high", "")
    assert mail_dates.find_absolute("2026年9月25日 前反馈", REF) == ("2026-09-25", "high", "")


def test_find_absolute_short_cn_borrows_ref_year_and_flags_low():
    value, confidence, note = mail_dates.find_absolute("9月25日 前到岗", REF)
    assert value == "2026-09-25" and confidence == "low"
    assert "没有年份" in note and "请确认" in note


def test_find_absolute_relative_days():
    assert mail_dates.find_absolute("明天 面试", REF)[0] == "2026-10-10"
    assert mail_dates.find_absolute("后天 截止", REF)[0] == "2026-10-11"
    # 「大后天」先于「后天」命中（词表顺序即优先级）
    assert mail_dates.find_absolute("大后天 截止", REF)[0] == "2026-10-12"


def test_find_absolute_this_and_next_weekday_natural_week():
    # 本周以周一为起点；本周一在周五看来已经过去——那正是「已过期」信号，照给
    assert mail_dates.find_absolute("本周五 前", REF)[0] == "2026-10-09"
    assert mail_dates.find_absolute("本周一 前", REF)[0] == "2026-10-05"
    assert mail_dates.find_absolute("下周一 入职", REF)[0] == "2026-10-12"


def test_find_absolute_bare_weekday_is_not_parsed():
    """无前缀「周五」起算点随人而异——宁可漏也不猜（模块自述的已知边界）。"""
    assert mail_dates.find_absolute("周五 之前", REF) == ("", "", "")


def test_find_absolute_empty_when_nothing_found():
    assert mail_dates.find_absolute("欢迎投递，期待与你共事", REF) == ("", "", "")


# --- duration_date：基准是邮件发出那天（反向结论陷阱的正面战场）-------------

def _token(text):
    """与 `mail_facts._DURATION_RE` 同形（含「个」量词；group(2) 是单位）。"""
    match = re.search(r"(\d{1,3})\s*(?:个)?\s*(工作日|自然日|天|日|小时)\s*(?:内|以内|之内)",
                      text)
    assert match, text
    return match


def test_duration_uses_mail_date_not_today():
    """三天前收到的邮件写「3 天内」：按邮件日期算应当已过期；按今天算会得出
    「还有 3 天」——反向结论。"""
    value, confidence, note = mail_dates.duration_date(
        _token("3 天内回复"), REF, date(2026, 10, 5))
    assert value == "2026-10-08" and confidence == "low"
    assert "邮件日期 2026-10-05" in note
    assert "已过期" in note


def test_duration_falls_back_to_ref_and_says_so():
    value, _confidence, note = mail_dates.duration_date(_token("3 天内回复"), REF, None)
    assert value == "2026-10-12"
    assert "未取到邮件日期" in note
    assert "已过期" not in note


def test_duration_hours_are_day_granularity():
    assert mail_dates.duration_date(_token("24 小时内"), REF, None)[0] == "2026-10-10"
    assert mail_dates.duration_date(_token("6 小时内"), REF, None)[0] == "2026-10-09"


def test_duration_workdays_skip_weekend_and_note_holidays():
    # 周三收到、3 个工作日：周四、周五、下周一
    value, _confidence, note = mail_dates.duration_date(
        _token("3 个工作日内"), REF, date(2026, 10, 7))
    assert value == "2026-10-12"
    assert "未跳法定节假日" in note


# --- with_clock --------------------------------------------------------------

def test_with_clock_appends_time_from_same_line():
    assert mail_dates.with_clock("2026-09-25", "2026-09-25 14:00 前") == "2026-09-25 14:00"
    assert mail_dates.with_clock("2026-09-25", "2026-09-25 前") == "2026-09-25"
