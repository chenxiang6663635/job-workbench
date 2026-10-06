# -*- coding: utf-8 -*-
"""工具调用的数据根守卫（B4 整改 B）：持久化选择失效时 fail-closed。

背景（cross_end_audit 缺陷 B）：MCP 此前只在**启动**时解析工作区；运行中数据根
失效（选择文件被改坏 / 根被删）后，工具仍沿启动时路径读写、写路径还会
makedirs 重建目录——而 API（`deps._require_usable_data_root`，每请求一次）与
CLI（`jobws.py` 命令组守卫）都会拒绝。本中间件补上 MCP 侧的同源闸。

实现走**官方拦截点**：`MCPServer(middleware=[...])`（`ServerMiddleware`，
`(ctx, call_next)`，在参数校验前包裹每条入站消息）——单一具位点，不需要在
15 个工具入口各加一行。

细节：
- 判据与 API 同源：`dataroot.persisted_unavailable()`（O(1)：一个文件读取 +
  一次 stat；**不做候选扫描**——那是诊断面的事）。
- **豁免 `jobws.info`**：诊断与补救必须在失效态可用（spec 决策 4——否则用户
  在失效态被锁死，连诊断都调不到）。
- 拒绝形态沿用工具层纪律（**不抛栈**）：返回 `CallToolResult` 形状的
  `ok:false` 文本 + `isError`，宿主按普通工具失败展示可读理由。
- 只拦 `tools/call`：resources / prompts 的读由工作区路径自然失败接管，
  不在本闸语义内（它们不是「写」，也不构成静默回落）。
"""

import json

from jobws_core import dataroot
from mcp_types import CallToolResult, TextContent

#: 稳定错误标识（与 API 的 `sys.dataRootUnavailable` 同值——宿主按 code 分支）
REFUSAL_CODE = "sys.dataRootUnavailable"

#: 诊断豁免：失效态最需要它（决策 4 的补救通道）
EXEMPT_TOOL = "jobws.info"


def refusal_text():
    """拒绝载荷（JSON 文本；`ok:false` + 稳定 code + 可读修复指引）。"""
    return json.dumps({
        "ok": False,
        "code": REFUSAL_CODE,
        "errors": ["数据根不可用：持久化选择指向的位置不存在或不可写——"
                   "读写已拒绝（fail-closed，禁止静默回落到其它根）。"
                   "请修复该路径或清除持久化选择后重试；"
                   "`jobws doctor` 或 jobws.info 可查看详情。"],
    }, ensure_ascii=False, indent=2)


class DataRootGuard:
    """`MCPServer(middleware=[DataRootGuard()])`：tools/call 前查一次数据根。"""

    async def __call__(self, ctx, call_next):
        if ctx.method == "tools/call" and not self._allow(ctx):
            return CallToolResult(
                content=[TextContent(type="text", text=refusal_text())],
                is_error=True,
            )
        return await call_next(ctx)

    @staticmethod
    def _allow(ctx):
        """放行判据：非 tools/call、豁免工具、或数据根可用。"""
        params = ctx.params if isinstance(ctx.params, dict) else {}
        if params.get("name") == EXEMPT_TOOL:
            return True
        return not dataroot.persisted_unavailable()
