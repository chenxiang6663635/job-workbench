# -*- coding: utf-8 -*-
"""便携性判定与默认数据根（B3 重写——此前的「行为锁」被 spec 决策 6 **有意识地**更新）。

历史沿革（为什么这个文件改过两次语义）：
- B4 / #4：钉住「打包后用户数据落进安装目录」——NSIS 安装目录**可写**，
  「可写即便携」会把数据写进安装目录、卸载连带删除。当时给 frozen 形态加了
  `portable.txt` 门槛。
- **B3（本次，spec 决策 6）**：把门槛推广到**所有形态**——便携 = 显式标记，
  「可写」从来只是能力、不是选择；新装默认一律 `<user_data_dir>/data`
  （四端可共同计算，不依赖应用根）；旧默认位置**已有真实工作区**的原样保留
  （`legacy_portable` / `legacy_userdata`，不搬迁、不静默换根——搬家走
  `jobws data-root migrate`，必须经确认）。

另有一条容易被顺手改坏：快照目录有意**不**跟随便携模式——备份跟源数据
同盘同目录等于没备份。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

from jobws_core import pathres  # noqa: E402


def _plant_workspace(root):
    """摆一个「真实工作区」的信号（与 dataroot_probe.SIGNALS 同源的两个文件）。"""
    ws = os.path.join(str(root), "personal", "config")
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "profile.md"), "w", encoding="utf-8") as fh:
        fh.write("# 档案\n")


@pytest.fixture()
def app_root(tmp_path):
    """一个「应用根」：personal/ 骨架存在且可写（无信号 = 未初始化）。"""
    d = tmp_path / "app"
    (d / "personal").mkdir(parents=True)
    return d


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    """系统用户数据目录与数据根 env 都指到临时目录，避免读到开发机真实目录。"""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)


def _freeze(monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def test_env_dir_has_highest_priority(app_root, monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    assert pathres.resolve_workspace_root(str(app_root)) == (
        os.path.abspath(str(elsewhere)), "env")


# --- B3：新装默认 <user_data_dir>/data -------------------------------------------

def test_fresh_install_defaults_to_user_data_subdir(app_root, monkeypatch):
    """全新安装（无 env / 无标记 / 两处旧位置都无真实工作区）→ 新默认。"""
    _freeze(monkeypatch, False)
    data_root, mode = pathres.resolve_workspace_root(str(app_root))
    assert (data_root, mode) == (pathres.default_data_root(), "userdata")
    assert data_root == os.path.join(pathres.user_data_dir(), "data")


def test_fresh_install_default_is_form_agnostic(app_root, monkeypatch):
    """新默认不挑形态：frozen / 非 frozen 落同一个 `<user_data_dir>/data`。"""
    _freeze(monkeypatch, False)
    assert pathres.resolve_workspace_root(str(app_root))[0] == pathres.default_data_root()
    _freeze(monkeypatch, True)
    assert pathres.resolve_workspace_root(str(app_root))[0] == pathres.default_data_root()


def test_default_root_is_never_the_app_root(app_root, monkeypatch):
    """回归锁（B4/#4 的原始缺陷）：数据绝不因「可写」落进应用根。"""
    _freeze(monkeypatch, False)
    data_root, _ = pathres.resolve_workspace_root(str(app_root))
    assert data_root != str(app_root)


# --- B3：便携 = 显式标记（两种形态同一判据） --------------------------------------

def test_portable_marker_is_honoured_unfrozen(app_root, monkeypatch):
    """「便携降级为显式」：源码形态也要 portable.txt 才便携。"""
    _freeze(monkeypatch, False)
    (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "portable")


def test_frozen_with_marker_is_portable(app_root, monkeypatch):
    _freeze(monkeypatch, True)
    (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "portable")


def test_frozen_without_marker_never_stays_in_app_root(app_root, monkeypatch):
    """打包 + 无标记 → 一律不落应用根（哪怕它可写）。"""
    _freeze(monkeypatch, True)
    data_root, mode = pathres.resolve_workspace_root(str(app_root))
    assert mode == "userdata"
    assert data_root != str(app_root)


# --- B3：legacy 保留（旧默认位置已有真实工作区 → 原样继续） ------------------------

def test_legacy_workspace_in_app_root_is_kept(app_root, monkeypatch):
    """旧安装（源码形态，数据在仓库根）：原样保留，不静默换根。"""
    _freeze(monkeypatch, False)
    _plant_workspace(app_root)
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "legacy_portable")


def test_legacy_workspace_in_user_data_is_kept(app_root, monkeypatch):
    """旧安装（NSIS 形态，数据在系统用户目录）：同样保留。"""
    _freeze(monkeypatch, True)
    _plant_workspace(tmp_root(app_root))
    data_root, mode = pathres.resolve_workspace_root(str(app_root))
    assert (data_root, mode) == (pathres.user_data_dir(), "legacy_userdata")


def test_legacy_user_data_kept_even_without_app_root(tmp_path, monkeypatch):
    """MCP-only 形态的默认解析同样走 legacy 保留。"""
    _plant_workspace(tmp_root(None))
    assert pathres.resolve_default_root() == (pathres.user_data_dir(), "legacy_userdata")


def test_mcp_only_fresh_install_gets_the_new_default(tmp_path, monkeypatch):
    _freeze(monkeypatch, False)
    assert pathres.resolve_default_root() == (pathres.default_data_root(), "userdata")


def test_legacy_keep_honours_workspace_env(app_root, monkeypatch):
    """legacy 判据按 JOBWS_WORKSPACE 找旧数据（默认工作区名不是唯一形态）。"""
    _freeze(monkeypatch, False)
    ws = app_root / "side_quest"
    (ws / "05_投递追踪").mkdir(parents=True)
    (ws / "05_投递追踪" / "tracker.csv").write_text("id\n", encoding="utf-8")
    monkeypatch.setenv(pathres.ENV_WORKSPACE, "side_quest")
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "legacy_portable")


def test_app_root_legacy_wins_over_user_data_legacy(app_root, monkeypatch, tmp_path):
    """两处旧位置都有数据时保持历史优先级（应用根先）；歧义由诊断层报告。"""
    _freeze(monkeypatch, False)
    _plant_workspace(app_root)
    _plant_workspace(tmp_root(app_root))
    assert pathres.resolve_workspace_root(str(app_root)) == (str(app_root), "legacy_portable")


def test_bare_personal_skeleton_is_not_a_workspace(app_root, monkeypatch):
    """空骨架不算：personal/ 在但没有信号文件 → 走新默认（未初始化由三态报告）。"""
    _freeze(monkeypatch, False)
    assert pathres.resolve_workspace_root(str(app_root))[0] == pathres.default_data_root()


def tmp_root(_=None):
    """user_data_dir() 的便捷别名（测试里它已被隔离到 tmp）。"""
    return pathres.user_data_dir()


# --- 快照纪律（不跟随便携） ------------------------------------------------------

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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
