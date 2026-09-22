# -*- coding: utf-8 -*-
"""批 8 新增：更新类写工具（preview_update_application）与拒绝码透传。

钉四件事（2026-09-19 补后两类：四类拒绝在**壳层各自都有端到端覆盖**）：
1. 两段式——preview 绝不落盘（字节不变），apply 后才更新字段；
2. 第四类拒绝（输入校验失败）——preview 阶段就地拒绝、不发放令牌；
3. 拒绝时 apply_approval 返回稳定 code（not_found / expired / fingerprint 等）
   ——宿主据此区分四类，不要解析中文文案；
4. 过期与指纹不符也在壳层测过：协议层负责造令牌与判定，壳层负责把
   ApprovalError 转成宿主读得懂的 `{"ok": false, "code": ...}`。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import tools_writable  # noqa: E402

from jobws_core import approval  # noqa: E402
from jobws_core import tracker  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """令牌目录隔离：不污染系统临时目录里真实的 jobws-approvals。"""
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    monkeypatch.setattr(approval, "_store_dir", lambda: str(tokens))
    return tokens


@pytest.fixture()
def ws(tmp_path):
    workspace = tmp_path / "personal"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    with io.open(str(tracking / "tracker.csv"), "w", encoding="utf-8-sig",
                 newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.FIELDS,
                                extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerow({"id": "A001", "公司": "云帆", "岗位": "后端",
                         "方向": "backend", "批次": "正式批", "当前阶段": "待投"})
    return str(workspace)


def _csv_bytes(workspace):
    with open(os.path.join(workspace, "05_投递追踪", "tracker.csv"), "rb") as handle:
        return handle.read()


def _read_stage(workspace):
    with io.open(os.path.join(workspace, "05_投递追踪", "tracker.csv"), "r",
                 encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))[0]["当前阶段"]


def test_preview_does_not_write_then_apply_updates(store, ws):
    before = _csv_bytes(ws)
    data = tools_writable.preview_update_application(
        ws, "A001", {"当前阶段": "一面", "下次动作": "准备一面"})
    assert data["ok"] is True and data["token"]
    assert _csv_bytes(ws) == before, "预览阶段不许落盘"

    applied = tools_writable.apply_approval(ws, data["token"])
    assert applied["ok"] is True
    assert _read_stage(ws) == "一面"


def test_replay_returns_not_found_code(store, ws):
    data = tools_writable.preview_update_application(ws, "A001", {"当前阶段": "一面"})
    assert tools_writable.apply_approval(ws, data["token"])["ok"] is True
    replay = tools_writable.apply_approval(ws, data["token"])
    assert replay["ok"] is False
    assert replay["code"] == "not_found"


def test_input_validation_failure_is_rejected_without_token(store, ws):
    """第四类拒绝：找不到 id / 没有要改的字段——不发令牌、不落盘。"""
    missing = tools_writable.preview_update_application(ws, "A999", {"备注": "x"})
    assert missing["ok"] is False
    assert "token" not in missing


def _raw_token(ws, ttl=None):
    """直接经协议层造令牌：MCP 工具刻意不暴露 ttl（那是协议层内务），
    所以"造一个过期 / 将被篡改的令牌"只能在壳外完成——本文件测的是壳的转译。"""
    kwargs = {} if ttl is None else {"ttl": ttl}
    return approval.preview(
        "track.add", ws,
        {"company": "云帆", "role": "后端", "direction": "backend", "batch": "正式批"},
        summary="新增投递：云帆 后端", diff="+ 云帆 后端",
        targets=["05_投递追踪/tracker.csv"], **kwargs)


def test_expired_token_is_rejected_with_code(store, ws):
    """过期（第三类拒绝之一）：壳层转成可读拒绝 + 稳定 code `expired`。"""
    data = _raw_token(ws, ttl=-1)

    result = tools_writable.apply_approval(ws, data["token"])

    assert result["ok"] is False
    assert result["code"] == "expired"


def test_tampered_payload_is_rejected_with_code(store, ws):
    """指纹不符（第三类拒绝之二）：令牌记录里的载荷被改过 → 拒绝。

    这条防的是"拿到令牌后改载荷再落盘"——载荷指纹在预览时就绑定了，
    改一个字节都会让 apply 拒绝（协议层的 fingerprint 判定，壳层如实转译）。
    """
    data = _raw_token(ws)
    path = next(store.glob("*.json"))
    record = json.loads(io.open(str(path), encoding="utf-8").read())
    record["payload"]["company"] = "篡改过的公司"
    with io.open(str(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))

    result = tools_writable.apply_approval(ws, data["token"])

    assert result["ok"] is False
    assert result["code"] == "fingerprint"

    empty = tools_writable.preview_update_application(ws, "A001", {})
    assert empty["ok"] is False
    assert "token" not in empty
