# -*- coding: utf-8 -*-
"""`paths.resolve_within_workspace` 的越界判定：与 containment 同源。

收编背景（2026-10-09 桶二）：三类越界写法（绝对 / `..` 段 / 盘符相对）的
判据此前在本函数里手写了一份，与 `containment.escape_reason` 并行存在——
现在只保留一层判据（文案映射仍在这边，因为措辞是既有对外形态、被测试钉住）。

两条网：
1. **委托证明**：把 `containment.escape_reason` 换成替身，函数必须跟着走
   （有人再抄一份规则进来，这里会红）；
2. **文案关键词**：三类各自的提示词保留（`盘符` 等是宿主能看懂的关键词）。
"""
import os
import sys

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import paths  # noqa: E402


def test_resolve_within_workspace_delegates_to_the_shared_judge(monkeypatch):
    """判据来自 `containment.escape_reason`：替换它，函数必须拒绝本来合法的名字。"""
    monkeypatch.setattr(paths.containment, "escape_reason",
                        lambda name: "含 .. 段")

    real, rel, err = paths.resolve_within_workspace("ws", "正常名字", "模块目录")

    assert real is None and rel is None
    assert ".. 段" in err, err


def test_resolve_within_workspace_keeps_the_three_class_messages():
    for value, keyword in (("/etc/passwd", "绝对路径"),
                           ("../x", ".. 段"),
                           ("C:foo", "盘符")):
        real, rel, err = paths.resolve_within_workspace("ws", value, "目录")
        assert real is None and rel is None, value
        assert keyword in err, (value, err)


def test_resolve_within_workspace_still_rejects_empty_and_dot():
    """`.` / 空白：判据层不管这个（不是越界写法），工具层仍按「不能为空」拒。"""
    for value in (".", "   ", ""):
        real, rel, err = paths.resolve_within_workspace("ws", value, "目录")
        assert real is None and "不能为空" in err, (value, err)


def test_resolve_within_workspace_accepts_normal_names():
    real, rel, err = paths.resolve_within_workspace("ws", "a/b", "目录")
    assert err is None, err
    assert rel == "a/b" and real
