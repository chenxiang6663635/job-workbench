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

import tracker  # noqa: E402  （tools/ 已由 jobws_mcp.paths 加进 sys.path）


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


def test_read_unknown_resource_is_rejected(ws):
    text, error = resources.read_resource(ws, "jobws://workspace/../../etc/passwd")
    assert text is None
    assert "未知资源" in error


def test_prompts_are_nonempty_and_guidance_bearing(ws):
    cases = [
        (prompts.review_jd(ws, "01_岗位池/云帆-后端"), "jwb-jd"),
        (prompts.generate_application_pack(ws, ""), "两段式"),
        (prompts.interview_review(ws, "A001"), "复盘"),
        (prompts.today_todos(ws, 7), "看板"),
    ]
    for text, keyword in cases:
        assert isinstance(text, str) and len(text) > 40
        assert keyword in text


def test_generate_pack_mentions_confirmation_flow(ws):
    """投递包模板必须提醒走两段式——这是安全边界在提示层的落点。"""
    text = prompts.generate_application_pack(ws, "01_岗位池/云帆-后端")
    assert "preview_add_application" in text or "preview_update_application" in text
    assert "apply_approval" in text
