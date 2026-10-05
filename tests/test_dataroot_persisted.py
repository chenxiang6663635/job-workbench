# -*- coding: utf-8 -*-
"""持久化选择（A3）的行为锁：解析接线 / 原子写 / 根标记 / 失效态补救。

为什么单独一个文件：
- `tests/test_dataroot.py` 锁 A1 的「行为零变更」——其中「相对 env 绑 cwd」的
  旧边界已随 A3 收紧为**拒绝**（spec 决策 1），该文件同步订正；
- `tests/test_dataroot_states.py` 锁 A2 的三态判据；
- 本文件锁 A3：`resolve_data_root` 接入 persisted（**env > persisted > legacy，
  四种 form 一致**）、`state/data-root.json` 的写 / 清（原子、幂等、root_id
  身份随数据走）、根标记 `.jobws-root.json` 与 `describe().root_id` 的来源
  优先级、以及「失效态下仍是补救通道」的**域层一半**（CLI / API 面见
  `test_cli_data_root.py` / `test_data_root_api.py`）。

行为影响（spec 决策 1 的目的，如实记录）：A3 之前四端都不读 persisted，
选择文件只被只读探测；此后三种带应用根的 form 与 FORM_MCP_ONLY 的解析都会
优先落在它上——这是「换机 / 换目录不再静默漂移」的落地。
"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "web", "backend"))

from jobws_core import dataroot, pathres  # noqa: E402

ALL_FORMS = (dataroot.FORM_SOURCE, dataroot.FORM_PORTABLE,
             dataroot.FORM_PACKAGED, dataroot.FORM_MCP_ONLY)


@pytest.fixture()
def app_root(tmp_path):
    """一个「应用根」：personal/ 存在且可写（仓库根 / 便携目录都是这个形态）。"""
    d = tmp_path / "app"
    (d / "personal").mkdir(parents=True)
    return d


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    """系统用户数据目录、数据根 env、工作区 env 都指到临时值。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)


def _freeze(monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def _configure_form(monkeypatch, form, app_root):
    """按 form 摆出该形态的进程环境；返回**无 env / 无 persisted** 时的预期。"""
    if form == dataroot.FORM_SOURCE:
        _freeze(monkeypatch, False)
        return (str(app_root), "legacy_portable")
    if form == dataroot.FORM_PORTABLE:
        _freeze(monkeypatch, True)
        (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
        return (str(app_root), "legacy_portable")
    if form == dataroot.FORM_PACKAGED:
        _freeze(monkeypatch, True)   # 无 portable.txt → userdata
        return (pathres.user_data_dir(), "legacy_userdata")
    assert form == dataroot.FORM_MCP_ONLY
    return (pathres.user_data_dir(), "legacy_userdata")


def _call(form, app_root):
    """MCP-only 没有应用根可传——统一入口但不给不存在的参数。"""
    if form == dataroot.FORM_MCP_ONLY:
        return dataroot.resolve_data_root(form)
    return dataroot.resolve_data_root(form, str(app_root))


def _selection_path():
    return os.path.join(pathres.user_data_dir(), "state", "data-root.json")


def _plant_selection(text):
    """在（已隔离的）用户数据目录里种一份 state/data-root.json。"""
    path = _selection_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _plant_marker(root, root_id):
    with io.open(os.path.join(str(root), ".jobws-root.json"), "w",
                 encoding="utf-8") as fh:
        fh.write(json.dumps({"format": 1, "root_id": root_id,
                             "created_at": "2026-10-05T00:00:00",
                             "schema_version": None}))


# --- 优先级矩阵：四种 form × （env 有/无）×（persisted 有/无） ------------------

@pytest.mark.parametrize("form", ALL_FORMS)
def test_defaults_unchanged_without_env_and_persisted(form, app_root, monkeypatch):
    """A3 硬约束：无 env、无 persisted 时四形态默认值一个不改（B3 才动默认）。"""
    expected = _configure_form(monkeypatch, form, app_root)
    res = _call(form, app_root)
    assert (res.path, res.form, res.source) == (expected[0], form, expected[1])


@pytest.mark.parametrize("form", ALL_FORMS)
def test_persisted_is_used_when_env_is_absent(form, app_root, monkeypatch, tmp_path):
    """env 缺位时 persisted 高于 legacy——四种 form 一致（spec §九「仅 persisted」列）。"""
    _configure_form(monkeypatch, form, app_root)
    sel_root = tmp_path / "sel-root"
    _plant_selection(json.dumps({"format": 1, "data_root": str(sel_root),
                                 "root_id": "sel-id"}))
    res = _call(form, app_root)
    assert (res.path, res.form, res.source) == (str(sel_root), form, "persisted")


@pytest.mark.parametrize("form", ALL_FORMS)
def test_env_still_wins_and_shadows_persisted(form, app_root, monkeypatch, tmp_path):
    """env > persisted：env 生效时失效的旧选择降级为告警（shadowed_by="env"）。"""
    _configure_form(monkeypatch, form, app_root)
    env_root = tmp_path / "env-root"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(env_root))
    _plant_selection(json.dumps({"format": 1, "data_root": str(tmp_path / "sel-root"),
                                 "root_id": "sel-id"}))
    res = _call(form, app_root)
    assert (res.path, res.source) == (str(env_root), "env")

    sel = dataroot.read_persisted_selection()
    assert sel["readable"] is True and sel["shadowed_by"] == "env"


def test_stale_persisted_resolves_to_it_and_state_is_unavailable(tmp_path):
    """失效选择：解析**不静默回落**（path/source 都指向它），state=unavailable。"""
    _plant_selection(json.dumps({"format": 1, "data_root": str(tmp_path / "gone"),
                                 "root_id": "sel-id"}))
    for form in ALL_FORMS:
        res = _call(form, tmp_path / "app")
        assert (res.path, res.source) == (str(tmp_path / "gone"), "persisted")

    diag = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert diag["state"] == dataroot.STATE_UNAVAILABLE
    assert diag["source"] == "persisted"
    assert diag["persisted_selection"]["readable"] is True


# --- 写入：schema / 原子 / root_id 身份 ----------------------------------------

def test_write_creates_parseable_selection_without_temp_residue(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    doc = dataroot.write_persisted_selection(str(root))

    path = _selection_path()
    assert os.path.isfile(path)
    with io.open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert set(data) == {"format", "data_root", "root_id", "selected_at",
                         "selected_by", "migration_state", "schema_version"}
    assert data["format"] == 1
    assert data["data_root"] == str(root)
    assert data["selected_by"] == "cli"
    assert data["migration_state"] == "idle"
    assert data["selected_at"]
    assert data["root_id"] == doc["root_id"]

    # 原子写不留临时文件（同目录 tempfile + os.replace）
    assert os.listdir(os.path.dirname(path)) == ["data-root.json"]


def test_write_records_selected_by(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    dataroot.write_persisted_selection(str(root), source="user")
    with io.open(_selection_path(), "r", encoding="utf-8") as fh:
        assert json.load(fh)["selected_by"] == "user"

    with pytest.raises(ValueError):
        dataroot.write_persisted_selection(str(root), source="not-a-source")


def test_blank_or_relative_selection_path_is_rejected(tmp_path):
    """只接受绝对路径（spec 决策 1）；相对值 fail-fast，不落盘。"""
    for bad in ("", "   ", os.path.join("rel", "data"), "C:relative"):
        with pytest.raises(ValueError):
            dataroot.write_persisted_selection(bad)
    assert not os.path.exists(_selection_path())


def test_same_root_keeps_root_id(tmp_path):
    """改选同一根不换身份——标记与选择文件都保 root_id。"""
    root = tmp_path / "data"
    root.mkdir()
    first = dataroot.write_persisted_selection(str(root))
    second = dataroot.write_persisted_selection(str(root))
    assert second["root_id"] == first["root_id"]
    assert dataroot.read_root_marker(str(root))["root_id"] == first["root_id"]


def test_switching_root_gets_new_root_id(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    id_a = dataroot.write_persisted_selection(str(a))["root_id"]
    id_b = dataroot.write_persisted_selection(str(b))["root_id"]
    assert id_a != id_b


def test_existing_selection_root_id_is_reused_when_root_has_no_marker(tmp_path):
    """选择文件里已有身份（根还没标记）时沿用，不无谓换 id。"""
    root = tmp_path / "data"
    root.mkdir()
    _plant_selection(json.dumps({"format": 1, "data_root": str(root),
                                 "root_id": "fixed-id"}))
    assert dataroot.write_persisted_selection(str(root))["root_id"] == "fixed-id"


# --- 清除：幂等 ----------------------------------------------------------------

def test_clear_is_idempotent(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    dataroot.write_persisted_selection(str(root))

    assert dataroot.clear_persisted_selection() is True    # 删除了一份
    assert not os.path.exists(_selection_path())
    assert dataroot.clear_persisted_selection() is False   # 已不存在：仍是成功
    assert dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).source == "legacy_userdata"


# --- 根标记：幂等、不含路径、describe 的 root_id 优先级 -------------------------

def test_root_marker_is_idempotent_and_pathless(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    first = dataroot.ensure_root_marker(str(root))
    again = dataroot.ensure_root_marker(str(root))
    assert first["root_id"] == again["root_id"]

    with io.open(os.path.join(str(root), ".jobws-root.json"),
                 "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert set(data) == {"format", "root_id", "created_at", "schema_version"}
    assert data["root_id"] == first["root_id"]


def test_describe_root_id_prefers_marker_over_selection(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    _plant_selection(json.dumps({"format": 1, "data_root": str(root),
                                 "root_id": "from-selection"}))
    assert dataroot.describe(dataroot.FORM_MCP_ONLY)["root_id"] == "from-selection"

    _plant_marker(root, "from-marker")
    assert dataroot.describe(dataroot.FORM_MCP_ONLY)["root_id"] == "from-marker"


def test_describe_reports_real_selection_and_root_id(tmp_path):
    root = tmp_path / "data"
    (root / "personal").mkdir(parents=True)
    doc = dataroot.write_persisted_selection(str(root))
    diag = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert diag["source"] == "persisted"
    assert diag["path"] == str(root)
    assert diag["persisted_selection"] == {
        "path": str(root), "readable": True, "shadowed_by": None}
    assert diag["root_id"] == doc["root_id"]
    assert diag["state"] == dataroot.STATE_OK


# --- 相对 env：四种 form 一致拒绝（spec 决策 1） -------------------------------

@pytest.mark.parametrize("form", ALL_FORMS)
def test_relative_env_is_rejected_for_every_form(form, app_root, monkeypatch):
    _configure_form(monkeypatch, form, app_root)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, os.path.join("rel", "data"))
    with pytest.raises(ValueError):
        _call(form, app_root)


# --- 补救通道（域层）：失效态下写 / 清仍可用 -----------------------------------

def test_rescue_write_and_clear_work_while_stale(tmp_path):
    _plant_selection(json.dumps({"format": 1, "data_root": str(tmp_path / "gone"),
                                 "root_id": "sel-id"}))
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) == dataroot.STATE_UNAVAILABLE

    # 明路一：重选数据根
    good = tmp_path / "good"
    good.mkdir()
    dataroot.write_persisted_selection(str(good))
    assert dataroot.detect_state(dataroot.FORM_MCP_ONLY) != dataroot.STATE_UNAVAILABLE

    # 明路二：清除选择（回到 legacy 默认）
    assert dataroot.clear_persisted_selection() is True
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.source == "legacy_userdata"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
