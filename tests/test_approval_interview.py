# -*- coding: utf-8 -*-
"""面试两段式（批 4.7）：预览不落盘 → 令牌 → 落盘，附四类拒绝与冲突路径。

为什么单独一个文件：面试原先只有 CLI 直写路径，本批才补上「预览 → 确认 → 落盘」。
这些用例同时是**口径对齐检查**——校验口径必须与 `_cli_interview.py` 一致
（同一组枚举、同一条外键规则）；谁改坏了枚举或外键，先在这里红。
"""
from __future__ import annotations

import argparse
import io
import os
import sys

import pytest

# 自插 sys.path：单独跑本文件（pytest 直接收一个文件）也要能过
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("tools", "web/backend"):
    _p = os.path.join(ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import approval  # noqa: E402
import tracker  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """令牌目录隔离：不污染系统临时目录里真实的 jobws-approvals。"""
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    monkeypatch.setattr(approval._shell, "_store_dir", lambda: str(tokens))
    return tokens


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    workspace = tmp_path / "personal"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text(
        ",".join(tracker.FIELDS) + "\n", encoding="utf-8-sig")
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    return str(workspace)


def _seed_application(workspace, app_id="A001"):
    """主表里放一条记录，供面试关联（外键校验要用）。"""
    record = {field: "" for field in tracker.FIELDS}
    record.update({"id": app_id, "公司": "云帆", "岗位": "后端",
                   "方向": "backend", "批次": "正式批", "当前阶段": "待投"})
    tracker.write_rows([record], workspace)
    return app_id


def _interview_path(workspace):
    return os.path.join(workspace, "05_投递追踪", tracker.INTERVIEW_FILE)


def _snapshot(workspace):
    """`05_投递追踪` 目录快照（相对路径 → 字节）——预览阶段必须一个不差。"""
    tracking = os.path.join(workspace, "05_投递追踪")
    snap = {}
    for name in sorted(os.listdir(tracking)):
        full = os.path.join(tracking, name)
        if os.path.isfile(full):
            with io.open(full, "rb") as handle:
                snap[name] = handle.read()
    return snap


def _preview_add(workspace, fields, ttl=approval.DEFAULT_TTL_SECONDS):
    errors, plan = tracker.preview_interview_add_fields(fields, workspace)
    assert not errors, errors
    return approval.preview("interview.add", workspace, plan["payload"],
                            plan["summary"], plan["diff"], plan["targets"], ttl=ttl)


# --- 新增：预览与落盘 --------------------------------------------------------


def test_add_preview_does_not_write(store, ws):
    """预览阶段连一个字节都不该动（"不落盘"不是打印一句就算了）。"""
    _seed_application(ws)
    before = _snapshot(ws)
    data = _preview_add(ws, {"关联记录": "A001", "轮次": "一面"})
    assert data["token"]
    assert _snapshot(ws) == before


def test_add_apply_writes_row_and_history(store, ws):
    """落盘：interviews.csv 多一行、时间线入账；公司/岗位从关联记录带出。"""
    _seed_application(ws)
    data = _preview_add(ws, {"关联记录": "A001", "轮次": "二面",
                             "面试时间": "2026-09-20 14:00", "形式": "视频"})
    result = approval.apply(data["token"], workspace=ws)
    assert result.get("written") == 1
    assert result.get("id") == "I001"

    rows = tracker.read_interviews(ws)
    assert len(rows) == 1
    assert rows[0]["面试id"] == "I001"
    assert rows[0]["公司"] == "云帆" and rows[0]["岗位"] == "后端"
    assert rows[0]["轮次"] == "二面" and rows[0]["结果"] == "待定"

    history = tracker.read_history(ws)
    assert any(item.get("字段") == "面试" for item in history), history


def test_add_requires_company_without_link(store, ws):
    """未关联记录时必须给公司——就地拒绝，且不发放令牌。"""
    errors, plan = tracker.preview_interview_add_fields({"轮次": "一面"}, ws)
    assert plan is None
    assert any("公司" in item for item in errors)


def test_add_rejects_unknown_link(store, ws):
    _seed_application(ws)
    errors, plan = tracker.preview_interview_add_fields(
        {"关联记录": "A999", "轮次": "一面"}, ws)
    assert plan is None
    assert any("A999" in item for item in errors)


def test_add_rejects_bad_enums(store, ws):
    _seed_application(ws)
    errors, plan = tracker.preview_interview_add_fields(
        {"关联记录": "A001", "轮次": "四面", "形式": "脑机接口"}, ws)
    assert plan is None
    assert any("轮次" in item for item in errors)
    assert any("形式" in item for item in errors)


def test_add_expired_token(store, ws):
    _seed_application(ws)
    data = _preview_add(ws, {"关联记录": "A001", "轮次": "一面"}, ttl=-1)
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"])
    assert excinfo.value.code == "expired"
    assert not os.path.isfile(_interview_path(ws))


def test_add_replayed_token(store, ws):
    """重放：令牌取走即焚，第二次拿到的就是 not_found，且只落盘一次。"""
    _seed_application(ws)
    data = _preview_add(ws, {"关联记录": "A001", "轮次": "一面"})
    approval.apply(data["token"], workspace=ws)
    before = _snapshot(ws)
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"], workspace=ws)
    assert excinfo.value.code == "not_found"
    assert _snapshot(ws) == before


def test_add_conflict_when_link_disappeared(store, ws):
    """预览之后关联记录没了：apply 重校验必须拒绝（而不是照旧写下去）。"""
    _seed_application(ws)
    data = _preview_add(ws, {"关联记录": "A001", "轮次": "一面"})
    tracker.write_rows([], ws)  # 主表被清空
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"], workspace=ws)
    assert excinfo.value.code == "conflict"


# --- 更新 --------------------------------------------------------------------


def _seed_interview(workspace):
    data = _preview_add(workspace, {"关联记录": "A001", "轮次": "一面"})
    approval.apply(data["token"], workspace=workspace)
    return "I001"


def _preview_update(workspace, interview_id, changes, ttl=approval.DEFAULT_TTL_SECONDS):
    errors, plan = tracker.preview_interview_update_fields(
        {"id": interview_id, "changes": changes}, workspace)
    assert not errors, errors
    return approval.preview("interview.update", workspace, plan["payload"],
                            plan["summary"], plan["diff"], plan["targets"], ttl=ttl)


def test_update_preview_and_apply(store, ws):
    _seed_application(ws)
    interview_id = _seed_interview(ws)
    before = _snapshot(ws)

    data = _preview_update(ws, interview_id, {"结果": "通过",
                                             "我的回答要点": "先讲项目再讲取舍"})
    assert _snapshot(ws) == before  # 预览不落盘

    result = approval.apply(data["token"], workspace=ws)
    assert result.get("written") == 1
    row = tracker.read_interviews(ws)[0]
    assert row["结果"] == "通过"
    assert row["我的回答要点"] == "先讲项目再讲取舍"


def test_update_without_change_is_rejected(store, ws):
    """没有实际变化 → 预览阶段就拒绝，不发令牌（与 CLI「未写入」同语义）。"""
    _seed_application(ws)
    interview_id = _seed_interview(ws)
    errors, plan = tracker.preview_interview_update_fields(
        {"id": interview_id, "changes": {"结果": "待定"}}, ws)
    assert plan is None
    assert any("没有字段变化" in item for item in errors)


def test_update_unknown_id(store, ws):
    _seed_application(ws)
    errors, plan = tracker.preview_interview_update_fields(
        {"id": "I999", "changes": {"结果": "通过"}}, ws)
    assert plan is None
    assert any("I999" in item for item in errors)


def test_update_ignores_non_updatable_fields(store, ws):
    """面试 id / 关联记录 / 公司 不在可更新集合里——传了也不改（防接错时间线）。"""
    _seed_application(ws)
    interview_id = _seed_interview(ws)
    errors, plan = tracker.preview_interview_update_fields(
        {"id": interview_id,
         "changes": {"公司": "别家公司", "结果": "通过"}}, ws)
    assert not errors, errors
    assert "公司" not in plan["payload"]["changes"]
    assert plan["payload"]["changes"] == {"结果": "通过"}


# --- CLI 分支（`track interview add|update --preview`）-------------------------
#
# 为什么必须有这几条：领域层全绿 ≠ 命令行走得通。本批首次实现 `--preview` 时，
# `_cli_interview.py` 漏了 `_core` 的导入，735 项既有测试全绿却照样 NameError——
# 因为没有任何用例真的走命令行分支（独立审查前的实测踩到）。


def _interview_args(**overrides):
    """按 `_add_interview_parser` 的参数表构造 Namespace（少一个属性就 AttributeError）。"""
    base = dict(
        action="add", app="A001", company=None, role=None, round="一面",
        when=None, form=None, link=None, interviewer=None, questions=None,
        answers=None, retro=None, result="待定", preview=False, id=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cli_add_preview_registers_token_only(store, ws, monkeypatch):
    _seed_application(ws)
    monkeypatch.setenv("JOBWS_DATA_DIR", os.path.dirname(ws))
    monkeypatch.setattr(tracker._core, "WORKSPACE", ws)
    before = _snapshot(ws)
    code = tracker.cmd_interview(_interview_args(preview=True))
    assert code == 0
    assert _snapshot(ws) == before, "预览阶段不该动工作区任何字节"
    assert not os.path.isfile(_interview_path(ws))


def test_cli_add_writes_without_preview(store, ws, monkeypatch):
    """不带 --preview 时保持默认行为：直接落盘（与改动前一致）。"""
    _seed_application(ws)
    monkeypatch.setenv("JOBWS_DATA_DIR", os.path.dirname(ws))
    monkeypatch.setattr(tracker._core, "WORKSPACE", ws)
    code = tracker.cmd_interview(_interview_args(preview=False))
    assert code == 0
    rows = tracker.read_interviews(ws)
    assert [row["面试id"] for row in rows] == ["I001"]
    assert rows[0]["公司"] == "云帆"


def test_cli_add_reports_validation_errors(store, ws, monkeypatch):
    """外键不存在：命令行必须给出**退出码 1**，而不是抛栈。"""
    _seed_application(ws)
    monkeypatch.setenv("JOBWS_DATA_DIR", os.path.dirname(ws))
    monkeypatch.setattr(tracker._core, "WORKSPACE", ws)
    code = tracker.cmd_interview(_interview_args(app="A999"))
    assert code == 1
    assert not os.path.isfile(_interview_path(ws))
