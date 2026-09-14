# -*- coding: utf-8 -*-
"""写入工具的两段式回归：预览不落盘、令牌才落盘、跨工作区被拒。

思路与 `test_tools.py` 一致——数据真落盘、断言真字节（这些工具的全部价值在于
与 CLI/Web 同源，mock 掉调用等于什么都没测）。额外做的一件事是把**令牌目录**
也挪进 tmp：否则用例会写进真实临时目录，彼此之间互相看见。
"""

import io
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import tools_writable  # noqa: E402
import approval  # noqa: E402
import tracker  # noqa: E402  （tools/ 已由 paths.py 加进 sys.path）


@pytest.fixture(autouse=True)
def _isolated_token_store(tmp_path, monkeypatch):
    store = tmp_path / "tokens"
    store.mkdir()
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
