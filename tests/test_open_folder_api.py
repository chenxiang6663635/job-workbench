# -*- coding: utf-8 -*-
"""数据位置：open-folder 的预设键与「数据根」键（设置页「数据位置」卡片用）。

设置页要显示数据根（便携模式 = 应用旁；打包装到不可写位置 = 系统用户目录）
并能一键打开。本文件钉住：
1. `_open_target` 纯函数把预设键解析成正确路径——直接单测，不拉起文件管理器；
2. 未知键被拒绝（400，sys.unknownTarget）——「任意目录打开器」这条边界不放松；
3. `/api/system/paths` 的 dataRoot / mode 字段与 pathres 的解析口径一致。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from apierror import ApiError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    # APPDATA 也要隔离：快照目录走系统用户目录，不隔离会读到开发机上的真实快照
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入，避免读到真实仓库根）
    return TestClient(main.app)


def _system():
    from routers import system
    return system


def test_workspace_key_resolves_to_the_workspace(tmp_path, client):
    ws = str(tmp_path / WS)
    assert _system()._open_target("workspace", ws) == ws


def test_snapshots_key_resolves_to_snapshot_dir(tmp_path, client):
    system = _system()
    ws = str(tmp_path / WS)
    assert system._open_target("snapshots", ws) == system._snapshot_dir(ws)


def test_data_root_key_resolves_to_data_root(tmp_path, client):
    assert _system()._open_target("dataRoot", "unused") == os.path.normpath(deps.data_root())


def test_unknown_key_is_rejected(client):
    with pytest.raises(ApiError) as exc:
        _system()._open_target("nope", "unused")
    assert exc.value.status_code == 400
    assert exc.value.code == "sys.unknownTarget"
    assert exc.value.params["target"] == "nope"


def test_api_rejects_unknown_key(client):
    res = client.post("/api/system/open-folder", params={"ws": WS},
                      json={"path": "nope"})
    assert res.status_code == 400
    data = res.json()
    assert data["error_code"] == "sys.unknownTarget"
    assert data["error_params"]["target"] == "nope"


def test_paths_reports_data_root_and_mode(tmp_path, client):
    """非打包、无 JOBWS_DATA_DIR、应用根可写 → 便携模式：数据根 == 应用根。"""
    res = client.get("/api/system/paths", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["dataRoot"] == os.path.normpath(str(tmp_path))
    assert data["mode"] == "portable"


def test_mode_falls_back_to_user_dir_when_env_points_elsewhere(tmp_path, client, monkeypatch):
    alt = tmp_path / "alt-root"
    monkeypatch.setenv("JOBWS_DATA_DIR", str(alt))
    res = client.get("/api/system/paths", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["dataRoot"] == os.path.normpath(str(alt))
    assert data["mode"] == "user"
