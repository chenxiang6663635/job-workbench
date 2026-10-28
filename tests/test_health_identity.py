# -*- coding: utf-8 -*-
"""/api/health 的身份字段。

为什么值得单测（2026-10-28 审计）：桌面壳靠这个端点判断「8765 上是不是本工作台」。
只要它只回 `{"status":"ok"}`，任何返回 ok 的陌生服务都会被当成我们的后端——
隔离数据根（`JOBWS_DATA_DIR`）因此**验收不了**：两个实例之间分辨不出来。

前端侧的对应用例在 `web/electron/backend_process.test.js`；两侧都改才算闭环
（单侧改动会让桌面壳永远等不到「就绪」）。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def test_health_reports_service_identity(client):
    """`service` 是身份判据，不是装饰——缺了它前端无法分辨陌生进程。"""
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "jobws"


def test_health_reports_real_version(client):
    """版本要能读出来（来自 web/electron/package.json），不是占位符。"""
    body = client.get("/api/health").json()
    version = body.get("version")
    assert version and version != "0.0.0-dev", "版本应来自 package.json，实际 %r" % version
    assert version[0].isdigit(), "版本应形如 26.10.0，实际 %r" % version


def test_health_does_not_leak_data_root(client):
    """刻意**不**返回数据根：ADR `port-identity` 规定复用的后端用它自己的数据根，
    把数据根做成拒绝条件会让「dev 后端 + 桌面壳」的复用失效。"""
    body = client.get("/api/health").json()
    joined = " ".join(str(v) for v in body.values()).lower()
    for marker in ("job-workbench", "data_root", "dataroot", "c:\\", "/home/", "workspace"):
        assert marker not in joined, "健康响应不应带数据根线索，命中 %r" % marker
