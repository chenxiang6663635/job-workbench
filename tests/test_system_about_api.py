# -*- coding: utf-8 -*-
"""「关于」区块：版本 / 平台字段与 `_app_version()` 的三个来源分支。

为什么单独钉这一块：它是使用者唯一能「自我核对装的是哪一版」的入口，取值有三
条路径（打包注入 → package.json → 空串）。**把 `_app_version` 改成恒返回 ""、把
platform 写死，全仓其它测试照样全绿**——第二轨审查 MAJOR-12 指出的正是这种
「单人仓库唯一防线失效」的情形。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把应用根与环境都隔离到 tmp_path：避免读到开发机上的真实版本与快照目录。"""
    monkeypatch.delenv("JOBWS_APP_VERSION", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （ROOT 改写后再导入，避免读到真实仓库根）
    return TestClient(main.app)


def _system():
    from routers import system
    return system


def test_version_prefers_injected_env(client, monkeypatch):
    """打包版：主进程注入 JOBWS_APP_VERSION 时优先用它（不再回退读 package.json）。"""
    monkeypatch.setenv("JOBWS_APP_VERSION", "26.9.15")
    assert _system()._app_version() == "26.9.15"


def test_version_falls_back_to_package_json(tmp_path, client):
    """开发模式：回退读 `<ROOT>/web/electron/package.json` 的 version。"""
    pkg_dir = tmp_path / "web" / "electron"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "package.json").write_text('{"version": "26.9.15"}', encoding="utf-8")
    assert _system()._app_version() == "26.9.15"


def test_version_is_empty_when_nothing_available(client):
    """两条路都不可用 → 空串（界面显示「未知」），不编造版本。"""
    assert _system()._app_version() == ""


def test_paths_reports_version_and_platform(client, monkeypatch):
    """API 字段：appVersion 跟随注入；platform 取 sys.platform（不是写死的字符串）。"""
    monkeypatch.setenv("JOBWS_APP_VERSION", "26.9.15")
    res = client.get("/api/system/paths", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["appVersion"] == "26.9.15"
    assert data["platform"] == sys.platform
    # 死字段已删（全仓无 JOBWS_BUILD_DATE 的生产方，第二轨 MAJOR-2）
    assert "buildDate" not in data
