# -*- coding: utf-8 -*-
"""数据根守卫（B4 整改 B）的单元网：放行 / 拒绝语义不依赖真通道。

真通道行为（stdio + SDK middleware 接线）由 `test_stdio_smoke.py` 覆盖；
本文件钉语义：非 tools/call 放行、jobws.info 豁免、unavailable 时其余
tools/call 拒（返回 `ok:false` + 稳定 code 的 CallToolResult）。
"""

import asyncio
import json
import types

from jobws_mcp import guard


def _ctx(method, name=None):
    params = {"name": name, "arguments": {}} if name else {}
    return types.SimpleNamespace(method=method, params=params)


def _run(ctx):
    calls = []

    async def call_next(c):
        calls.append(c)
        return "NEXT"

    async def main():
        return await guard.DataRootGuard()(ctx, call_next)

    return asyncio.run(main()), calls


def test_passes_when_data_root_ok(monkeypatch):
    monkeypatch.setattr(guard.dataroot, "persisted_unavailable", lambda: False)
    result, calls = _run(_ctx("tools/call", "dashboard_summary"))
    assert result == "NEXT"
    assert calls, "数据根可用时必须放行到 call_next"


def test_refuses_when_unavailable(monkeypatch):
    monkeypatch.setattr(guard.dataroot, "persisted_unavailable", lambda: True)
    result, calls = _run(_ctx("tools/call", "dashboard_summary"))
    assert calls == [], "unavailable 时不得触达真实处理链"
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["code"] == guard.REFUSAL_CODE
    assert result.is_error is True


def test_info_is_exempt(monkeypatch):
    """诊断工具豁免（spec 决策 4：失效态仍要能调它定位问题）。"""
    monkeypatch.setattr(guard.dataroot, "persisted_unavailable", lambda: True)
    result, calls = _run(_ctx("tools/call", "jobws.info"))
    assert result == "NEXT"
    assert calls


def test_non_tool_methods_pass(monkeypatch):
    """只拦 tools/call：列表 / 握手 / 资源等一律放行。"""
    monkeypatch.setattr(guard.dataroot, "persisted_unavailable", lambda: True)
    result, calls = _run(_ctx("tools/list"))
    assert result == "NEXT"
    assert calls


def test_missing_params_refuses_fail_closed(monkeypatch):
    """params 形状异常（None）判不出工具名 → **fail-closed 拒绝**（不炸）。

    fail-closed 优先：畸形请求无法确认是不是豁免工具，宁可拒（宿主会重试
    正常请求；静默放行则可能绕开失效守卫）。
    """
    monkeypatch.setattr(guard.dataroot, "persisted_unavailable", lambda: True)
    ctx = types.SimpleNamespace(method="tools/call", params=None)
    result, calls = _run(ctx)
    assert calls == []
    payload = json.loads(result.content[0].text)
    assert payload["code"] == guard.REFUSAL_CODE
