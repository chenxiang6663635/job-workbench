# -*- coding: utf-8 -*-
"""邮件正文 / ICS → 候选事实（批 9）：纯函数口径。

钉四件事：

1. **ICS 优先**：会议邀请的结构化字段（时间 / 会议链接）以 `text/calendar` 部件为准，
   正文正则只做兜底；
2. **引用与签名不参与解析**：回复邮件里被引的旧时间 / 旧链接不得当成本次线索；
3. **白名单才算会议链接**：只认各平台 join-link 的域名与路径前缀，不做过宽匹配；
4. **每条事实都带出处与把握程度**：没有证据的猜测不产出。
"""

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from jobws_core import mail_facts  # noqa: E402

TODAY = datetime.date(2026, 9, 22)

ICS = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "METHOD:REQUEST",
    "BEGIN:VEVENT",
    "UID:abc-123@example.com",
    "DTSTART;TZID=Asia/Shanghai:20260925T140000",
    "DTEND;TZID=Asia/Shanghai:20260925T150000",
    "SUMMARY:面试邀请（技术面）",
    "LOCATION:线上",
    "URL:https://meeting.tencent.com/dm/abc123",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
])


def _facts_by_kind(facts, kind):
    return [f for f in facts if f["kind"] == kind]


def test_ics_time_is_high_confidence_and_keeps_wall_clock():
    facts = mail_facts.extract_facts("（正文略）", ics_text=ICS, today=TODAY)
    times = _facts_by_kind(facts, "时间")
    assert [f["value"] for f in times] == ["2026-09-25 14:00"]
    assert times[0]["confidence"] == "high"
    assert times[0]["source"] == "ics"
    assert times[0]["evidence"], "事实必须带原文出处，便于复核"


def test_ics_meeting_url_is_extracted_from_url_property():
    facts = mail_facts.extract_facts("（正文略）", ics_text=ICS, today=TODAY)
    links = _facts_by_kind(facts, "会议链接")
    assert [f["value"] for f in links] == ["https://meeting.tencent.com/dm/abc123"]
    assert links[0]["source"] == "ics"


def test_ics_folded_lines_are_unfolded():
    """RFC 5545 的折行（CRLF + 空格）必须还原，否则链接会被截断成半截。"""
    folded = "\r\n".join([
        "BEGIN:VCALENDAR",
        "BEGIN:VEVENT",
        "DTSTART:20260925T060000Z",
        "SUMMARY:第一轮面试",
        "URL:https://zoom.us/j/1234567890?pwd=ab",
        " cd",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    facts = mail_facts.extract_facts("", ics_text=folded, today=TODAY)
    assert [f["value"] for f in _facts_by_kind(facts, "会议链接")] == [
        "https://zoom.us/j/1234567890?pwd=abcd"
    ]
    assert [f["value"] for f in _facts_by_kind(facts, "时间")] == ["2026-09-25 06:00"]


def test_ics_rrule_is_flagged_not_expanded():
    """重复会议不展开，但必须标注——否则用户会把首场时间当成唯一场次。"""
    ics = ICS.replace("END:VEVENT", "RRULE:FREQ=WEEKLY\r\nEND:VEVENT")
    time_fact = _facts_by_kind(mail_facts.extract_facts("", ics_text=ics, today=TODAY),
                               "时间")[0]
    assert "重复会议" in time_fact["note"]
    assert time_fact["confidence"] == "high"


# --- 正文兜底：引用剥离 / 白名单 / 日期时间 ---------------------------------------

def test_reference_block_is_ignored():
    """被引用的旧时间与旧链接不能当成本次线索（回复邮件的高频误判）。"""
    body = (
        "您好，面试改到 2026-09-25 14:00，会议链接：https://meeting.tencent.com/dm/new001\n"
        "\n"
        "在 2026-09-20 10:00 写道：\n"
        "> 面试时间：2026-09-23 09:00，链接：https://zoom.us/j/1111111111\n"
    )
    facts = mail_facts.extract_facts(body, today=TODAY)
    assert [f["value"] for f in _facts_by_kind(facts, "会议链接")] == [
        "https://meeting.tencent.com/dm/new001"]
    assert [f["value"] for f in _facts_by_kind(facts, "时间")] == ["2026-09-25 14:00"]


def test_signature_block_is_ignored():
    body = ("详见 2026-09-25 14:00 的面试安排\n"
            "--\n"
            "某某科技 官网：https://zoom.us/j/9999999999\n")
    facts = mail_facts.extract_facts(body, today=TODAY)
    assert _facts_by_kind(facts, "会议链接") == []


def test_body_meeting_link_whitelist_only():
    body = ("加入会议：https://us02web.zoom.us/j/1234567890?pwd=xyz\n"
            "公司主页：https://example.com/j/123\n"
            "Teams：https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc\n")
    links = [f["value"] for f in _facts_by_kind(
        mail_facts.extract_facts(body, today=TODAY), "会议链接")]
    assert links == ["https://us02web.zoom.us/j/1234567890?pwd=xyz",
                     "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc"]


def test_body_cn_date_without_year_is_low_confidence():
    facts = mail_facts.extract_facts("面试时间：9月25日 14:00", today=TODAY)
    time_fact = _facts_by_kind(facts, "时间")[0]
    assert time_fact["value"] == "2026-09-25 14:00"
    assert time_fact["confidence"] == "low"
    assert "年份" in time_fact["note"]


def test_relative_date_is_low_confidence():
    facts = mail_facts.extract_facts("电话沟通改到明天 14:00", today=TODAY)
    time_fact = _facts_by_kind(facts, "时间")[0]
    assert time_fact["value"] == "2026-09-23 14:00"
    assert time_fact["confidence"] == "low"


def test_ics_link_wins_over_body_duplicate():
    body = "会议：https://meeting.tencent.com/dm/abc123"
    links = _facts_by_kind(mail_facts.extract_facts(body, ics_text=ICS, today=TODAY),
                           "会议链接")
    assert len(links) == 1
    assert links[0]["source"] == "ics"


# --- 截断：按行边界并优先保留含链接 / 日期的行 ------------------------------------

def test_smart_truncate_keeps_url_and_date_lines():
    import imap_fetch

    filler = ("这是一段很长的正文占位。" * 30 + "\n") * 40
    body = filler + "\n面试时间：2026-09-25 14:00\n链接：https://meeting.tencent.com/dm/tail01\n"

    out = imap_fetch.smart_truncate(body, limit=4000)

    assert "https://meeting.tencent.com/dm/tail01" in out, "尾部会议链接不能被截断丢掉"
    assert "2026-09-25 14:00" in out
    assert len(out) <= 4000 + 60


# --- 阶段与记录匹配（复用 status_parse 的口径，不另造一套） ------------------------

ROWS = [
    {"id": "A001", "公司": "云帆智算", "岗位": "后端工程师", "当前阶段": "已投"},
    {"id": "A007", "公司": "星河数据", "岗位": "热管理", "当前阶段": "测评"},
]


def test_stage_fact_carries_stage_and_target():
    facts = mail_facts.extract_facts("云帆智算：很遗憾，本次不再推进。", today=TODAY, rows=ROWS)
    stage = _facts_by_kind(facts, "阶段")[0]
    assert stage["value"] == "已挂"
    assert stage["targetId"] == "A001"
    assert stage["evidence"], "阶段建议同样要留原文证据"


def test_record_fact_names_the_matched_row():
    facts = mail_facts.extract_facts("云帆智算 后端工程师 面试邀请", today=TODAY, rows=ROWS)
    record = _facts_by_kind(facts, "公司岗位")[0]
    assert record["value"] == "A001"
    assert "云帆智算" in record["label"]
    assert record["targetId"] == "A001"


def test_focus_id_beats_substring_matching():
    """用户点选的记录比子串匹配权威（通篇不写公司名的站内信走这条）。"""
    facts = mail_facts.extract_facts("您的简历已进入笔试环节", today=TODAY,
                                     rows=ROWS, focus_id="A007")
    record = _facts_by_kind(facts, "公司岗位")[0]
    assert record["value"] == "A007"
    assert record["note"] == "手动指定"


def test_no_match_means_no_record_fact():
    facts = mail_facts.extract_facts("某某公司 面试邀请", today=TODAY, rows=ROWS)
    assert _facts_by_kind(facts, "公司岗位") == []


def test_next_weekday_uses_monday_based_weeks():
    """「下周X」按自然周（周一为起点）算：周日的「下周一」= 第二天。"""
    sunday = datetime.date(2026, 9, 27)
    facts = mail_facts.extract_facts("下周一 14:00 面试", today=sunday)
    assert [f["value"] for f in _facts_by_kind(facts, "时间")] == ["2026-09-28 14:00"]


def test_quote_separator_must_be_dashes_only():
    """整行连字符才算引用分隔线：Markdown 分隔线后的正文不能被截掉。"""
    kept = mail_facts.strip_quoted("正文\n----- 以下是补充\n链接：https://zoom.us/j/123")
    assert "以下是补充" in kept
    assert mail_facts.strip_quoted("正文\n-------\n引用内容").strip() == "正文"


def test_fully_quoted_body_yields_nothing():
    """整段都是引用的邮件不该产出任何事实（避免把上一封的线索当本次）。"""
    body = "> 面试时间：2026-09-23 09:00\n> 链接：https://zoom.us/j/1111111111\n"
    assert mail_facts.extract_facts(body, today=TODAY) == []
