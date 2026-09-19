# -*- coding: utf-8 -*-
"""共享只读原语（web/backend/ro_files.py）的直接单测。

端点层的行为（错误码、截断字段的双向契约）由 test_prep_api.py 钉住；这里守
原语本身的规则：遍历的确定性与过滤、解码的严格性与截断回退、realpath 归属判断。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

import ro_files  # noqa: E402


def _write(base, rel, content):
    path = os.path.join(str(base), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


# --- walk_files ---------------------------------------------------------------


def test_walk_files_filters_and_sorts(tmp_path):
    _write(tmp_path, "b.md", "B")
    _write(tmp_path, "a.md", "A")
    _write(tmp_path, "sub/c.md", "C")
    _write(tmp_path, "sub/.hidden.md", "H")
    _write(tmp_path, ".obsidian/x.md", "X")
    _write(tmp_path, "__pycache__/y.md", "Y")
    _write(tmp_path, "note.txt", "T")

    # 隐藏目录（. 与 __ 开头）与隐藏文件都不出现；rel 字典序是唯一排序口径
    rels = [item["rel"] for item in ro_files.walk_files(tmp_path)]
    assert rels == ["a.md", "b.md", "note.txt", "sub/c.md"]

    only_md = [item["rel"] for item in ro_files.walk_files(tmp_path, exts={".md"})]
    assert only_md == ["a.md", "b.md", "sub/c.md"]


def test_walk_files_missing_dir_is_empty(tmp_path):
    assert ro_files.walk_files(tmp_path / "无此目录") == []


def test_walk_files_keeps_zero_byte(tmp_path):
    _write(tmp_path, "空.md", "")
    items = ro_files.walk_files(tmp_path)
    assert [item["size"] for item in items] == [0]


def test_walk_files_fields(tmp_path):
    _write(tmp_path, "sub/一篇.md", "# 标题")
    item = ro_files.walk_files(tmp_path)[0]
    assert item["name"] == "一篇.md"
    assert item["rel"] == "sub/一篇.md"  # 正斜杠归一
    assert item["mtime"] > 0


# --- decode_text / read_text_limited ------------------------------------------


def test_decode_text_strips_bom():
    assert ro_files.decode_text("# hi".encode("utf-8-sig"), False) == "# hi"


def test_decode_text_truncation_falls_back():
    raw = ("字" * 10).encode("utf-8")[:20]  # 切坏最后一个字符（每字 3 字节）
    assert ro_files.decode_text(raw, True) == "字" * 6


def test_decode_text_prefers_longest_prefix():
    # 回退取**最长**可解码前缀（从最小切法开始试）；顺序反了会把
    # b"abc\xE4" 解成 "a"——丢两个完整字符（独立审查 MINOR-1）
    raw = "abc".encode("utf-8") + "中".encode("utf-8")[:1]
    assert ro_files.decode_text(raw, True) == "abc"


def test_decode_text_rejects_non_utf8():
    with pytest.raises(ro_files.TextDecodeError):
        ro_files.decode_text("中文".encode("gbk"), False)


def test_read_text_limited_reports_real_bytes(tmp_path):
    body = "字" * (100 * 1024)  # 300KB，超 256KB 上限
    path = _write(tmp_path, "大.md", body)
    text, truncated, size = ro_files.read_text_limited(path)
    assert truncated is True
    assert size == os.path.getsize(path)  # 真实总字节，不是返回内容长度
    assert len(text.encode("utf-8")) <= ro_files.CONTENT_MAX_BYTES


# --- inside -------------------------------------------------------------------


def test_inside_accepts_child_rejects_sibling(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    assert ro_files.inside(str(base), str(base / "a.txt")) is True
    assert ro_files.inside(str(base), str(tmp_path / "outside.txt")) is False


@pytest.mark.skipif(os.name != "posix", reason="符号链接场景仅在 POSIX 上验证")
def test_inside_rejects_symlink_escape(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("x", encoding="utf-8")
    os.symlink(str(outside), str(base / "link"))
    assert ro_files.inside(str(base), str(base / "link" / "x.txt")) is False
