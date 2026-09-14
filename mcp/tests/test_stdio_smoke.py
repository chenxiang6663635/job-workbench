# -*- coding: utf-8 -*-
"""stdio 冒烟：真起一个子进程，用官方 client 走完握手 → 列出工具 → 调一次。

只在装了 MCP SDK 的环境运行（需要 Python 3.10+）：CI 由独立的 3.12 job 跑，
主干 3.8 的 pytest 会因为 `importorskip` 自动跳过而不是报错。

为什么必须真起进程：工具的实现细节（`tools_readonly`）已有单测覆盖，
这里要钉的是**另一件事**——stdio 通道干净（没有多余输出污染协议）、
工具能被宿主发现并调用。这类缺陷只在真连一次时才暴露。
"""

import io
import json
import os
import sys

import pytest

pytest.importorskip("mcp", reason="MCP SDK 需要 Python 3.10+；本用例由 CI 的 3.12 job 执行")

import anyio  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed(ws):
    """最小工作区：一条投递记录即可（只验证通道与调用，不做口径断言）。"""
    d = os.path.join(ws, "05_投递追踪")
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(os.path.join(d, "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("id,公司,岗位,当前阶段\n1,示例科技,后端开发工程师,一面\n")


@pytest.mark.anyio
async def test_stdio_lists_and_calls_tools(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    ws = os.path.join(str(tmp_path), "personal")
    os.makedirs(os.path.join(ws, "config"))
    _seed(ws)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jobws_mcp.server", "--workspace", ws],
        env=dict(os.environ, PYTHONPATH=MCP_DIR, JOBWS_DATA_DIR=str(tmp_path)),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            assert names == ["dashboard_summary", "list_applications", "list_jobs"]

            result = await session.call_tool("dashboard_summary", {})
            text = result.content[0].text
            assert json.loads(text)["total"] == 1
