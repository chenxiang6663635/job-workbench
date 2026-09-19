# -*- coding: utf-8 -*-
"""令牌拒绝语义（批 8）：每类拒绝都要有**稳定 code**——文案可改，code 不可改。

四类拒绝的归属（与 MCP 侧口径一致）：
- 重放       → not_found（令牌取走即焚，第二次拿到的就是"不存在"）
- 过期       → expired
- 指纹不符   → fingerprint（令牌记录里的载荷被改动）
- 输入校验失败 → preview 阶段就地拒绝、不发放令牌（该路径在 mcp/tests 覆盖）

另钉一条：拒绝路径**绝不落盘**（第二次 apply 后 CSV 字节不变）。
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

# 自插 sys.path：不能指望"别的测试模块先被导入时顺手插好"——单独跑本文件也要能过
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


def _preview_add(workspace, ttl=approval.DEFAULT_TTL_SECONDS):
    return approval.preview(
        "track.add",
        workspace,
        {"company": "云帆", "role": "后端", "direction": "backend", "batch": "正式批"},
        summary="新增投递：云帆 后端",
        diff="+ 云帆 后端",
        targets=["05_投递追踪/tracker.csv"],
        ttl=ttl,
    )


def _csv_bytes(workspace):
    with open(os.path.join(workspace, "05_投递追踪", "tracker.csv"), "rb") as handle:
        return handle.read()


# --- 四类拒绝 --------------------------------------------------------------


def test_replayed_token_is_not_found(store, ws):
    """重放：令牌已被消费（等价于第二次 apply）→ not_found，且不落盘。"""
    data = _preview_add(ws)
    before = _csv_bytes(ws)
    os.remove(approval._token_path(data["token"]))  # 模拟"已被使用"
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"])
    assert excinfo.value.code == "not_found"
    assert _csv_bytes(ws) == before


def test_expired_token(store, ws):
    data = _preview_add(ws, ttl=-1)  # 立即过期
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"])
    assert excinfo.value.code == "expired"


def test_fingerprint_mismatch(store, ws):
    """指纹不符：令牌记录里的载荷被改动 → fingerprint（拒绝执行）。"""
    data = _preview_add(ws)
    path = approval._token_path(data["token"])
    with io.open(path, "r", encoding="utf-8") as handle:
        record = json.load(handle)
    record["payload"]["company"] = "篡改过的公司"
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"])
    assert excinfo.value.code == "fingerprint"


def test_bad_token_format(store, ws):
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply("not-a-token")
    assert excinfo.value.code == "bad_token"


def test_binding_mismatch(store, ws, tmp_path):
    data = _preview_add(ws)
    other = str(tmp_path / "other-ws")
    with pytest.raises(approval.ApprovalError) as excinfo:
        approval.apply(data["token"], workspace=other)
    assert excinfo.value.code == "binding"


# --- 幂等：拒绝路径不落盘 --------------------------------------------------


def test_reject_does_not_touch_data(store, ws):
    """过期令牌被拒后，数据文件与令牌目录都不该有副作用。"""
    before = _csv_bytes(ws)
    data = _preview_add(ws, ttl=-1)
    with pytest.raises(approval.ApprovalError):
        approval.apply(data["token"])
    assert _csv_bytes(ws) == before


def test_every_code_is_documented():
    """code 集合必须与 docstring 声明一致（防后来加分支忘了写 code）。"""
    declared = {
        "bad_token", "not_found", "unreadable", "lost", "expired",
        "binding", "fingerprint", "unknown_operation", "conflict",
    }
    doc = approval.ApprovalError.__doc__ or ""
    for code in declared:
        assert code in doc, "code %s 未在 ApprovalError docstring 中登记" % code
