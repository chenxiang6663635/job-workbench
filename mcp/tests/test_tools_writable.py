# -*- coding: utf-8 -*-
"""写入工具的两段式回归：预览不落盘、令牌才落盘、跨工作区被拒。

思路与 `test_tools.py` 一致——数据真落盘、断言真字节（这些工具的全部价值在于
与 CLI/Web 同源，mock 掉调用等于什么都没测）。额外做的一件事是把**令牌目录**
也挪进 tmp：否则用例会写进真实临时目录，彼此之间互相看见。
"""

import csv
import io
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import tools_writable  # noqa: E402
from jobws_core import approval  # noqa: E402
from jobws_core import question_bank  # noqa: E402
from jobws_core import tracker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_token_store(tmp_path, monkeypatch):
    store = tmp_path / "tokens"
    store.mkdir()
    # 这里的 `approval` 是**包内**模块（PR-B 起 MCP 不再走仓内转发层），直接打它。
    monkeypatch.setattr(approval, "_store_dir", lambda: str(store))


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    """一个落在允许根之内的工作区（JOBWS_DATA_DIR 指向 tmp）。"""
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    target = os.path.join(str(tmp_path), "personal")
    os.makedirs(os.path.join(target, "05_投递追踪"))
    with io.open(os.path.join(target, "05_投递追踪", "tracker.csv"), "w",
                 encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(tracker.FIELDS) + "\n")
    return target


def _csv_bytes(ws):
    with open(os.path.join(ws, "05_投递追踪", "tracker.csv"), "rb") as handle:
        return handle.read()


def test_preview_add_then_apply(ws):
    """三步：预览（字节不变）→ 展示 → apply 落盘。"""
    before = _csv_bytes(ws)

    data = tools_writable.preview_add_application(ws, **{
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"})

    assert data["ok"] is True, data
    assert data["token"] and data["diff"]
    assert _csv_bytes(ws) == before, "预览阶段不许动工作区"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    assert applied["id"] == "A001"
    assert "示例公司甲" in _csv_bytes(ws).decode("utf-8-sig")


def test_preview_add_reports_validation_errors_without_token(ws):
    data = tools_writable.preview_add_application(ws, **{
        "公司": "", "岗位": "示例岗位乙", "方向": "backend", "批次": "正式批"})

    assert data["ok"] is False
    assert "token" not in data
    assert any("--company" in problem for problem in data["errors"])


def test_token_is_single_use_across_host_calls(ws):
    """同一令牌调两次：第二次是可读的拒绝，不是异常。"""
    data = tools_writable.preview_add_application(ws, **{
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"})

    assert tools_writable.apply_approval(ws, data["token"])["ok"] is True
    replay = tools_writable.apply_approval(ws, data["token"])

    assert replay["ok"] is False
    assert any("找不到这个令牌" in problem for problem in replay["errors"])


def test_apply_rejects_token_from_another_workspace(ws, tmp_path):
    """令牌绑定工作区：换一个工作区调 apply 必须被拒。"""
    data = tools_writable.preview_add_application(ws, **{
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"})

    other = os.path.join(str(tmp_path), "other")
    os.makedirs(os.path.join(other, "05_投递追踪"))
    with io.open(os.path.join(other, "05_投递追踪", "tracker.csv"), "w",
                 encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(tracker.FIELDS) + "\n")

    result = tools_writable.apply_approval(other, data["token"])

    assert result["ok"] is False
    assert any("绑定" in problem for problem in result["errors"])


def test_preview_import_then_apply(ws):
    csv_text = ("公司,岗位,方向,批次,当前阶段\n"
                "示例公司甲,示例岗位乙,backend,正式批,待投\n")
    before = _csv_bytes(ws)

    data = tools_writable.preview_import_applications(ws, csv_text)

    assert data["ok"] is True, data
    assert _csv_bytes(ws) == before, "预览阶段不许动工作区"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    assert applied["written"] == 1


def test_preview_import_with_error_rows_gives_no_token(ws):
    csv_text = ("公司,岗位,方向,批次,当前阶段\n"
                ",示例岗位乙,backend,正式批,待投\n")   # 公司为空 → 错误行

    data = tools_writable.preview_import_applications(ws, csv_text)

    assert data["ok"] is False
    assert "token" not in data
    assert data["error_rows"]


def test_apply_reports_conflict_as_readable_error(ws):
    """预览之后数据变了：apply_approval 返回 ok=False 与冲突理由，不是抛栈。

    宿主拿到的是可读的拒绝理由（ApprovalConflict 是 ApprovalError 子类，
    在这一层被捕获），所以模型能自己决定"重新预览"而不是崩掉。
    """
    data = tools_writable.preview_add_application(ws, **{
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"})

    tracker.apply_approved_add({"fields": {
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"}}, ws)   # 模拟"别处先写了一条"

    result = tools_writable.apply_approval(ws, data["token"])

    assert result["ok"] is False
    assert any("已存在相同公司+岗位" in problem for problem in result["errors"])


def test_import_preview_reuses_plan_import(ws, monkeypatch):
    """diff / 载荷的构造必须来自 `tracker.plan_import`（单一事实源）。

    CLI / 网页端 / 本工具三处各拼一份 diff 的话，表头或列一改就漂移——独立
    审查 M2 抓到的正是本函数曾手搓第二份。这里用「标记注入」证明复用：
    plan_import 的输出带上标记，工具返回的 diff / summary 必须跟着带
    （若哪天回退成手搓，标记消失，这条即红）。
    """
    real_plan = tracker.plan_import

    def marked(preview, workspace=None):
        plan = real_plan(preview, workspace)
        plan["diff"] = plan["diff"] + ["| 标记 |"]
        plan["summary"] = "标记：" + plan["summary"]
        return plan

    monkeypatch.setattr(tracker, "plan_import", marked)

    csv_text = ("公司,岗位,方向,批次,当前阶段\n"
                "示例公司甲,示例岗位乙,backend,正式批,待投\n")
    data = tools_writable.preview_import_applications(ws, csv_text)

    assert data["ok"] is True, data
    assert data["diff"][-1] == "| 标记 |", "diff 必须经由 tracker.plan_import 构造"
    assert data["summary"].startswith("标记：")


# --- 题库导入（question.import）：两段式行为（T 批补网）-------------------------


def _write_card(ws, rel, text):
    """在工作区内写一张训练卡（03_面试准备 下的任意层级 .md）。"""
    path = os.path.join(ws, "03_面试准备", rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def test_preview_import_questions_then_apply(ws):
    _write_card(ws, "技术面/tcp.md", "# TCP\n\n三次握手要点。\n")
    _write_card(ws, "行为面/冲突问题.md", "# 冲突问题\n\n先对齐目标。\n")
    q_path = question_bank.question_path(ws)

    data = tools_writable.preview_import_questions(ws)

    assert data["ok"] is True, data
    assert data["token"] and data["diff"]
    assert not os.path.isfile(q_path), "预览阶段不许落盘"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    assert applied["written"] == 2
    rows = question_bank.read_questions(ws)
    assert sorted(r["题目"] for r in rows) == ["TCP", "冲突问题"]
    assert all(r["来源"] == "导入" for r in rows)


def test_preview_import_questions_rejects_escape_attempts(ws):
    """module_dir 只收工作区内相对目录：绝对路径与 .. 都在工具层先拒。"""
    for bad in (os.path.abspath(os.sep), "../03_面试准备"):
        data = tools_writable.preview_import_questions(ws, bad)
        assert data["ok"] is False, bad
        assert data["errors"], bad
    assert not os.path.isfile(question_bank.question_path(ws))


def test_preview_import_questions_nothing_new_is_readable_error(ws):
    """全部已入题库：返回可读错误（ok=False），不是异常也不是空令牌。"""
    _write_card(ws, "技术面/tcp.md", "# TCP\n\n要点。\n")
    first = tools_writable.preview_import_questions(ws)
    assert tools_writable.apply_approval(ws, first["token"])["ok"] is True

    again = tools_writable.preview_import_questions(ws)

    assert again["ok"] is False
    assert "token" not in again
    assert any("都已入题库" in problem for problem in again["errors"])


# --- 面试更新（interview.update）：两段式行为（T 批补网）-----------------------


def _seed_interview(ws, iid="I001", result="通过"):
    row = {field: "" for field in tracker.INTERVIEW_FIELDS}
    row.update({"面试id": iid, "公司": "云帆", "岗位": "后端", "轮次": "一面",
                "结果": result})
    with io.open(tracker.interview_path(ws), "w", encoding="utf-8-sig",
                 newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.INTERVIEW_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def test_preview_update_interview_then_apply(ws):
    _seed_interview(ws)
    path = tracker.interview_path(ws)
    with io.open(path, "rb") as handle:
        before = handle.read()

    data = tools_writable.preview_update_interview(ws, "I001", {"结果": "未通过"})

    assert data["ok"] is True, data
    assert data["token"] and data["diff"]
    with io.open(path, "rb") as handle:
        assert handle.read() == before, "预览阶段不许落盘"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    rows = tracker.read_interviews(ws)
    assert rows[0]["结果"] == "未通过"


def test_preview_update_interview_missing_id_is_readable_error(ws):
    _seed_interview(ws)
    data = tools_writable.preview_update_interview(ws, "I999", {"结果": "未通过"})
    assert data["ok"] is False
    assert any("找不到面试" in problem for problem in data["errors"])


def test_preview_update_interview_no_effective_change(ws):
    """changes 与现值相同（或全是不可更新字段）：可读错误，不发令牌。"""
    _seed_interview(ws)
    data = tools_writable.preview_update_interview(ws, "I001", {"结果": "通过"})
    assert data["ok"] is False
    assert "token" not in data
    assert any("没有字段变化" in problem for problem in data["errors"])


# --- 面试新增（interview.add）：两段式行为（T 批补网）---------------------------


def test_preview_add_interview_then_apply(ws):
    path = tracker.interview_path(ws)

    data = tools_writable.preview_add_interview(ws, **{
        "公司": "云帆", "岗位": "后端", "轮次": "一面", "结果": "待定"})

    assert data["ok"] is True, data
    assert data["token"] and data["diff"]
    assert not os.path.isfile(path), "预览阶段不许落盘"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    assert applied["id"] == "I001"
    rows = tracker.read_interviews(ws)
    assert rows[0]["公司"] == "云帆" and rows[0]["轮次"] == "一面"


def test_preview_add_interview_with_link_carries_company_and_history(ws):
    """关联记录版：公司/岗位从主表带出；落盘入账时间线（与 CLI 同款）。"""
    tracker.apply_approved_add({"fields": {
        "公司": "云帆", "岗位": "后端", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"}}, ws)

    data = tools_writable.preview_add_interview(ws, **{"关联记录": "A001"})

    assert data["ok"] is True, data
    assert "云帆" in "\n".join(data["diff"]), "公司应从主表带出"

    applied = tools_writable.apply_approval(ws, data["token"])

    assert applied["ok"] is True
    history = tracker.read_history(ws)
    assert any(r["字段"] == "面试" for r in history)


def test_preview_add_interview_rejects_bad_enum_and_unknown_link(ws):
    bad_enum = tools_writable.preview_add_interview(ws, **{
        "公司": "云帆", "岗位": "后端", "结果": "元宇宙"})
    assert bad_enum["ok"] is False
    assert any("结果必须是" in problem for problem in bad_enum["errors"])

    unknown_link = tools_writable.preview_add_interview(ws, **{"关联记录": "A999"})
    assert unknown_link["ok"] is False
    assert any("找不到关联记录" in problem for problem in unknown_link["errors"])
