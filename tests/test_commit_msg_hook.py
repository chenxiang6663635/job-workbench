# -*- coding: utf-8 -*-
"""`.githooks/commit_msg.py` 本身的测试。

为什么单独测钩子：它是 git 真正调用的那个文件，前面只测了工具库
（commit_header）等于没测链路。钩子有两处只有它自己才有的行为——

1. **首行提取**：跳过空行与 `#` 注释行、容忍 UTF-8 BOM。编辑器写 BOM 会让首行
   正则失配，这条以前就踩过。
2. **降级路径**：共享模块缺失时给可读提示、退出 0 而不是抛 `ModuleNotFoundError`
   裸栈（实测过：裸栈退出码 1，fail-closed 但不可读，与 pre-commit 在缺 pytest 时
   的既定降级做法不一致）。

另外钉住一条反向激励：钩子**不该**在报错里教人用 `--no-verify`——它管的是文案，
而 `--no-verify` 会连带跳过 pre-commit 的隐私护栏。
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_PATH = os.path.join(ROOT, ".githooks", "commit_msg.py")


def _load_hook():
    spec = importlib.util.spec_from_file_location("commit_msg_hook", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook():
    return _load_hook()


def _write(tmp_path, text, name="msg.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_chinese_subject_passes(hook, tmp_path, capsys):
    assert hook.main([_write(tmp_path, "feat(ui): 迁移到新原语")]) == 0
    assert capsys.readouterr().out == ""


def test_english_subject_blocked(hook, tmp_path, capsys):
    assert hook.main([_write(tmp_path, "feat(ui): migrate to new primitives")]) == 1
    out = capsys.readouterr().out
    assert "必须含中文" in out
    # 不教人用 --no-verify：那是反向激励（会连带跳过隐私护栏）
    assert "--no-verify" not in out
    assert "改文案即可" in out


def test_bom_and_comment_lines_are_skipped(hook, tmp_path):
    """编辑器写 BOM + 注释行时，仍要取到真正的首行。"""
    message = "\ufeff# 这是注释\n\nfeat(ui): 中文说明\n\n正文\n"
    assert hook.main([_write(tmp_path, message)]) == 0


def test_comment_only_message_is_rejected(hook, tmp_path):
    assert hook.main([_write(tmp_path, "# 只有注释\n\n")]) == 1


def test_missing_argv_is_rejected(hook, capsys):
    assert hook.main([]) == 1
    assert "missing message file argument" in capsys.readouterr().out


def test_missing_shared_module_degrades_without_traceback(hook, tmp_path, monkeypatch, capsys):
    """共享模块缺失 → 明确提示 + 退出 0（不阻断提交），而不是抛栈。"""
    monkeypatch.setattr(hook, "commit_header", None)
    assert hook.main([_write(tmp_path, "feat(ui): migrate to new primitives")]) == 0
    out = capsys.readouterr().out
    assert "[SKIP]" in out
    assert "commit_header" in out
    assert "CI" in out  # 说清兜底在哪，避免「跳过」被理解成「没人管」


def test_hook_wiring_points_at_shared_module(hook):
    """把钩子与工具库同源这件事钉住：钩子目录下不该再有一份自己的正则。"""
    with open(HOOK_PATH, encoding="utf-8") as fh:
        source = fh.read()
    assert "import commit_header" in source
    assert "HEADER_PATTERN" not in source
    assert "TYPES" not in source
