# -*- coding: utf-8 -*-
"""五张从表的日期入口闸门（2026-09-23 审计 P1 补网 + 批末独立审查）。

背景：`check_date` 此前只装在投递主表的三条写路径上，其余表照收任何字符串。
后果不是"界面报错"，而是**静默丢数据**——日历上不存在的日子（`2026-02-31`）
写进去以后，导出 .ics 时那一行被跳过（面试从日历里消失）、看板时间线同样跳过，
而界面上一切正常。

两类字段两种口径，别混：
- **纯日期**（答复截止日 / 最近联系 / 下次跟进）：`2026-02-31` 必须拒；
- **日期或时间**（邮件日期 / 面试时间 / 宣讲会时间）：`2026-09-16 10:00` 是它们的
  常见形态，不能被纯日期校验误拒（这条正是加闸门时被测出来的：邮件日期带时刻）。

每个域都配一条"合法值必须通过"的否定验证——闸门装成"一律拒绝"比没有更糟。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
BAD_DAY = "2026-02-31"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """与 test_status_suggest_api 同款隔离：应用根指向 tmp，别读到真实工作区。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402

    return TestClient(main.app)


def _post(client, path, body):
    return client.post("/api/progress/%s" % path, params={"ws": WS}, json=body)


# ---- 纯日期 -----------------------------------------------------------------

def test_offer_deadline_rejects_impossible_day(client):
    res = _post(client, "offers",
                {"公司": "示例公司", "岗位": "示例岗位", "答复截止日": BAD_DAY})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "date.format"


def test_offer_deadline_accepts_a_real_day(client):
    res = _post(client, "offers",
                {"公司": "示例公司", "岗位": "示例岗位", "答复截止日": "2026-09-30"})
    assert res.status_code == 201, res.text


def test_contact_dates_reject_impossible_day(client):
    res = _post(client, "contacts", {"姓名": "张老师", "下次跟进": BAD_DAY})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "date.format"


def test_contact_accepts_empty_dates(client):
    """「还没约」是合法状态：空值一律放行。"""
    res = _post(client, "contacts", {"姓名": "张老师"})
    assert res.status_code == 201, res.text


# ---- 日期或时间 --------------------------------------------------------------

def test_interview_time_rejects_impossible_day(client):
    res = _post(client, "interviews",
                {"公司": "示例公司", "岗位": "示例岗位", "轮次": "一面",
                 "面试时间": BAD_DAY + " 14:00"})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "date.when"


def test_interview_time_accepts_date_with_clock(client):
    res = _post(client, "interviews",
                {"公司": "示例公司", "岗位": "示例岗位", "轮次": "一面",
                 "面试时间": "2026-09-30 14:00"})
    assert res.status_code == 201, res.text


def test_mail_date_accepts_date_with_clock(client):
    res = _post(client, "mails",
                {"方向": "收", "主题": "面试通知", "日期": "2026-09-16 10:00"})
    assert res.status_code == 201, res.text


def test_mail_date_rejects_impossible_day(client):
    res = _post(client, "mails",
                {"方向": "收", "主题": "面试通知", "日期": BAD_DAY + " 10:00"})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "date.when"


def test_talk_time_rejects_impossible_day(client):
    res = _post(client, "talks", {"公司": "示例公司", "时间": BAD_DAY})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "date.when"
