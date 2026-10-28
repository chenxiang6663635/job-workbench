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

def test_health_echoes_instance_id_from_env(monkeypatch, client):
    """后端必须**回显** JOBWS_INSTANCE_ID —— 跨语言链路的中间一段。

    完整链路：Electron 生成 → 经 env 注入子进程 → 后端放进 /api/health →
    Electron 校验。JS 侧测的是**假响应**（`backend_identity.test.js`），
    所以「真后端会不会回显」此前没有任何断言（2026-10-28 独立审查指出）。
    """
    monkeypatch.setenv("JOBWS_INSTANCE_ID", "deadbeef01")
    body = client.get("/api/health").json()
    assert body.get("instance_id") == "deadbeef01"


def test_health_instance_id_is_empty_when_not_injected(monkeypatch, client):
    """没注入时是**空串**，不是缺字段。

    消费方据此区分「受控实例」与「手工 `uvicorn main:app` 起的」——后者不该被
    误认成「壳拉起的那个」。空串也让字段始终存在，避免消费方写 `if key in body`
    这类容易写错的判断。
    """
    monkeypatch.delenv("JOBWS_INSTANCE_ID", raising=False)
    body = client.get("/api/health").json()
    assert body.get("instance_id") == ""
