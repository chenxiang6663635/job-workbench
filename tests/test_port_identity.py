# -*- coding: utf-8 -*-
"""端口身份判据（ADR: docs/decisions/port-identity.md）。

`_is_our_service` 是「复用一个已在跑的服务」的身份关：只认结构化
`{"status": "ok"}`——子串匹配（`b"ok" in r.read()`）会让任何返回 ok 字样的
本地服务被当成后端（复用 = 界面接错进程）。全部离线：urlopen 被 mock。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))


class _Resp:
    """urlopen 的最小假响应（context manager + read）。"""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def main_module(tmp_path, monkeypatch):
    """与其他后端测试同款：钉数据根，再 import main（导入期会读环境）。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import deps

    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    import main

    return main


def _patch_urlopen(monkeypatch, payload):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout=None: _Resp(payload))


def test_health_json_ok_is_ours(monkeypatch, main_module):
    _patch_urlopen(monkeypatch, b'{"status": "ok"}')
    assert main_module._is_our_service(8765) is True


def test_substring_ok_is_not_enough(monkeypatch, main_module):
    """含 ok 字样的陌生服务不是我们的后端（2026-10-07 判据收紧）。"""
    _patch_urlopen(monkeypatch, b"ok")
    assert main_module._is_our_service(8765) is False
    _patch_urlopen(monkeypatch, b"all ok, promise")
    assert main_module._is_our_service(8765) is False


def test_other_status_values_are_not_ready(monkeypatch, main_module):
    _patch_urlopen(monkeypatch, b'{"status": "starting"}')
    assert main_module._is_our_service(8765) is False


def test_network_errors_mean_false(monkeypatch, main_module):
    def _boom(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert main_module._is_our_service(8765) is False
