# -*- coding: utf-8 -*-
"""stdio 冒烟：真起一个子进程，用官方 client 走完握手 → 列出工具 → 调一次。

只在装了 MCP SDK 的环境运行（需要 Python 3.10+）：CI 由独立的 3.12 job 跑，
主干环境没装 SDK 时 `importorskip` 会自动跳过而不是报错。

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
    # 岗位正文（批 8 补缺的模板资源）：一个岗位目录 + JD 原文。目录名用中文，
    # 顺带钉住"模板变量能匹配非 ASCII 目录名"这件事（匹配不上会静默 404）。
    job_dir = os.path.join(ws, "01_岗位池", "探针_岗位")
    if not os.path.isdir(job_dir):
        os.makedirs(job_dir)
    with io.open(os.path.join(job_dir, "JD原文.md"), "w", encoding="utf-8") as f:
        f.write("# 探针岗位的 JD\n\n用于验证模板资源能被协议层读到。\n")


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
            init_result = await session.initialize()
            listed = await session.list_tools()
            # 固定顺序（批 8）：**不排序**——注册顺序就是协议输出顺序；
            # 顺序抖动会让宿主的 tools/list 提示缓存整段失效。
            names = [t.name for t in listed.tools]
            assert names == ["list_applications", "list_jobs", "dashboard_summary",
                             "preview_add_application",
                             "preview_import_applications",
                             "preview_update_application", "apply_approval",
                             # 批 4.7 主线补口，同样**追加在末尾**（顺序不许动）
                             "list_interviews", "score_jd", "list_questions",
                             "preview_add_interview", "preview_update_interview",
                             "preview_add_question", "preview_import_questions"]

            result = await session.call_tool("dashboard_summary", {})
            text = result.content[0].text
            assert json.loads(text)["total"] == 1

            # 两段式写入走一遍真通道：preview 不落盘，apply 才写。
            # 这条比单测更硬——它验的是宿主实际要走的那条路（stdio + JSON 序列化）。
            tracker_csv = os.path.join(ws, "05_投递追踪", "tracker.csv")
            with open(tracker_csv, "rb") as handle:
                before = handle.read()

            preview = await session.call_tool("preview_add_application", {
                "company": "示例公司乙", "role": "示例岗位丙",
                "direction": "backend", "batch": "正式批"})
            data = json.loads(preview.content[0].text)
            assert data["ok"] is True, data
            with open(tracker_csv, "rb") as handle:
                assert handle.read() == before, "预览阶段不许落盘"

            applied = await session.call_tool("apply_approval", {"token": data["token"]})
            assert json.loads(applied.content[0].text)["ok"] is True
            with open(tracker_csv, "rb") as handle:
                assert handle.read() != before, "apply 之后应真的写入"

            # --- 批 4.7 的新工具同样走一遍真通道 -------------------------------
            # 只读两件：面试列表（此刻应为空）与题库列表；再加越界拒绝这条负路径。
            empty_interviews = await session.call_tool("list_interviews", {})
            assert json.loads(empty_interviews.content[0].text)["total"] == 0

            questions = await session.call_tool("list_questions", {})
            assert json.loads(questions.content[0].text)["total"] == 0

            escaped = await session.call_tool("score_jd", {"job_id": "../config"})
            escaped_data = json.loads(escaped.content[0].text)
            assert escaped_data["ok"] is False, "越界的 job_id 必须被拒绝"

            # 面试两段式：预览不落盘 → apply 才写（与投递同一条硬约束）
            interview_csv = os.path.join(ws, "05_投递追踪", "interviews.csv")
            preview_interview = await session.call_tool("preview_add_interview", {
                "app": "1", "round": "一面"})
            inv = json.loads(preview_interview.content[0].text)
            assert inv["ok"] is True, inv
            assert not os.path.isfile(interview_csv), "预览阶段不许落盘"

            applied_interview = await session.call_tool(
                "apply_approval", {"token": inv["token"]})
            assert json.loads(applied_interview.content[0].text)["ok"] is True
            assert os.path.isfile(interview_csv), "apply 之后应真的写入"

            # verbose 透传（批 8 补缺 MINOR-3）：默认精简列与全字段必须**真不同**——
            # 否则"全字段用可选参数展开"这条性能红线在宿主路径上形同虚设
            # （此前 verbose 只到领域层，MCP 签名根本不透传）。
            plain = await session.call_tool("list_interviews", {})
            plain_item = json.loads(plain.content[0].text)["items"][0]
            full = await session.call_tool("list_interviews", {"verbose": True})
            full_item = json.loads(full.content[0].text)["items"][0]
            assert "问题记录" not in plain_item
            assert "问题记录" in full_item

            # --- 批 8 补缺：资源与提示必须走**协议**（SDK 接线层）验证 ---------
            # 此前只测了纯函数（resources.read_resource / prompts.*），SDK 那一层
            # 一行断言都没有——唯一保障是"子进程起得来不报错"。注册写错时（比如
            # handler 签名与 URI 模板变量不一致、mime_type 不受支持）那层保障
            # 根本拦不住，故这里逐条走真通道（属性名经探针实测，勿凭记忆改）。
            listed_resources = await session.list_resources()
            resource_uris = [item.uri for item in listed_resources.resources]
            assert resource_uris == [
                "jobws://workspace/applications",
                "jobws://workspace/jobs",
                "jobws://workspace/dashboard",
            ], resource_uris

            applications = await session.read_resource(
                "jobws://workspace/applications")
            payload = json.loads(applications.contents[0].text)
            # 不钉总数：本用例前半段已经 apply 落过一条记录，总数会随前面的步骤
            # 变化——这里要验的是"资源真把工作区数据读出来了"，不是计数。
            assert "示例科技" in [item["公司"] for item in payload["items"]]

            # 模板资源：注册成 template（不是静态资源），且**中文目录名能匹配上**。
            # 匹配不上时 read_resource 只会报"未知资源"，很容易被当成小事——
            # 而它意味着宿主永远拿不到 JD 正文，提示模板会退化成空转。
            templates = await session.list_resource_templates()
            assert len(templates.resource_templates) == 2, templates.resource_templates
            jd_resource = await session.read_resource("jobws://job/探针_岗位/jd")
            assert "探针岗位的 JD" in jd_resource.contents[0].text

            listed_prompts = await session.list_prompts()
            prompt_names = sorted(item.name for item in listed_prompts.prompts)
            assert prompt_names == ["generate_application_pack",
                                    "interview_review", "review_jd",
                                    "today_todos"], prompt_names

            # 参数注入是提示模板的全部价值：传进去的 job_dir 必须原样出现在文本里
            marker = "探针-岗位X"
            rendered = await session.get_prompt("review_jd", {"job_dir": marker})
            assert marker in rendered.messages[0].content.text

            # 服务元数据：instructions 是宿主理解"只读优先 / 两段式"的唯一来源，
            # 空了或退化没人会报错——这里钉一句关键词。
            assert "两段式" in (init_result.instructions or "")
