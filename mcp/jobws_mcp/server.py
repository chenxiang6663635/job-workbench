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

from . import paths, prompts, resources, tools_readonly, tools_writable


def _server_version():
    """包版本（服务元数据用）；未安装（源码直跑）时回落 "0"，不抛。"""
    from importlib.metadata import PackageNotFoundError, version

    for name in ("jobws-mcp", "jobws_mcp"):
        try:
            return version(name)
        except PackageNotFoundError:
            continue
    return "0"


def build_server(workspace=None):
    """构建 MCPServer。workspace 为 None 时按 paths 的优先级现解析。"""
    if workspace is None:
        workspace = paths.resolve_workspace()
    mcp = MCPServer(
        "jobws",
        title="求职工作台",
        description="本地优先的求职工作台数据接口：只读优先，写入走两段式确认。",
        instructions=(
            "所有数据都在本机工作区（纯文本 CSV / Markdown），不联网。"
            "读取：用 list_* 工具或 jobws:// 资源（按需读，不要全量预载）；"
            "写入：**必须两段式**——先调 preview_* 拿到令牌，把 summary 与 diff "
            "展示给用户，用户确认后再用同一令牌调 apply_approval。"
        ),
        version=_server_version(),
    )

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
                                source: str = "", resume: str = "",
                                archive: str = "", note: str = "",
                                link: str = "") -> str:
        """预览新增一条投递记录（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        """
        data = tools_writable.preview_add_application(workspace, **{
            "公司": company, "岗位": role, "方向": direction, "批次": batch,
            "当前阶段": stage or "待投", "截止日期": deadline, "投递日期": applied,
            "下次动作": next_action, "下次动作日期": next_date,
            "评分": "" if score is None or score < 0 else str(score),
            "来源": source, "简历版本": resume, "归档目录": archive, "备注": note,
            "链接": link,
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
    def preview_update_application(app_id: str, stage: str = "",
                                   next_action: str = "", next_date: str = "",
                                   reason: str = "", score: int = -1,
                                   link: str = "", note: str = "",
                                   applied: str = "", deadline: str = "") -> str:
        """预览更新一条投递记录（**不写入**），返回 token 与逐字段差异表。

        只列**要改**的字段（未传的字段保持原值）；可更新字段与新增同族
        （当前阶段 / 状态原因 / 下次动作 / 下次动作日期 / 备注 / 评分 /
        投递日期 / 截止日期 / 链接）。**先把 diff 展示给用户**，用户确认后
        再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        """
        changes = {}
        for field, value in (("当前阶段", stage), ("状态原因", reason),
                             ("下次动作", next_action), ("下次动作日期", next_date),
                             ("备注", note), ("链接", link),
                             ("投递日期", applied), ("截止日期", deadline)):
            if value:
                changes[field] = value
        if score is not None and score >= 0:
            changes["评分"] = str(score)
        data = tools_writable.preview_update_application(workspace, app_id, changes)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def apply_approval(token: str) -> str:
        """凭令牌执行已确认的写入（两段式的第二步）。

        令牌一次性、默认 10 分钟内有效，且绑定到本服务的工作区——过期、用过、
        或来自别的工作区的令牌都会被拒绝（返回 ok=false 与理由）。
        """
        data = tools_writable.apply_approval(workspace, token)
        return json.dumps(data, ensure_ascii=False, indent=2)

    # --- 批 4.7 主线补口：面试 / 题库 / JD 评分 -------------------------------
    # 一律**追加在末尾**：既有冒烟按注册顺序钉住工具清单，宿主侧也按前缀比对
    # 工具描述做提示缓存——顺序抖动会让缓存全灭。
    @mcp.tool()
    def list_interviews(app_id: str = "", result: str = "", limit: int = 20) -> str:
        """列出面试记录（只读）。

        app_id 只看关联该投递记录的面试（如 A001）；result 精确匹配结果
        （待定 / 通过 / 未通过 / 取消）；按面试时间倒序，空时间排最后。
        """
        data = tools_readonly.list_interviews(
            workspace, app_id=app_id or None, result=result or None, limit=limit)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def score_jd(job_id: str, resume_version: str = "") -> str:
        """读岗位的 JD 解析卡并给出评分与档位（只读）。

        job_id 是岗位池目录名（如 云帆_后端）。解析卡由 AI 或用户写成 Markdown，
        本工具只做**校验与解读**：四个维度之和必须等于总分才给档位（填到一半的
        卡片不给分档）。resume_version 给了才附上差距分析。
        """
        data = tools_readonly.score_jd(workspace, job_id,
                                       resume_version=resume_version or None)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def list_questions(domain: str = "", subject: str = "", status: str = "",
                       keyword: str = "", limit: int = 20) -> str:
        """列出题库题目（只读）。

        按领域 / 科目 / 状态精确筛选；keyword 对题目、答案要点与关联公司岗位做
        子串匹配。筛选口径与命令行 `bank list` 同源。
        """
        data = tools_readonly.list_questions(
            workspace, domain=domain or None, subject=subject or None,
            status=status or None, keyword=keyword or None, limit=limit)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def preview_add_interview(app: str = "", company: str = "", role: str = "",
                              round: str = "一面", when: str = "",
                              form: str = "", link: str = "",
                              interviewer: str = "", questions: str = "",
                              answers: str = "", retro: str = "",
                              result: str = "待定") -> str:
        """预览新增一条面试记录（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        给了 app（关联记录 id）时，公司与岗位自动从主表带出。
        """
        data = tools_writable.preview_add_interview(workspace, **{
            "关联记录": app, "公司": company, "岗位": role, "轮次": round,
            "面试时间": when, "形式": form, "链接": link,
            "面试官": interviewer, "问题记录": questions,
            "我的回答要点": answers, "复盘与改进": retro, "结果": result,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def preview_update_interview(interview_id: str, result: str = "",
                                 when: str = "", round: str = "",
                                 form: str = "", link: str = "",
                                 interviewer: str = "", questions: str = "",
                                 answers: str = "", retro: str = "") -> str:
        """预览更新一条面试记录（**不写入**），返回 token 与逐字段差异表。

        只改**传了值**的字段（未传的保持原值）；interview_id 形如 I001。
        **先把 diff 展示给用户**，用户确认后再用同一个 token 调 apply_approval。
        """
        changes = {}
        for field, value in (("结果", result), ("面试时间", when), ("轮次", round),
                             ("形式", form), ("链接", link),
                             ("面试官", interviewer), ("问题记录", questions),
                             ("我的回答要点", answers), ("复盘与改进", retro)):
            if value:
                changes[field] = value
        data = tools_writable.preview_update_interview(
            workspace, interview_id, changes)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def preview_add_question(title: str, domain: str = "", subject: str = "",
                             tags: str = "", difficulty: str = "",
                             answer: str = "", origin: str = "",
                             company: str = "", role: str = "",
                             status: str = "", note: str = "") -> str:
        """预览新增一道题库题目（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘。
        """
        data = tools_writable.preview_add_question(workspace, **{
            "题目": title, "领域": domain, "科目": subject, "标签": tags,
            "难度": difficulty, "答案要点": answer, "来源": origin,
            "关联公司": company, "关联岗位": role, "状态": status, "备注": note,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def preview_import_questions(module_dir: str = "") -> str:
        """预览从 03_面试准备 导入题目（**不写入**）。

        module_dir 是工作区内的相对目录（默认 03_面试准备），越界会被拒绝。
        其余流程同上：展示 diff → 用户确认 → apply_approval 落盘。
        """
        data = tools_writable.preview_import_questions(
            workspace, module_dir=module_dir or None)
        return json.dumps(data, ensure_ascii=False, indent=2)

    # --- 资源（批 8）：固定 URI、按需读取（list 不触发任何数据读取）-----------
    def _make_reader(uri):
        # 固定 URI 的 handler 必须**无参**（SDK 校验签名与 URI 模板变量一致），
        # 所以用工厂闭合 uri——顺带避开循环里闭包晚绑定的坑。
        def _read():
            text, error = resources.read_resource(workspace, uri)
            if text is not None:
                return text
            return json.dumps({"ok": False, "errors": [error]}, ensure_ascii=False)

        return _read

    for _item in resources.list_resources(workspace):
        mcp.resource(_item["uri"], name=_item["name"],
                     description=_item["description"],
                     mime_type=_item["mimeType"])(_make_reader(_item["uri"]))

    # --- 提示模板（批 8）：四个参数化工作流，与技能分工不重叠（见 prompts.py）--
    @mcp.prompt(name="review_jd",
                description="评估岗位 JD：资格门槛 → 四维评分 → 投递建议")
    def review_jd(job_dir: str = "") -> str:
        """评估一个岗位的 JD（只读）。job_dir 留空时先让用户选岗位。"""
        return prompts.review_jd(workspace, job_dir)

    @mcp.prompt(name="generate_application_pack",
                description="生成投递包：按 JD 改简历 → 归档 → 记入追踪表（写入走确认）")
    def generate_application_pack(job_dir: str = "") -> str:
        """生成投递包。所有写入必须走两段式（preview → 用户确认 → apply）。"""
        return prompts.generate_application_pack(workspace, job_dir)

    @mcp.prompt(name="interview_review",
                description="面试复盘：汇总面试记录 → 表现要点与改进项")
    def interview_review(app_id: str = "") -> str:
        """做一次面试复盘（只读）。app_id 留空时先让用户选一条记录。"""
        return prompts.interview_review(workspace, app_id)

    @mcp.prompt(name="today_todos",
                description="今日待办：从看板摘要挑出今天该做的事")
    def today_todos(days: int = 7) -> str:
        """整理今天的求职待办（只读）。days 是待办窗口天数（默认 7）。"""
        return prompts.today_todos(workspace, days)

    return mcp


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="求职工作台 MCP 服务（默认只读；写入走两段式确认）")
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
