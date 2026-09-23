# -*- coding: utf-8 -*-
"""CLI / 领域层的日期闸门（2026-09-23 二轮审计）。

为什么必须有：`2026-02-31` 这类"日历上不存在"的日期能过正则，落库后
`.ics` 导出与看板时间线对它是**静默跳过**——用户看不到自己的面试从日历里消失，
却也不会收到任何报错。Web 侧已经装了闸门，CLI / MCP 侧此前没有，于是「同一份
数据、两个入口、两套判定」。

两类口径不要混：纯日期（答复截止日 / 最近联系 / 下次跟进）用 `check_date`；
带时刻或纯日期的（邮件日期 / 面试时间 / 宣讲会时间）用 `check_when`。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from jobws_core import tracker  # noqa: E402

BAD_DAY = "2026-02-31"


def _ws(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(os.path.join(ws, "05_投递追踪"))
    return ws


def _invoke(monkeypatch, capsys, argv):
    import jobws  # noqa: E402

    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        code = jobws.main()
    except SystemExit as exc:
        code = exc.code
    code = 0 if code is None else code
    capsys.readouterr()
    return code


def _cmd(ws, *rest):
    return ["track", "--workspace", ws] + list(rest)


# ---- check_when 本体 ---------------------------------------------------------

def test_check_when_accepts_date_and_datetime():
    assert tracker.check_when("2026-09-30", "时间") is None
    assert tracker.check_when("2026-09-30 14:00", "时间") is None
    assert tracker.check_when("2026-09-30 14:00:30", "时间") is None
    assert tracker.check_when("", "时间") is None


def test_check_when_rejects_impossible_moments():
    for raw in (BAD_DAY, BAD_DAY + " 14:00", "2026-09-30 25:00", "2026-09-30 14:61",
                "9/30/2026", "2026-9-30"):
        assert tracker.check_when(raw, "时间"), raw


# ---- CLI：纯日期 -------------------------------------------------------------

def test_cli_offer_deadline_rejects_impossible_day(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "offer", "add", "--company", "示例公司",
                        "--deadline", BAD_DAY)) != 0
    assert tracker.read_offers(ws) == [], "假日期不该落盘"


def test_cli_offer_deadline_accepts_a_real_day(tmp_path, monkeypatch, capsys):
    """否定验证：合法日期照常通过（闸门不许变成"一律拒绝"）。"""
    ws = _ws(tmp_path)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "offer", "add", "--company", "示例公司",
                        "--deadline", "2026-09-30")) == 0
    assert tracker.read_offers(ws)[0]["答复截止日"] == "2026-09-30"


def test_cli_contact_dates_reject_impossible_day(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "contact", "add", "--name", "张老师",
                        "--next-follow", BAD_DAY)) != 0
    assert tracker.read_contacts(ws) == []


def test_cli_contact_update_only_checks_touched_fields(tmp_path, monkeypatch, capsys):
    """存量坏日期不该挡住一次无关的更新（只校验本次真正改动的字段）。"""
    ws = _ws(tmp_path)
    tracker.write_contacts([{"联系人id": "C001", "姓名": "张老师",
                             "最近联系": BAD_DAY}], ws)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "contact", "update", "--id", "C001", "--note", "已回信")) == 0
    assert tracker.read_contacts(ws)[0]["备注"] == "已回信"


# ---- CLI：日期或时间 ---------------------------------------------------------

def test_cli_mail_update_rejects_impossible_datetime(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    tracker.write_mails([{"邮件id": "M001", "主题": "面试通知",
                          "日期": "2026-09-16 10:00"}], ws)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "mail", "update", "--id", "M001",
                        "--when", BAD_DAY + " 10:00")) != 0
    assert tracker.read_mails(ws)[0]["日期"] == "2026-09-16 10:00"


def test_cli_talk_update_rejects_impossible_time(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    tracker.write_talks([{"宣讲会id": "T001", "公司": "示例公司",
                          "时间": "2026-09-30 14:00"}], ws)
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "talk", "update", "--id", "T001", "--when", BAD_DAY)) != 0
    assert tracker.read_talks(ws)[0]["时间"] == "2026-09-30 14:00"


# ---- 领域层：面试两段式 -------------------------------------------------------

def test_interview_preview_rejects_impossible_time(tmp_path):
    ws = _ws(tmp_path)
    errors, plan = tracker.preview_interview_add_fields(
        {"公司": "示例公司", "轮次": "一面", "结果": "待定", "面试时间": BAD_DAY + " 14:00"}, ws)
    assert errors, "假日期必须在预览阶段就被拦下（否则会静默进 .ics 的跳过分支）"
    assert plan is None or not plan.get("payload")


def test_interview_preview_accepts_date_with_clock(tmp_path):
    ws = _ws(tmp_path)
    errors, _plan = tracker.preview_interview_add_fields(
        {"公司": "示例公司", "轮次": "一面", "结果": "待定",
         "面试时间": "2026-09-30 14:00"}, ws)
    assert errors == [], errors


def test_mail_preview_rejects_impossible_datetime(tmp_path):
    ws = _ws(tmp_path)
    errors, _plan = tracker.preview_mail_fields(
        {"主题": "面试通知", "日期": BAD_DAY}, ws)
    assert errors
