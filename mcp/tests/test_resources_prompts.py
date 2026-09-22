# -*- coding: utf-8 -*-
"""批 8 新增：只读资源与提示模板的行为。

钉三件事：
1. list 不含数据（按需读取的第一步只列 URI 与描述）；
2. 未知 URI 被拒绝（固定 URI 白名单，无路径参数 → 无穿越面）；
3. 四个提示模板只做参数化组装（非空、含关键指引、不读写文件）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import prompts, resources  # noqa: E402

from jobws_core import tracker  # noqa: E402


@pytest.fixture()
def ws(tmp_path):
    workspace = tmp_path / "personal"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    with io.open(str(tracking / "tracker.csv"), "w", encoding="utf-8-sig",
                 newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.FIELDS,
                                extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerow({"id": "A001", "公司": "云帆", "岗位": "后端",
                         "方向": "backend", "批次": "正式批", "当前阶段": "待投"})
    (workspace / "config").mkdir()
    (workspace / "config" / "profile.md").write_text("---\nkicker: x\n---\n",
                                                     encoding="utf-8")
    return str(workspace)


def test_list_resources_contains_no_data(ws):
    items = resources.list_resources(ws)
    assert len(items) >= 3
    for item in items:
        assert item["uri"].startswith("jobws://workspace/")
        assert set(item) == {"uri", "name", "description", "mimeType"}
        assert "云帆" not in json.dumps(item)  # 清单里绝不夹带数据（夹具里的公司名）


def test_read_known_resource_returns_json(ws):
    text, error = resources.read_resource(ws, "jobws://workspace/applications")
    assert error is None
    payload = json.loads(text)
    assert payload["total"] == 1
    assert payload["items"][0]["公司"] == "云帆"


def test_read_jobs_and_dashboard_resources(ws_with_job):
    """岗位池与看板资源也要真读一遍（批 8 补缺 MINOR-6）。

    此前三个资源只有 applications 有读取用例。dashboard 尤其值得钉：它是**聚合
    口径**，算错了不会报错，只会静默给错数。
    """
    jobs_text, jobs_error = resources.read_resource(ws_with_job,
                                                    "jobws://workspace/jobs")
    assert jobs_error is None, jobs_error
    jobs_payload = json.loads(jobs_text)
    job = next(item for item in jobs_payload["items"] if item["目录"] == "云帆_后端")
    assert job["有JD原文"] is True
    assert job["有解析卡"] is True

    dash_text, dash_error = resources.read_resource(ws_with_job,
                                                    "jobws://workspace/dashboard")
    assert dash_error is None, dash_error
    dash = json.loads(dash_text)
    assert "total" in dash
    assert "funnel" in dash


def test_read_unknown_resource_is_rejected(ws):
    text, error = resources.read_resource(ws, "jobws://workspace/../../etc/passwd")
    assert text is None
    assert "未知资源" in error


def test_prompts_are_nonempty_and_guidance_bearing(ws):
    # 参数注入是提示模板的**全部价值**：传进去的值必须原样出现在渲染结果里。
    # 此前只断言了长度与关键词——参数化这一整个特性等于没测（批 8 补缺 NIT-8）。
    cases = [
        (prompts.review_jd(ws, "01_岗位池/云帆-后端"), "jwb-jd",
         "01_岗位池/云帆-后端"),
        (prompts.generate_application_pack(ws, "01_岗位池/云帆-后端"), "两段式",
         "01_岗位池/云帆-后端"),
        (prompts.interview_review(ws, "A001"), "复盘", "A001"),
        # 用非默认值（14），否则"参数被忽略、写死 7"也照样绿（独立审查 NIT-2）
        (prompts.today_todos(ws, 14), "看板", "14"),
    ]
    for text, keyword, injected in cases:
        assert isinstance(text, str) and len(text) > 40
        assert keyword in text
        assert injected in text, "传入的参数没有出现在提示里：%s" % injected


def test_generate_pack_mentions_confirmation_flow(ws):
    """投递包模板必须提醒走两段式——这是安全边界在提示层的落点。"""
    text = prompts.generate_application_pack(ws, "01_岗位池/云帆-后端")
    assert "preview_add_application" in text or "preview_update_application" in text
    assert "apply_approval" in text


@pytest.fixture()
def ws_with_job(ws):
    """带一个岗位目录的工作区（JD 原文 + 解析卡 + 一个二进制占位）。"""
    job_dir = os.path.join(ws, "01_岗位池", "云帆_后端")
    if not os.path.isdir(job_dir):
        os.makedirs(job_dir)
    with io.open(os.path.join(job_dir, "JD原文.md"), "w", encoding="utf-8") as handle:
        handle.write("# 云帆 后端工程师\n\n负责服务端开发与性能优化。\n")
    with io.open(os.path.join(job_dir, "解析卡.md"), "w", encoding="utf-8") as handle:
        handle.write("# 解析卡\n\n总分：82\n")
    # 二进制不进资源（简历 PDF 等）：放这里是为了钉"它没有入口"这件事
    with io.open(os.path.join(job_dir, "简历.pdf"), "wb") as handle:
        handle.write(b"%PDF-1.4\n")
    return ws


def test_prompts_point_only_to_reachable_data(ws):
    """提示里要的数据必须是 MCP 面**真拿得到**的（批 8 补缺 MAJOR-2）。

    写"读 XX"而实际拿不到，模型只剩空转或**编造**两条路——后者正是本项目最忌的
    结果。所以这里钉两件事：指到的资源真存在，且读不到时给的是明确指引。
    """
    text = prompts.review_jd(ws, "01_岗位池/云帆-后端")
    # 模板资源要单个目录名——提示里必须是取过最后一段的形态，否则永远匹配不上
    assert "jobws://job/云帆-后端/jd" in text
    assert "jobws://job/云帆-后端/card" in text
    assert "推断" in text, "读不到时必须明说不要凭岗位名推断"

    review = prompts.interview_review(ws, "A001")
    assert "verbose=True" in review, "全字段必须显式要，否则拿不到复盘字段"
    assert "不提供阶段时间线" in review, "MCP 面没有的能力必须明说"


def test_job_text_reads_jd_and_card(ws_with_job):
    text, error = resources.read_job_text(ws_with_job, "云帆_后端", "jd")
    assert error is None, error
    assert "云帆 后端工程师" in text

    card, card_error = resources.read_job_text(ws_with_job, "云帆_后端", "card")
    assert card_error is None, card_error
    assert "总分：82" in card


def test_job_text_rejects_escape_and_unknown(ws_with_job):
    # 穿越：目录名里带 `..` 直接被拒（判据在 tools_readonly._job_dir，不是模板层）
    text, error = resources.read_job_text(ws_with_job, "../config", "jd")
    assert text is None and error

    # 含分隔符同样拒——job_name 只能是单个目录名
    text2, error2 = resources.read_job_text(ws_with_job, "01_岗位池/云帆_后端", "jd")
    assert text2 is None and error2

    # 岗位不存在 → 明确错误，不返回空成功（空字符串会被模型当成"JD 就是空的"）
    text3, error3 = resources.read_job_text(ws_with_job, "没有这个岗位", "jd")
    assert text3 is None and "岗位不存在" in error3

    # 未知类型（简历 / 二进制没有入口）
    text4, error4 = resources.read_job_text(ws_with_job, "云帆_后端", "resume")
    assert text4 is None and "未知正文类型" in error4


def test_job_text_truncates_long_content(ws_with_job, monkeypatch):
    monkeypatch.setattr(resources, "JD_TEXT_MAX_BYTES", 64)
    with io.open(os.path.join(ws_with_job, "01_岗位池", "云帆_后端", "JD原文.md"),
                 "w", encoding="utf-8") as handle:
        handle.write("很长的一段JD" * 50)
    text, error = resources.read_job_text(ws_with_job, "云帆_后端", "jd")
    assert error is None
    # 截断必须**说出来**，否则宿主会把半截内容当全文引用
    assert "已截断" in text
    assert "01_岗位池/云帆_后端/JD原文.md" in text
    # **按字节**截断（独立审查 MINOR-1/NIT-3）：此前按字符切，纯中文会把 64 字节
    # 上限放大成 64 字符 ≈ 190 字节——长度断言是唯一能让它变红的东西。
    assert len(text.encode("utf-8")) < 64 + 200, len(text.encode("utf-8"))
