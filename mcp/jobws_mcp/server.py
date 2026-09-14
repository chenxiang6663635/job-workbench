# -*- coding: utf-8 -*-
"""MCP 服务入口：只读工具 + 两段式写入工具，stdio 传输。

两条写在最前面的纪律：

1. **stdout 是协议通道**——stdio 传输下任何 print 都会变成畸形报文。
   诊断信息一律走 stderr（所以 `main()` 的错误出口是 `sys.stderr.write`）。
2. **工具返回 JSON 文本**而不是 dict：宿主侧拿到的是字符串，结构化输出留到
   SDK 各版本行为稳定之后再说；序列化集中在这一层，底层 `tools_readonly` /
   `tools_writable` 保持返回 dict（便于脱离 SDK 单测）。

写入工具是**两段式**的：`preview_*` 只给出令牌与差异（不落盘），
`apply_approval(token)` 才真正写入。宿主必须先把 summary/diff 展示给用户，
拿到同意后再调 apply——这是协议上的留痕，不靠提示词约束。
"""

import argparse
import json
import sys

from mcp.server import MCPServer

from . import paths, tools_readonly, tools_writable


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

    @mcp.tool()
    def preview_add_application(company: str, role: str, direction: str, batch: str,
                                stage: str = "待投", deadline: str = "",
                                applied: str = "", next_action: str = "",
                                next_date: str = "", score: int = -1,
                                source: str = "", note: str = "") -> str:
        """预览新增一条投递记录（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        """
        data = tools_writable.preview_add_application(workspace, **{
            "公司": company, "岗位": role, "方向": direction, "批次": batch,
            "当前阶段": stage or "待投", "截止日期": deadline, "投递日期": applied,
            "下次动作": next_action, "下次动作日期": next_date,
            "评分": "" if score is None or score < 0 else str(score),
            "来源": source, "备注": note,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def preview_import_applications(csv_text: str) -> str:
        """预览批量导入投递记录（**不写入**）。

        csv_text 是 CSV 全文（含表头）。有错误行时不给令牌——先让用户修数据。
        其余流程同上：展示 diff → 用户确认 → apply_approval。
        """
        data = tools_writable.preview_import_applications(workspace, csv_text)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def apply_approval(token: str) -> str:
        """凭令牌执行已确认的写入（两段式的第二步）。

        令牌一次性、默认 10 分钟内有效，且绑定到本服务的工作区——过期、用过、
        或来自别的工作区的令牌都会被拒绝（返回 ok=false 与理由）。
        """
        data = tools_writable.apply_approval(workspace, token)
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
