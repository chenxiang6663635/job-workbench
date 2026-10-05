# -*- coding: utf-8 -*-
"""数据根**三态**（A2）：ok / ambiguous / uninitialized / unavailable 的判据锁。

为什么单独一个文件：`tests/test_dataroot.py` 锁的是 A1 的**行为零变更**（四形态 ×
env、逐字对账）；本文件锁 A2 新增的状态计算——spec §四的表格逐行对应一条用例，
外加两条硬约束（性能上限、词表稳定）与一条"盲区"用例（MCP 看不到源码形态应用根）。

A2 的边界（与 A1 的"零变更"合起来看）：
- 解析链不变（env > 便携 > 用户目录）；persisted 只被**只读探测**，用来算状态与
  填充诊断字段，**不参与解析**（那是 A3 的事）；
- `unavailable`：persisted 存在但路径不可用即拒绝（spec 决策 4 的 fail-closed）——
  但仅当**生效来源确实是持久化选择**时；env 显式覆盖（决策 1 优先级更高）时降级为
  告警（`shadowed_by="env"`），state 按 env 根正常判定（决策 4 的边界）；
- `ambiguous` 优先于 `uninitialized`：机器上"有数据但不知读哪份"比"没数据"严重，
  不能被引导去初始化（spec §四两行的严重度对照）。

术语见 `docs/specs/2026-10-04-single-canonical-data-root.md` §四/§五。
"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "web", "backend"))

from jobws_core import dataroot, dataroot_probe, pathres  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    """系统用户数据目录与数据根 env 都指到临时目录——断言不落在开发机真实目录。"""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)


def _plant_selection(text):
    """在（已隔离的）用户数据目录里种一份 state/data-root.json，返回其路径。"""
    path = os.path.join(pathres.user_data_dir(), "state", "data-root.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _selection_path(root):
    return os.path.normpath(str(root))


def _write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _make_tracker_workspace(root, name="personal"):
    """用「05_投递追踪/tracker.csv」信号造一个像真实工作区的目录。"""
    ws = os.path.join(str(root), name)
    _write_file(os.path.join(ws, "05_投递追踪", "tracker.csv"), "id,公司\n1,示例\n")
    return ws


def _make_profile_workspace(root, name="personal"):
    """用「config/profile.md」信号造一个像真实工作区的目录。"""
    ws = os.path.join(str(root), name)
    _write_file(os.path.join(ws, "config", "profile.md"), "# 档案\n")
    return ws


# --- 词表 ---------------------------------------------------------------------

def test_state_constants_are_stable():
    """状态是跨端契约词表（spec §四）——值不许漂。"""
    assert dataroot.STATE_OK == "ok"
    assert dataroot.STATE_AMBIGUOUS == "ambiguous"
    assert dataroot.STATE_UNINITIALIZED == "uninitialized"
    assert dataroot.STATE_UNAVAILABLE == "unavailable"


# --- unavailable：persisted 指向不可用 ----------------------------------------

def test_unavailable_when_persisted_points_to_missing_path(tmp_path):
    """persisted 指向不存在的路径 → unavailable（spec 决策 4 的验收形态）。"""
    gone = tmp_path / "gone-root"
    _plant_selection(json.dumps({"format": 1, "data_root": str(gone)}))

    assert dataroot.persisted_unavailable() is True
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) == dataroot.STATE_UNAVAILABLE

    sel = dataroot.read_persisted_selection()
    assert sel["path"] == _selection_path(gone)
    assert sel["readable"] is True
    assert sel["shadowed_by"] is None

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert diag["state"] == dataroot.STATE_UNAVAILABLE
    assert diag["persisted_selection"]["path"] == _selection_path(gone)


def test_broken_persisted_shadowed_by_env_is_a_warning_not_a_lockout(tmp_path, monkeypatch):
    """env 显式覆盖时，失效的 persisted 降级为告警——不是把产品锁死。

    spec 决策 4 的边界（按 A2 实施反馈补写）：只有**生效来源确实是持久化选择**
    时才判 unavailable；env 给了非空绝对路径（决策 1 优先级更高）就以 env 为准，
    `shadowed_by="env"` 如实呈现遮蔽关系，state 按 env 根正常判定。
    """
    gone = tmp_path / "gone-root"
    _plant_selection(json.dumps({"data_root": str(gone)}))
    good = tmp_path / "good-root"
    _make_profile_workspace(good, "personal")
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(good))

    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) == dataroot.STATE_OK
    assert dataroot.persisted_unavailable() is False

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert diag["state"] == dataroot.STATE_OK
    assert diag["persisted_selection"]["path"] == _selection_path(gone)
    assert diag["persisted_selection"]["readable"] is True
    assert diag["persisted_selection"]["shadowed_by"] == "env"


def test_blank_env_does_not_shadow_broken_persisted(tmp_path, monkeypatch):
    """env 空串 / 纯空白视为未设置（决策 1）——不能靠它绕过 fail-closed。"""
    gone = tmp_path / "gone-root"
    _plant_selection(json.dumps({"data_root": str(gone)}))
    monkeypatch.setenv(pathres.ENV_DATA_DIR, "   ")

    assert dataroot.persisted_unavailable() is True
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) == dataroot.STATE_UNAVAILABLE


def test_bad_json_is_treated_as_unset_but_reported_unreadable(tmp_path):
    """坏 JSON 按「未设置」处理（不锁死用户），但诊断里 readable=false 要报出来。"""
    _plant_selection("{ 这不是 JSON")

    sel = dataroot.read_persisted_selection()
    assert sel["readable"] is False
    assert sel["path"] is None
    assert dataroot.persisted_unavailable() is False
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) != dataroot.STATE_UNAVAILABLE


def test_persisted_relative_path_is_rejected_like_bad_file(tmp_path):
    """相对路径不是合法的持久化选择（决策 1：只接受绝对路径）——按坏文件处理。"""
    _plant_selection(json.dumps({"data_root": "relative/data"}))

    sel = dataroot.read_persisted_selection()
    assert sel["readable"] is False
    assert dataroot.persisted_unavailable() is False


# --- ambiguous：多候选且都含真实工作区 ------------------------------------------

def test_ambiguous_when_two_candidates_have_workspaces(tmp_path):
    """env 根与 user_data 根各含一个工作区 → ambiguous，候选清单两条都可见。"""
    env_root = tmp_path / "env-root"
    _make_tracker_workspace(env_root, "ws-env")
    _make_profile_workspace(pathres.user_data_dir(), "ws-user")

    env = {pathres.ENV_DATA_DIR: str(env_root)}
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY, env=env) == dataroot.STATE_AMBIGUOUS

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY, env=env)
    assert diag["state"] == dataroot.STATE_AMBIGUOUS
    by_path = {c["path"]: c["has_workspace"] for c in diag["legacy_candidates"]}
    assert by_path == {
        _selection_path(env_root): True,
        _selection_path(pathres.user_data_dir()): True,
    }


def test_not_ambiguous_when_only_one_candidate_has_a_workspace(tmp_path):
    """只有一个候选含工作区不算歧义——单点数据指向明确。"""
    env_root = tmp_path / "env-root"
    _make_tracker_workspace(env_root, "ws-env")
    env = {pathres.ENV_DATA_DIR: str(env_root)}

    state = dataroot.detect_state(dataroot.FORM_MCP_ONLY, env=env)
    assert state != dataroot.STATE_AMBIGUOUS


def test_ambiguous_takes_precedence_over_uninitialized(tmp_path):
    """有数据（两处）而解析根没有工作区目录时：报 ambiguous，不报「正常首启」。"""
    env_root = tmp_path / "env-root"
    env_root.mkdir()                       # 解析根存在、可写，但没有 <root>/personal
    _make_tracker_workspace(env_root, "ws-env")
    _make_profile_workspace(pathres.user_data_dir(), "ws-user")

    env = {pathres.ENV_DATA_DIR: str(env_root)}
    assert dataroot.detect_state(
        dataroot.FORM_MCP_ONLY, env=env, workspace_name="personal") == dataroot.STATE_AMBIGUOUS


def test_candidates_are_deduped(tmp_path):
    """env 与 user_data 指同一处时只算一个候选——去重防「自己和自己歧义」。"""
    ud = pathres.user_data_dir()
    _make_profile_workspace(ud, "personal")

    env = {pathres.ENV_DATA_DIR: ud}
    diag = dataroot.describe(dataroot.FORM_MCP_ONLY, env=env)
    assert diag["state"] != dataroot.STATE_AMBIGUOUS
    assert [c["path"] for c in diag["legacy_candidates"]] == [_selection_path(ud)]


# --- uninitialized：根在、工作区未建 -------------------------------------------

def test_uninitialized_when_root_is_fresh_and_empty(tmp_path):
    """全新空根（存在但无工作区）→ uninitialized（正常首启，走初始化流程）。"""
    fresh = tmp_path / "fresh-root"
    fresh.mkdir()
    env = {pathres.ENV_DATA_DIR: str(fresh)}

    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY, env=env) == dataroot.STATE_UNINITIALIZED

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY, env=env)
    assert diag["state"] == dataroot.STATE_UNINITIALIZED
    assert diag["writable"] is True
    assert diag["persisted_selection"] is None
    assert diag["legacy_candidates"] == []


def test_uninitialized_when_root_does_not_exist_yet(tmp_path):
    """根还不存在（父目录可写）也算 uninitialized——首次运行不该报错。"""
    fresh = tmp_path / "not-created-yet"
    env = {pathres.ENV_DATA_DIR: str(fresh)}
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY, env=env) == dataroot.STATE_UNINITIALIZED


# --- ok ------------------------------------------------------------------------

def test_ok_when_resolved_root_contains_the_workspace(tmp_path):
    """解析根下工作区已建 → ok；候选清单里这条带 has_workspace=True。"""
    root = tmp_path / "root"
    _make_profile_workspace(root, "personal")
    env = {pathres.ENV_DATA_DIR: str(root)}

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY, env=env)
    assert diag["state"] == dataroot.STATE_OK
    assert diag["writable"] is True
    by_path = {c["path"]: c["has_workspace"] for c in diag["legacy_candidates"]}
    assert by_path[_selection_path(root)] is True
    # 「至少一个候选含工作区」时列出全部候选（含没有工作区的），供人判断
    assert _selection_path(pathres.user_data_dir()) in by_path


def test_ok_when_workspace_dir_exists_but_not_yet_initialized(tmp_path):
    """工作区目录在（内容未填）不算 uninitialized——目录存在即「已建」。

    与 API 的 ws 服务口径一致：`<root>/<ws>` 在就正常服务；缺 config/profile.md
    只是空工作区，不是「尚未建」。
    """
    root = tmp_path / "root"
    (root / "personal").mkdir(parents=True)
    env = {pathres.ENV_DATA_DIR: str(root)}
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY, env=env) == dataroot.STATE_OK


# --- 盲区：MCP 看不到源码形态应用根 --------------------------------------------

def test_mcp_only_cannot_see_the_source_app_root(tmp_path):
    """同一台机器：源码形态应把应用根算作候选；MCP-only 看不见它（spec §三盲区）。"""
    app_root = tmp_path / "app"
    _make_profile_workspace(app_root, "personal")

    source_diag = dataroot.describe(dataroot.FORM_SOURCE, str(app_root))
    assert _selection_path(app_root) in [
        c["path"] for c in source_diag["legacy_candidates"]]
    assert source_diag["state"] == dataroot.STATE_OK

    mcp_diag = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert mcp_diag["legacy_candidates"] == []
    assert mcp_diag["state"] != dataroot.STATE_AMBIGUOUS


# --- 性能铁律：有界扫描 --------------------------------------------------------

def test_candidate_scan_has_a_bounded_entry_limit(tmp_path, monkeypatch):
    """条目数超过上限 → 直接视为「有工作区」并提前退出（绝不深扫大目录）。"""
    monkeypatch.setattr(dataroot_probe, "SCAN_LIMIT", 2)
    cand = tmp_path / "big"
    for i in range(3):
        (cand / ("d%d" % i)).mkdir(parents=True)

    assert dataroot_probe.has_workspace(str(cand)) is True

    small = tmp_path / "small"
    for i in range(2):                     # 恰好不超过上限：正常逐条检查，无信号
        (small / ("d%d" % i)).mkdir(parents=True)
    assert dataroot_probe.has_workspace(str(small)) is False


def test_candidate_scan_finds_workspace_signals(tmp_path):
    """两个信号（profile.md / tracker.csv）都认——单层、不递归。"""
    cand = tmp_path / "cand"
    _make_tracker_workspace(cand, "a")
    _make_profile_workspace(cand, "b")
    assert dataroot_probe.has_workspace(str(cand)) is True
    assert dataroot_probe.has_workspace(str(tmp_path / "nope")) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
