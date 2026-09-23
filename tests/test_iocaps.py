# -*- coding: utf-8 -*-
"""`web/backend/iocaps.py` 的上限语义（P2，2026-09-23 审计）。

两条断言是最要紧的：
1. 超限必须**截断而不是把整个文件读进来**（否则上限只是个装饰）；
2. 未超限一个字节都不能少——护栏矫枉过正到「一律截断」比没有更糟（内容悄悄
   少了一截，界面上还看不出来）。
"""

import io
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

from iocaps import read_bytes_capped, read_text_capped  # noqa: E402


def test_text_under_limit_is_complete(tmp_path):
    path = tmp_path / "card.md"
    path.write_text("完整内容\n第二行\n", encoding="utf-8")
    text, truncated = read_text_capped(str(path))
    assert text == "完整内容\n第二行\n"
    assert truncated is False


def test_text_over_limit_is_truncated(tmp_path):
    path = tmp_path / "huge.md"
    path.write_text("x" * 5000, encoding="utf-8")

    text, truncated = read_text_capped(str(path), limit=1000)

    assert len(text) == 1000, "超限必须截断——不然上限只是装饰"
    assert truncated is True


def test_bytes_under_limit_is_complete(tmp_path):
    path = tmp_path / "blob.bin"
    payload = bytes(range(256))
    path.write_bytes(payload)

    data, truncated = read_bytes_capped(str(path))

    assert data == payload
    assert truncated is False


def test_bytes_over_limit_is_truncated(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"\x01" * 5000)

    data, truncated = read_bytes_capped(str(path), limit=1024)

    assert len(data) == 1024
    assert truncated is True


def test_missing_file_still_raises(tmp_path):
    """否定验证：上限不该顺手把「文件不存在」也吞掉。"""
    import pytest

    with pytest.raises(IOError):
        read_text_capped(str(tmp_path / "nope.md"))
