# -*- coding: utf-8 -*-
"""jobws prefs 的读写与边界（批 4，4f）。

钉住四件事：空读数、写读回环、未知 key 拒绝（拼错 key 不许静默落盘）、
原子写不产生半截文件。工作区经 monkeypatch 重定向到 tmp——绝不碰真实工作区。
"""
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefs  # noqa: E402


class _Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    target = tmp_path / "ws"
    (target / "05_投递追踪").mkdir(parents=True)
    monkeypatch.setattr(prefs.tracker, "resolve_ws", lambda workspace=None: str(target))
    return str(target)


def test_read_defaults_to_empty(ws):
    assert prefs.read_prefs() == {}


def test_set_then_get_roundtrip(ws, capsys):
    assert prefs.cmd_set(_Args(key="theme", value="catppuccin-mocha")) == 0
    assert "已保存" in capsys.readouterr().out
    assert prefs.read_prefs() == {"theme": "catppuccin-mocha"}


def test_unknown_key_rejected(ws, capsys):
    assert prefs.cmd_set(_Args(key="them", value="nord")) == 1
    assert "未知偏好 key" in capsys.readouterr().out
    # 拒绝时不得落盘（拼错的 key 静默写进文件是最难查的那类问题）
    assert not os.path.isfile(prefs.prefs_path())


def test_empty_value_rejected(ws, capsys):
    assert prefs.cmd_set(_Args(key="theme", value="   ")) == 1
    assert "不能为空" in capsys.readouterr().out


def test_write_is_atomic_no_tmp_left(ws):
    prefs.write_prefs({"font": "system"})
    directory = os.path.dirname(prefs.prefs_path())
    leftovers = [name for name in os.listdir(directory) if name.endswith(".tmp")]
    assert leftovers == []
    with io.open(prefs.prefs_path(), "r", encoding="utf-8") as handle:
        assert json.load(handle) == {"font": "system"}


def test_doctor_recommends_terminal_fonts(ws, capsys):
    assert prefs.cmd_doctor(_Args()) == 0
    out = capsys.readouterr().out
    assert "Maple Mono" in out
    assert "终端字体" in out


def test_get_single_key(ws, capsys):
    prefs.write_prefs({"theme": "nord", "font": "default"})
    assert prefs.cmd_get(_Args(key="theme")) == 0
    assert capsys.readouterr().out.strip() == "nord"
    assert prefs.cmd_get(_Args(key="resume_style")) == 0
    assert capsys.readouterr().out.strip() == ""
