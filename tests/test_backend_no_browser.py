# -*- coding: utf-8 -*-
"""后端「自动开浏览器」开关（JOBWS_NO_BROWSER）的单测。

钉住桌面端多开浏览器那个缺陷的根因面：打包后端启动时要不要弹系统浏览器，
只由该环境变量决定；Electron 壳（web/electron/main.js 的 BACKEND_ENV）负责设为 1。
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import main  # noqa: E402


def test_defaults_to_open(monkeypatch):
    """独立运行：默认允许自动开界面。"""
    monkeypatch.delenv("JOBWS_NO_BROWSER", raising=False)
    assert main._should_open_browser() is True


def test_disabled_by_env(monkeypatch):
    """桌面端/CI：置 1 时不再弹浏览器（容错首尾空白）。"""
    monkeypatch.setenv("JOBWS_NO_BROWSER", "1")
    assert main._should_open_browser() is False
    monkeypatch.setenv("JOBWS_NO_BROWSER", " 1 ")
    assert main._should_open_browser() is False


def test_other_values_keep_browser(monkeypatch):
    """只认 "1"：0 / false / 空串等直觉上表示「要开」的取值保持开，不被静默改判。"""
    for value in ("0", "false", "no", "", " "):
        monkeypatch.setenv("JOBWS_NO_BROWSER", value)
        assert main._should_open_browser() is True, "value=%r" % value
