# -*- coding: utf-8 -*-
"""MCP 服务入口：三个只读工具，stdio 传输。

两条写在最前面的纪律：

1. **stdout 是协议通道**——stdio 传输下任何 print 都会变成畸形报文。
   诊断信息一律走 stderr（所以 `main()` 的错误出口是 `sys.stderr.write`）。
2. **工具返回 JSON 文本**而不是 dict：宿主侧拿到的是字符串，结构化输出留到
   SDK 各版本行为稳定之后再说；序列化集中在这一层，底层 `tools_readonly`
   保持返回 dict（便于脱离 SDK 单测）。
"""

import argparse
import json
import sys

from mcp.server import MCPServer

from . import paths, tools_readonly


def build_server(workspace=None):
    """构建 MCPServer。workspace 为 None 时按 paths 的优先级现解析。"""
    if workspace is None:
        workspace = paths.resolve_workspace()
    mcp = MCPServer("jobws")

    @mcp.tool()
    def list_applications(stage: str = "", keyword: str = "", limit: int = 20) -> str:
        """列出投递记录（只读）。

        stage 精确匹配当前阶段（如 一面 / offer）；keyword 对公司与岗位做
        子串包含匹配；结果按「下次动作日期」升序、终态沉底排序。
        """
        data = tools_readonly.list_applications(
            workspace, stage=stage or None, keyword=keyword or None, limit=limit)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def list_jobs(keyword: str = "", limit: int = 20) -> str:
        """列出岗位池里的岗位（只读）。

        给出公司、岗位、解析卡评分与投递状态（未投递 / 流程中 / 已终态）。
        """
        data = tools_readonly.list_jobs(
            workspace, keyword=keyword or None, limit=limit)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def dashboard_summary() -> str:
        """看板摘要（只读）。

        漏斗分布、近 7 天待办、已过截止仍未投、静默提醒（阶段停留过久）、
        待推进（健康度非正常）、各阶段转化率与失败归因。
        """
        data = tools_readonly.dashboard_summary(workspace)
        return json.dumps(data, ensure_ascii=False, indent=2)

    return mcp


def main(argv=None):
    parser = argparse.ArgumentParser(description="求职工作台 MCP 服务（只读）")
    parser.add_argument("--workspace", default=None,
                        help="工作区名或绝对路径；相对路径按应用根/数据根解析，越界拒绝")
    args = parser.parse_args(argv)
    try:
        workspace = paths.resolve_workspace(args.workspace, must_exist=True)
    except paths.WorkspaceError as exc:
        # 不进 stdout：stdio 传输下那是协议通道
        sys.stderr.write("jobws-mcp: %s\n" % exc)
        return 2
    build_server(workspace).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
