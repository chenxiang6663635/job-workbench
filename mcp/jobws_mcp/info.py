# -*- coding: utf-8 -*-
"""`jobws.info` 工具（A2）：版本、当前工作区与数据根诊断——**只读、无副作用**。

为什么单独一个模块：`server.py` 与 `tools_readonly.py` 都贴着规模水位线
（只许变小），新工具的实现与注册整体落在这里，`server.py` 只留一行接入。
呈现分工（spec §五）：本工具不自己算状态——`jobws_core.dataroot.describe()`
是四端共享的唯一事实源；这里只做「取版本 + 序列化」。

盲区（spec §三决策 3，必须可见）：MCP 只看得到 env 与系统用户目录两个候选，
看不到源码形态的应用根——「本工具报 state=ok」**不等于**全机没有多个数据根。

instructions 提示：不把本机路径塞进宿主系统提示词（spec §五）——歧义时只在
服务 instructions 里附一行**不带路径**的提示，详情走本工具的结构化输出。
"""

import json
import os

from jobws_core import __version__ as _core_version
from jobws_core import dataroot


def server_version():
    """`jobws-mcp` 包版本；未安装（源码直跑）时回落 "0"，不抛。"""
    from importlib.metadata import PackageNotFoundError, version

    for name in ("jobws-mcp", "jobws_mcp"):
        try:
            return version(name)
        except PackageNotFoundError:
            continue
    return "0"


def _describe(workspace):
    """工作区对应的数据根诊断（mcp_only 形态；工作区名进 uninitialized 判定）。"""
    ws_name = os.path.basename(os.path.normpath(workspace)) or "personal"
    return dataroot.describe(dataroot.FORM_MCP_ONLY, None, workspace_name=ws_name)


def payload(workspace):
    """`jobws.info` 的返回体（dict；字符串序列化交给 server.py 的注册块）。"""
    return {
        "serverVersion": server_version(),
        "coreVersion": _core_version,
        "workspace": workspace,
        "dataRoot": _describe(workspace),
    }


def ambiguous_hint(workspace):
    """歧义时的一行提示（不带本机路径）；无歧义返回空串。

    `describe` 会扫已知候选（单层、条目数有界）——只在本服务**启动时**算一次
    （server.py 拼 instructions 用），不在每次调用上重复。
    """
    if _describe(workspace)["state"] == dataroot.STATE_AMBIGUOUS:
        return ("提示：本机可能存在多个数据根（MCP 只看得到其中两个候选）——"
                "用 jobws.info 查看 state 与候选清单。")
    return ""


def register(mcp, workspace):
    """在 MCP server 上注册 `jobws.info`（**追加在工具注册末尾**——顺序稳定）。

    `annotations` 懒导入（D1）：本模块的 `payload()` / `ambiguous_hint()` 是纯
    函数、**不依赖 MCP SDK**（`test_info.py` 的字段断言据此脱 SDK 跑）；只有
    `register()` 本身在 SDK 环境里被调用。
    """
    from . import annotations

    @mcp.tool(name="jobws.info", annotations=annotations.READ_ONLY)
    def jobws_info() -> str:
        """本机安装与数据根的诊断信息（只读，无副作用）。

        返回 jobws-mcp 与 jobws-core 的版本、当前工作区，以及数据根诊断对象
        （state / source / form / writable / 候选根 / 持久化选择）。数据「看起来
        不对」或怀疑读的不是同一份数据时，先调它确认产品实际在用哪个根。
        """
        return json.dumps(payload(workspace), ensure_ascii=False, indent=2)
