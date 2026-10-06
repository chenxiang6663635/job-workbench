# -*- coding: utf-8 -*-
"""数据根控制面路由（A3）：`GET/POST/DELETE /api/system/data-root`。

为什么单独一个文件：`tests/test_data_root_guard.py` 锁的是 A2 的守卫（数据
端点被 fail-closed）；这里锁 A3 的**补救通道**——控制面路由必须在三态下都
可用（spec 决策 4），且**不得依赖 `workspace_dir`**（失效态里工作区解析本身
可能没有意义）。路由实现与呈现分工见 `web/backend/routers/data_root.py`。
"""

import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

import deps  # noqa: E402
from jobws_core import pathres  # noqa: E402

FIELDS = {"path", "source", "form", "state", "writable", "root_id",
          "schema_version", "persisted_selection", "legacy_candidates",
          "migration_state"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / "personal").mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入）
    return TestClient(main.app)


def _selection_path():
    return os.path.join(pathres.user_data_dir(), "state", "data-root.json")


def _plant_selection(text):
    path = _selection_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _get(client):
    res = client.get("/api/system/data-root")
    assert res.status_code == 200, res.text
    return res.json()


def _post(client, path):
    return client.post("/api/system/data-root", json={"path": str(path)})


# --- 读 ------------------------------------------------------------------------

def test_get_returns_diagnostic_without_workspace(client):
    """不带 `ws` 也能工作：控制面不依赖 workspace_dir（三态可用的前提）。"""
    data = _get(client)
    assert set(data) == FIELDS, sorted(set(data) ^ FIELDS)
    assert data["source"] in ("env", "persisted", "legacy_portable", "legacy_userdata")


# --- 设置 ----------------------------------------------------------------------

def test_post_sets_selection_and_get_reads_it_back(client, tmp_path):
    root = tmp_path / "data"
    root.mkdir()

    res = _post(client, root)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["source"] == "persisted"
    assert data["path"] == str(root)
    assert data["root_id"]

    assert os.path.isfile(_selection_path())
    with io.open(_selection_path(), "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["data_root"] == str(root)
    assert doc["selected_by"] == "user"

    assert _get(client)["path"] == str(root)


def test_post_rejects_relative_path(client):
    res = _post(client, os.path.join("rel", "x"))
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "sys.dataRootInvalidPath"
    assert not os.path.exists(_selection_path()), "非法输入不该落盘"


def test_post_rejects_blank_path(client):
    res = client.post("/api/system/data-root", json={"path": "   "})
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "sys.dataRootInvalidPath"


# --- 清除 ----------------------------------------------------------------------

def test_delete_clears_and_is_idempotent(client, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    _post(client, root)

    res = client.delete("/api/system/data-root")
    assert res.status_code == 200, res.text
    assert not os.path.exists(_selection_path())
    assert res.json()["source"] != "persisted"

    res = client.delete("/api/system/data-root")
    assert res.status_code == 200, res.text


# --- 补救通道：失效态下三条路由都可用 ------------------------------------------

def test_all_routes_work_while_unavailable(client, tmp_path):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    data = _get(client)                      # 读：如实报失效
    assert data["state"] == "unavailable"

    good = tmp_path / "good"
    good.mkdir()
    res = _post(client, good)                # 重选：可用
    assert res.status_code == 200, res.text
    assert _get(client)["state"] != "unavailable"

    res = client.delete("/api/system/data-root")   # 清除：可用
    assert res.status_code == 200, res.text
    assert _get(client)["source"] != "persisted"


# --- 迁移事务（B2）：preview → apply（plan_token 复核）→ resume / rollback --------

@pytest.fixture()
def mig_client(tmp_path, monkeypatch):
    """与 A3 的 client 同款隔离，但数据根收进 `tmp_path/root`——迁移目标
    不能落在源内部（preflight 的 usage 判定），必须给它留出兄弟位置。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path / "root"))
    (tmp_path / "root" / "personal").mkdir(parents=True)

    import main  # noqa: E402  （在 ROOT 被改写之后导入）
    return TestClient(main.app)


def _mk_ws(root):
    """给数据根放一个最小工作区（迁移要有东西可搬）。"""
    ws = os.path.join(str(root), "personal")
    os.makedirs(os.path.join(ws, "config"), exist_ok=True)
    with io.open(os.path.join(ws, "config", "profile.md"), "w",
                 encoding="utf-8", newline="\n") as fh:
        fh.write("# 档案\n")
    return ws


def _preview(client, target):
    res = client.post("/api/system/data-root/migrate/preview",
                      json={"target": str(target)})
    assert res.status_code == 200, res.text
    return res.json()


def test_migrate_preview_is_read_only(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    view = _preview(client, tmp_path / "out")
    assert view["ok"] is True and view["reasons"] == [], view
    assert view["entries"] == 1 and view["plan_token"]
    assert not os.path.exists(_selection_path()), "预览不该写选择文件"
    assert not os.path.exists(str(tmp_path / "out")), "预览不该建目标目录"


def test_migrate_apply_completes_with_token(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    target = tmp_path / "out"
    view = _preview(client, target)

    res = client.post("/api/system/data-root/migrate/apply",
                      json={"target": str(target), "plan_token": view["plan_token"]})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done", res.text
    assert os.path.isfile(os.path.join(str(target), "personal", "config", "profile.md"))
    assert _get(client)["path"] == str(target)


def test_migrate_apply_rejects_stale_token(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    target = tmp_path / "out"
    view = _preview(client, target)
    with io.open(os.path.join(deps.ROOT, "personal", "extra.md"), "w",
                 encoding="utf-8", newline="\n") as fh:
        fh.write("预览之后才写入\n")

    res = client.post("/api/system/data-root/migrate/apply",
                      json={"target": str(target), "plan_token": view["plan_token"]})
    assert res.status_code == 409, res.text
    assert res.json()["error_code"] == "sys.dataRootPlanStale", res.text


def test_migrate_apply_blocked_returns_409(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    target = os.path.join(deps.ROOT, "personal", "inner")   # 目标落在源内部

    res = client.post("/api/system/data-root/migrate/apply",
                      json={"target": target, "plan_token": "whatever"})
    assert res.status_code == 409, res.text
    assert res.json()["error_code"] == "sys.dataRootMigrateBlocked", res.text


def test_migrate_apply_is_idempotent_when_already_current(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    target = tmp_path / "out"
    assert _post(client, target).status_code == 200          # 选择已指向目标

    res = client.post("/api/system/data-root/migrate/apply",
                      json={"target": str(target), "plan_token": ""})
    assert res.status_code == 200, res.text
    assert res.json() == {"status": "noop", "already_current": True}, res.text


def test_migrate_resume_and_rollback_without_transaction(mig_client):
    client = mig_client
    res = client.post("/api/system/data-root/migrate/resume", json={"apply": False})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "nothing", res.text
    res = client.post("/api/system/data-root/migrate/rollback", json={"apply": True})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "nothing", res.text


def test_migrate_rollback_after_apply_points_back(mig_client, tmp_path):
    client = mig_client
    _mk_ws(deps.ROOT)
    target = tmp_path / "out"
    view = _preview(client, target)
    client.post("/api/system/data-root/migrate/apply",
                json={"target": str(target), "plan_token": view["plan_token"]})

    res = client.post("/api/system/data-root/migrate/rollback", json={"apply": True})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rolled-back", res.text
    assert _get(client)["path"] == str(deps.ROOT)
    assert os.path.isdir(os.path.join(str(target), "personal")), "回滚不删目标"


def test_migrate_works_while_unavailable(mig_client, tmp_path):
    """三态可用（spec 决策 4/5）：失效态里预览 / 续跑照样是明路。"""
    client = mig_client
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))
    assert _get(client)["state"] == "unavailable"

    view = _preview(client, tmp_path / "out")   # 源根失效 → 计划如实报 blocked
    assert view["ok"] is False
    assert any("源工作区不存在" in item["message"] for item in view["reasons"])

    res = client.post("/api/system/data-root/migrate/resume", json={"apply": False})
    assert res.status_code == 200, res.text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
