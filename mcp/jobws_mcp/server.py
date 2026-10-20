# -*- coding: utf-8 -*-
"""MCP 服务入口：装配 MCPServer 并把原语注册挂上去，stdio 传输。

两条写在最前面的纪律：

1. **stdout 是协议通道**——stdio 传输下任何 print 都会变成畸形报文。
   诊断信息一律走 stderr（所以 `main()` 的错误出口是 `sys.stderr.write`）。
2. **工具返回 JSON 文本**而不是 dict：宿主侧拿到的是字符串，结构化输出留到
   SDK 各版本行为稳定之后再说；序列化集中在注册层，底层 `tools_readonly` /
   `tools_writable` 保持返回 dict（便于脱离 SDK 单测）。

写入工具是**两段式**的：`preview_*` 只给出令牌与差异（不落盘），
`apply_approval(token)` 才真正写入。宿主必须先把 summary/diff 展示给用户，
拿到同意后再调 apply——这是协议上的留痕，不靠提示词约束。

注册面分三处（2026-10-12 拆分）：`tool_registry` 管**工具**（按能力分组、按序
注册），`resources` 管只读资源与岗位正文工具，`prompts` 管提示模板——本文件只做
装配与命令行入口，别再往这里堆注册块（2026-10-12 撞过两道规模闸：文件 378 行与
`build_server()` 254 行）。
"""

import argparse
import sys

from mcp.server import MCPServer

from . import guard, info, init_workspace, paths, prompts, resources, tool_registry

# A2 信息工具 / B4 数据根守卫 / 路径解析 / 资源 / 提示 / 工具注册表


def build_server(workspace=None):
    """构建 MCPServer。workspace 为 None 时按 paths 的优先级现解析。"""
    if workspace is None:
        workspace = paths.resolve_workspace()
    mcp = MCPServer(
        "jobws",
        title="求职工作台",
        description="本地优先的求职工作台数据接口：只读优先，写入走两段式确认。",
        instructions=(
            "所有数据都在本机工作区（纯文本 CSV / Markdown）；本服务自身不联网、不上传，宿主对返回内容的使用受宿主隐私策略约束。"
            "读取：用 list_* 工具或 jobws:// 资源（按需读，不要全量预载）；"
            "写入：**必须两段式**——先调 preview_* 拿到令牌，把 summary 与 diff "
            "展示给用户，用户确认后再用同一令牌调 apply_approval。"
            + info.ambiguous_hint(workspace)   # 仅歧义时附一行（不带本机路径）
        ),
        version=info.server_version(),
        middleware=[guard.DataRootGuard()],  # B4：tools/call 前查数据根（fail-closed）
    )

    # 工具：四组**按序**注册（顺序即协议输出顺序，见 tool_registry 的顺序纪律）
    tool_registry.register_all(mcp, workspace)

    # --- A2：数据根诊断（只读）--------------------------------------------------
    # 注册名是 `jobws.info`（带点，宿主可见）；实现与序列化在 info.py。
    # 工具一律**追加在既有工具之后**（批 4.7 的顺序纪律；其后还有 `read_job_text`）：
    # 宿主的工具描述缓存不失效。
    info.register(mcp, workspace)

    # --- 2026-10-12 收口：正文工具 + 只读资源 + 提示模板（注册在各自模块）-----
    # 顺序：`read_job_text` 是**工具**，按批 4.7 的顺序纪律追加在注册末尾（宿主的
    # 工具描述缓存不失效）；资源与提示是独立命名空间，注册次序不构成缓存面。
    resources.register_text_tool(mcp, workspace)

    # --- E 批（2026-10-16）：筛选校准（只读）-----------------------------------
    # 排在 `read_job_text` 之后：协议顺序的真实末尾在这，塞进 register_all 会把
    # 它插到 jobws.info / read_job_text 前面（批 4.7 纪律要防的正是这个）。
    tool_registry.register_calibration_tools(mcp, workspace)

    resources.register(mcp, workspace)
    prompts.register(mcp, workspace)

    return mcp


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="求职工作台 MCP 服务（默认只读；写入走两段式确认）")
    parser.add_argument("--workspace", default=None,
                        help="工作区名或绝对路径；相对路径按应用根/数据根解析，越界拒绝")
    parser.add_argument("--init", action="store_true",
                        help="把随包模板铺成空工作区（幂等、不覆盖已有文件）后退出；"
                             "只装插件的用户首次使用需要它")
    args = parser.parse_args(argv)

    if args.init:
        target = paths.resolve_default_workspace()
        created = init_workspace.init_workspace(target)
        # 一律走 stderr：stdio 传输下 stdout 是协议通道
        if created:
            sys.stderr.write("jobws-mcp: 已初始化空工作区 %s（%d 个文件）\n"
                             % (target, len(created)))
        else:
            sys.stderr.write("jobws-mcp: 工作区已存在，未改动：%s\n" % target)
        return 0

    try:
        # 默认根 + 缺失 → 自动建空骨架（零配置可用）；显式配置 → 仍然报错
        workspace, notice = init_workspace.ensure_workspace(args.workspace)
    except paths.WorkspaceError as exc:
        sys.stderr.write("jobws-mcp: %s\n" % exc)
        return 2
    if notice:
        sys.stderr.write(notice + "\n")
    build_server(workspace).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
