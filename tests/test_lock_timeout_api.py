# -*- coding: utf-8 -*-
"""持锁失败的 HTTP 契约：429 `server.lockTimeout`，不是 500 `server.error`。

`file_lock` 超时抛的是裸 `TimeoutError`，此前全仓没有任何一层接住它 → 冒泡进
兜底 handler，界面收到「服务器内部错误」；而真实原因往往只是「另一处正在写同一份
数据」（另一个标签页、CLI、批量导入）——可重试的预期情况被伪装成了崩溃。

锁超时必须在**契约层**而非各个 router 里翻译：一旦有人在某个入口单独 try/except，
两个入口对用户说的话就会漂。
"""

import contextlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
import lockctx  # noqa: E402
from jobws_core import tracker  # noqa: E402

WS = "ws-lock"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


@contextlib.contextmanager
def _timeout(_path):
    raise TimeoutError("file lock timeout after 0.0s")
    yield  # pragma: no cover - 只为让它是 generator contextmanager


def _seed(tmp_path):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": "A001", "公司": "云帆", "岗位": "后端", "当前阶段": "已投"})
    tracker.write_rows([row], str(tmp_path / WS))
    return row


def test_lock_timeout_is_reported_as_retryable(client, tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setattr(lockctx, "file_lock", _timeout)

    res = client.patch("/api/applications/A001", params={"ws": WS}, json={"备注": "x"})

    assert res.status_code == 429, res.text
    assert res.json()["error_code"] == "server.lockTimeout"
    # 落盘层一个字都没动：拿不到锁就不许写
    rows = tracker.read_rows(str(tmp_path / WS))
    assert rows[0]["备注"] == ""


def test_locked_passes_other_errors_through(monkeypatch):
    """只有 TimeoutError 翻译成契约错误；其余异常原样冒泡（不能被静默吃掉）。"""
    @contextlib.contextmanager
    def _boom(_path):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(lockctx, "file_lock", _boom)

    with pytest.raises(RuntimeError):
        with lockctx.locked("whatever"):
            pass


def test_locked_yields_when_the_lock_is_acquired(tmp_path):
    """否定验证：守卫不能矫枉过正到「一律拒绝」——拿到锁就要正常进。"""
    with lockctx.locked(str(tmp_path / "sample.lock")):
        assert True
