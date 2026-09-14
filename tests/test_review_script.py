# -*- coding: utf-8 -*-
"""scripts/review.py 的回归护栏。

背景：这个脚本的宿主分支连续踩过三个「只有实跑才暴露」的坑——
① Windows 上 codex 是 npm 的 `.CMD` 包装，含换行的长参数被 cmd.exe 截断到
   第一个换行（审查方只收到标题一行）；
② 用户级 execpolicy 白名单（`~/.codex/rules/*.rules`）不含审查命令 → 被判
   「需要审批」→ `approval: never` 下直接拒绝（blocked by policy）；
③ `--ignore-user-config` 会令 Windows 默认沙箱连读命令一起拒。
本文件把当时的修复固化成断言，防止「好心」把 flag 组合改回去。

全部离线运行：不依赖 git 历史（CI 的 checkout 环境各不相同），也不写仓库根。
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

import review  # noqa: E402


def _offline_git(heads=None, dirty=False):
    """可控的 _git 替身：diff 非空，rev-parse 按表返回（缺省同一 sha）。"""
    heads = heads or {}

    def fake(args):
        if args[0] == "rev-parse":
            return heads.get(args[1], "aaaa111122223333") + "\n"
        if args[0] == "status":
            return " M x\n" if dirty else ""
        if args[0] == "diff":
            return "diff --git a/x b/x\n+hello\n"
        if args[0] == "log":
            return "abc1234 feat: fake\n"
        raise AssertionError("未预期的 git 调用：%s" % (args,))

    return fake


def test_codex_flags_keep_sandbox_and_ignore_rules():
    """要 --ignore-rules（白名单误伤）与只读沙箱；不要 --ignore-user-config（沙箱误伤）。"""
    argv = review._codex_cmd("codex")
    assert argv[argv.index("-s") + 1] == "read-only"
    assert "--ignore-rules" in argv
    # 实测（2026-09-14）：缺了用户 config 的 [windows] sandbox 设置，
    # Windows 默认沙箱连读命令都拒（blocked by policy）
    assert "--ignore-user-config" not in argv


def test_codex_argv_carries_only_ascii_nav_line():
    """命令行只带单行 ASCII 导航语：多行参数会被 `.CMD` 包装截断、中文参数受 cmd 代码页影响。"""
    nav = review._codex_cmd("codex")[-1]
    assert "\n" not in nav
    assert nav.isascii()
    assert os.path.basename(review.PROMPT_OUT) in nav


def test_claude_flags_deny_write_tools():
    """allowedTools 是「免询问」而非「仅允许」——写/执行类工具必须显式拉黑（M1）。"""
    argv = review._claude_cmd("claude")
    denied = argv[argv.index("--disallowedTools") + 1:argv.index("--output-format")]
    for tool in ("Bash", "Edit", "Write"):
        assert tool in denied
    nav = argv[argv.index("-p") + 1]
    assert "\n" not in nav
    assert nav.isascii()


def test_worktree_note_same_and_mismatch(monkeypatch):
    """--head 指向别的提交时，提示词必须写明「判据以 diff 为准」（M2）。"""
    monkeypatch.setattr(review, "_git", _offline_git())
    same = review._worktree_note("HEAD")
    assert "即审查对象" in same

    monkeypatch.setattr(review, "_git", _offline_git(
        heads={"HEAD": "aaaa111122223333", "old-ref": "bbbb444455556666"}))
    other = review._worktree_note("old-ref")
    assert "不是同一版本" in other
    assert "以 diff 为准" in other

    monkeypatch.setattr(review, "_git", _offline_git(dirty=True))
    dirty_same = review._worktree_note("HEAD")
    assert "未提交修改" in dirty_same


def test_prompt_renders_all_placeholders(tmp_path, monkeypatch):
    """模板占位符必须全部渲染——漏一个就把 {{X}} 原样发给审查方。"""
    with open(review.PROMPT_FILE, "r", encoding="utf-8") as handle:
        template = handle.read()
    placeholders = set(re.findall(r"\{\{[A-Z_]+\}\}", template))
    assert "{{WORKTREE_NOTE}}" in placeholders

    monkeypatch.setattr(review, "_git", _offline_git())
    monkeypatch.setattr(review, "DIFF_FILE", str(tmp_path / "diff.patch"))
    monkeypatch.setattr(review, "PROMPT_OUT", str(tmp_path / "prompt.md"))
    rendered = review._prepare("HEAD", "HEAD")[0]
    assert "{{" not in rendered


def test_dry_run_needs_no_host(tmp_path, monkeypatch, capsys):
    """dry-run 只准备材料：没有宿主 CLI 也应成功退出（且不探测宿主）。"""
    monkeypatch.setattr(sys, "argv",
                        ["review.py", "--dry-run", "--base", "HEAD", "--head", "HEAD"])
    monkeypatch.setattr(review, "_git", _offline_git())
    monkeypatch.setattr(review, "DIFF_FILE", str(tmp_path / "diff.patch"))
    monkeypatch.setattr(review, "PROMPT_OUT", str(tmp_path / "prompt.md"))

    def _boom(_preferred):
        raise AssertionError("dry-run 不应探测宿主")

    monkeypatch.setattr(review, "_pick_host", _boom)
    assert review.main() == 0
    out = capsys.readouterr().out
    assert "未调用宿主" in out
    assert os.path.exists(str(tmp_path / "prompt.md"))
