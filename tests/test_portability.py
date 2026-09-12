# -*- coding: utf-8 -*-
"""便携性判定（B4 / #4）——此前零测试。

钉住的是「打包后用户数据落进安装目录」那个判定缺陷：NSIS 安装版落在
`%LOCALAPPDATA%\\Programs`，目录**可写**，所以「可写即便携」这条老规则在
打包形态下会把数据写进安装目录，卸载时被连带删除。现在的规则是：打包形态
必须认 `portable.txt` 标记，光可写不够。

另有一条容易被顺手改坏：快照目录有意**不**跟随便携模式——备份跟源数据
同盘同目录等于没备份。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

import pathres  # noqa: E402


@pytest.fixture()
def app_root(tmp_path):
    """一个「应用根」：personal/ 存在且可写（NSIS 安装目录也是这个形态）。"""
    d = tmp_path / "app"
    (d / "personal").mkdir(parents=True)
    return d


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    """把系统用户数据目录指到临时目录，避免读到开发机上的真实目录。"""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)


def _freeze(monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def test_env_dir_has_highest_priority(app_root, monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    assert pathres.resolve_workspace_root(str(app_root)) == (
        os.path.abspath(str(elsewhere)), "env")


def test_unfrozen_keeps_historical_behaviour(app_root, monkeypatch):
    """解包形态维持历史行为：可写即便携，数据在仓库根 personal/。"""
    _freeze(monkeypatch, False)
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "portable")


def test_frozen_without_marker_never_stays_in_app_root(app_root, monkeypatch):
    """打包 + 无标记 → 一律走系统用户目录，哪怕应用根可写。"""
    _freeze(monkeypatch, True)
    data_root, mode = pathres.resolve_workspace_root(str(app_root))
    assert mode == "userdata"
    assert data_root != str(app_root)


def test_frozen_with_marker_is_portable(app_root, monkeypatch):
    _freeze(monkeypatch, True)
    (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "portable")


def test_snapshots_stay_outside_the_data_root(app_root, monkeypatch):
    """快照不跟随便携模式：放在 exe 旁边就是同盘同目录，那不算备份。"""
    _freeze(monkeypatch, True)
    (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    data_root, mode = pathres.resolve_workspace_root(str(app_root))
    assert mode == "portable"
    snap = os.path.abspath(pathres.snapshot_root())
    data = os.path.abspath(data_root)
    assert snap != data
    # 带分隔符再比前缀：否则 `...\app` 会被 `...\appdata\...` 误判命中
    assert not snap.startswith(data + os.sep)
