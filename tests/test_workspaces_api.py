# -*- coding: utf-8 -*-
"""工作区新建 API（两段式）的回归。

钉三件事：

1. **预览不落盘**——`/preview` 之后目标目录必须**不存在**（不是"存在但为空"）；
2. **apply 才创建**，且回传目标路径供前端展示；
3. **越界与非法名一律拒绝**：新建是"在可写数据根下加一个目录"，不是"往任意位置写"。

连错误码一起断言：前端要靠 `error_code` 渲染本地化文案，也要靠 HTTP 状态码区分
"预览失败"与"没有内容"——这个项目里"静默错位比报错危险"是写进 deps.py 的老规矩。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import approval  # noqa: E402
import deps  # noqa: E402
import main as backend_main  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """数据根指向 tmp：新建的工作区都落在里面，且令牌目录也隔离。"""
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval._shell, "_store_dir", lambda: str(store))
    with TestClient(backend_main.app) as test_client:
        yield test_client


def test_domains_lists_plugins(client):
    body = client.get("/api/workspaces/domains").json()

    ids = [item["id"] for item in body["items"]]
    assert "software-backend" in ids and "hvac-cooling" in ids
    assert body["demoDefault"] == "software-backend"


def test_preview_does_not_create_then_apply_creates(client, tmp_path):
    target = tmp_path / "new-ws"

    preview = client.post("/api/workspaces/preview",
                          json={"name": "new-ws", "demo": True})

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["token"] and body["diff"]
    assert body["path"] == str(target)
    assert not target.exists(), "预览阶段连目标目录都不该建"

    applied = client.post("/api/workspaces/apply", json={"token": body["token"]})

    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["created"] > 0
    assert result["path"] == str(target)
    assert (target / "05_投递追踪" / "tracker.csv").is_file()
    assert (target / "AGENTS.md").is_file()


def test_apply_rejects_replayed_token(client):
    token = client.post("/api/workspaces/preview",
                        json={"name": "ws-a"}).json()["token"]
    first = client.post("/api/workspaces/apply", json={"token": token})
    assert first.status_code == 200, first.text

    again = client.post("/api/workspaces/apply", json={"token": token})

    assert again.status_code == 422
    assert again.json()["error_code"] == "ws.tokenInvalid"


# 后三类对应"会被系统悄悄改写、从而与既有目录静默合并"的输入：
# `"ws "` / `"ws."` 在 Windows 上就是 `"ws"`，保留设备名则根本建不出来。
@pytest.mark.parametrize("name", [
    "", "..", ".hidden", "a/b", "a\\b", "../evil",
    "ws ", " ws", "ws.",
    "CON", "nul", "COM1", "LPT9",
])
def test_illegal_names_are_rejected(client, name, tmp_path):
    resp = client.post("/api/workspaces/preview", json={"name": name})

    assert resp.status_code == 422
    assert resp.json()["error_code"] in ("ws.nameRequired", "ws.nameInvalid")
    # 一个副作用都不能有：数据根里除了令牌目录，不该多出任何东西（用集合比较，
    # 不比顺序——顺序会随平台与文件系统变）
    assert {p.name for p in tmp_path.iterdir()} == {"tokens"}


def test_conflict_after_preview_is_refused(client, tmp_path):
    """预览之后目标被填了内容 → apply 返回 409（而不是把东西盖掉）。"""
    token = client.post("/api/workspaces/preview",
                        json={"name": "ws-b"}).json()["token"]
    target = tmp_path / "ws-b"
    target.mkdir()
    (target / "我的数据.txt").write_text("别动我", encoding="utf-8")

    resp = client.post("/api/workspaces/apply", json={"token": token})

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "ws.initConflict"
    assert (target / "我的数据.txt").read_text(encoding="utf-8") == "别动我"
