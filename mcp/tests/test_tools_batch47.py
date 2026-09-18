# -*- coding: utf-8 -*-
"""批 4.7 新增 MCP 工具的**有数据**用例。

独立审查指认的缺口：此前新只读工具只有"空列表"与负路径的覆盖，`list_questions`
里一个变量名笔误（有数据必 NameError）因此活到了提审。这里把"表里有行"的正常
路径钉住——工具返回体有没有数据、字段裁剪是否生效，都必须在**真实行**上断言。
"""

import csv
import io
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (MCP_DIR, os.path.join(MCP_DIR, os.pardir, "tools")):
    _real = os.path.abspath(_p)
    if _real not in sys.path:
        sys.path.insert(0, _real)

import approval  # noqa: E402
import question_bank  # noqa: E402
import tracker  # noqa: E402
from jobws_mcp import tools_readonly, tools_writable  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_token_store(tmp_path, monkeypatch):
    """令牌目录挪进 tmp_path——不碰真实临时目录，用例之间互不相见。"""
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval, "_store_dir", lambda: str(store))


def _make_ws(tmp_path):
    ws = tmp_path / "personal"
    os.makedirs(os.path.join(str(ws), "05_投递追踪"))
    return str(ws)


def _write_csv(path, fields, rows):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _seed_question(workspace, qid="Q001", title="什么是索引", domain="技术面"):
    row = {field: "" for field in question_bank.QUESTION_FIELDS}
    row.update({"题目id": qid, "题目": title, "领域": domain, "状态": "未看"})
    _write_csv(question_bank.question_path(workspace),
               question_bank.QUESTION_FIELDS, [row])
    return row


def _seed_interview(workspace, iid="I001", result="通过"):
    row = {field: "" for field in tracker.INTERVIEW_FIELDS}
    row.update({"面试id": iid, "公司": "云帆", "岗位": "后端", "轮次": "一面",
                "结果": result})
    _write_csv(tracker.interview_path(workspace), tracker.INTERVIEW_FIELDS, [row])


# --- 只读：题库 ----------------------------------------------------------------


def test_list_questions_with_rows(tmp_path):
    """有数据时必须返回条目——此前一个变量名笔误让本路径直接 NameError。"""
    ws = _make_ws(tmp_path)
    _seed_question(ws)
    data = tools_readonly.list_questions(ws)
    assert data["total"] == 1 and data["returned"] == 1
    assert data["items"][0]["题目"] == "什么是索引"
    assert data["items"][0]["领域"] == "技术面"


def test_list_questions_default_fields_are_trimmed(tmp_path):
    ws = _make_ws(tmp_path)
    _seed_question(ws)
    data = tools_readonly.list_questions(ws)
    assert "题目" in data["items"][0]
    assert "答案要点" not in data["items"][0], "默认视图应为精简字段"


def test_list_questions_verbose_keeps_all_fields(tmp_path):
    ws = _make_ws(tmp_path)
    _seed_question(ws)
    data = tools_readonly.list_questions(ws, verbose=True)
    assert "答案要点" in data["items"][0]


def test_list_questions_domain_filter(tmp_path):
    ws = _make_ws(tmp_path)
    _seed_question(ws, qid="Q001", domain="技术面")
    _seed_question(ws, qid="Q002", title="行为面问题", domain="行为面")
    data = tools_readonly.list_questions(ws, domain="行为面")
    assert data["total"] == 1
    assert data["items"][0]["题目id"] == "Q002"


# --- 只读：面试 ----------------------------------------------------------------


def test_list_interviews_with_rows(tmp_path):
    ws = _make_ws(tmp_path)
    _seed_interview(ws)
    data = tools_readonly.list_interviews(ws)
    assert data["total"] == 1
    assert data["items"][0]["面试id"] == "I001"
    assert data["items"][0]["公司"] == "云帆"


def test_list_interviews_result_filter(tmp_path):
    """按结果筛：只返回匹配的；不传 result 不过滤（与 CLI 修复后的口径一致）。"""
    ws = _make_ws(tmp_path)
    rows = []
    for iid, result in (("I001", "通过"), ("I002", "待定")):
        row = {field: "" for field in tracker.INTERVIEW_FIELDS}
        row.update({"面试id": iid, "公司": "云帆", "岗位": "后端",
                    "轮次": "一面", "结果": result})
        rows.append(row)
    _write_csv(tracker.interview_path(ws), tracker.INTERVIEW_FIELDS, rows)
    assert tools_readonly.list_interviews(ws)["total"] == 2
    passed = tools_readonly.list_interviews(ws, result="通过")
    assert passed["total"] == 1
    assert passed["items"][0]["面试id"] == "I001"


# --- 只读：JD 评分与越界 --------------------------------------------------------


def test_score_jd_without_card(tmp_path):
    """没解析卡的岗位也要给出诚实回答（评分 None、有解析卡 False），而不是报错。"""
    ws = _make_ws(tmp_path)
    os.makedirs(os.path.join(ws, "01_岗位池", "云帆_后端"))
    data = tools_readonly.score_jd(ws, "云帆_后端")
    assert data["ok"] is True
    assert data["公司"] == "云帆" and data["岗位"] == "后端"
    assert data["评分"] is None and data["有解析卡"] is False


def test_score_jd_rejects_escape_attempts(tmp_path):
    ws = _make_ws(tmp_path)
    os.makedirs(os.path.join(ws, "01_岗位池", "云帆_后端"))
    for bad in ("../05_投递追踪", "C:foo", os.path.join("a", "b"), ""):
        data = tools_readonly.score_jd(ws, bad)
        assert data["ok"] is False, bad
        assert data["errors"], bad


def test_score_jd_rejects_missing_job(tmp_path):
    ws = _make_ws(tmp_path)
    data = tools_readonly.score_jd(ws, "不存在_岗位")
    assert data["ok"] is False
    assert "不存在" in data["errors"][0]


# --- 写入：题库两段式（不落盘）--------------------------------------------------


def test_preview_add_question_returns_token_without_writing(tmp_path):
    ws = _make_ws(tmp_path)
    data = tools_writable.preview_add_question(
        ws, 题目="什么是索引", 领域="技术面", 答案要点="B+ 树、回表、覆盖索引")
    assert data["ok"] is True, data
    assert data["token"] and data["diff"] and data["expires_at"]
    assert not os.path.isfile(question_bank.question_path(ws)), "预览阶段不许落盘"


def test_preview_add_question_rejects_missing_title(tmp_path):
    ws = _make_ws(tmp_path)
    data = tools_writable.preview_add_question(ws, 领域="技术面")
    assert data["ok"] is False
    assert data["errors"]
    assert not os.path.isfile(question_bank.question_path(ws))
