# -*- coding: utf-8 -*-
"""数据根唯一解析器（A1）的行为锁：单入口 + 诊断对象 + **行为零变更**。

为什么单独钉（spec: docs/specs/2026-10-04-single-canonical-data-root.md，A1）：
A1 把「四端各自决定传不传应用根」收口成 `jobws_core.dataroot` 的四种 `form`，
并承诺对既有取值**零变更**。既有 `tests/test_portability.py` 锁 pathres 自身的
判定；这里锁新入口：四种 form × env 两态、应用根可写的两个分支、MCP-only 与
迁移前内联规则的逐字对账、`describe()` 的形状与词表（`source` 的 `legacy_*`
前缀、`form` 字段、state=="ok"）。

A1 刻意保持的现状（A2 才收紧，别把这些当 bug 修）：
- env 相对值被 `os.path.abspath()` 绑到 cwd；
- env 空串（含纯空白）视为未设置；
- 源码形态默认仍是「可写即便携＝仓库根」——B3 才降级为显式选择。
"""

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
    """系统用户数据目录与数据根 env 都指到临时目录——断言不落在开发机真实目录。"""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)


def _freeze(monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def _configure_form(monkeypatch, form, app_root):
    """按 form 摆出该形态的进程环境，返回 env 未设置时的预期 (path, form, source)。

    `source` 是 spec §五 的来源词表：A1 只可能产出 `legacy_portable` /
    `legacy_userdata`（`persisted` 留给 A3）；`form` 即传入形态、原样回显。
    """
    if form == dataroot.FORM_SOURCE:
        _freeze(monkeypatch, False)
        return (str(app_root), form, "legacy_portable")
    if form == dataroot.FORM_PORTABLE:
        _freeze(monkeypatch, True)
        (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
        return (str(app_root), form, "legacy_portable")
    if form == dataroot.FORM_PACKAGED:
        _freeze(monkeypatch, True)   # 无 portable.txt → userdata（哪怕应用根可写）
        return (pathres.user_data_dir(), form, "legacy_userdata")
    assert form == dataroot.FORM_MCP_ONLY
    return (pathres.user_data_dir(), form, "legacy_userdata")


def _call(form, app_root):
    """MCP-only 没有应用根可传——统一入口但不给不存在的参数。"""
    if form == dataroot.FORM_MCP_ONLY:
        return dataroot.resolve_data_root(form)
    return dataroot.resolve_data_root(form, str(app_root))


# --- 四种 form × env 两态（A1 的验收矩阵） -------------------------------------

@pytest.mark.parametrize("form", ALL_FORMS)
def test_env_value_wins_for_every_form(form, app_root, monkeypatch, tmp_path):
    """`JOBWS_DATA_DIR` 是最高优先级：任何形态下 path/form/source 都落在 env 值上。"""
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    res = _call(form, app_root)
    assert res.path == os.path.abspath(str(elsewhere))
    assert (res.form, res.source) == (form, "env")


@pytest.mark.parametrize("form", ALL_FORMS)
def test_blank_env_is_treated_as_unset(form, app_root, monkeypatch):
    """空串（含纯空白）视为未设置——保持现状 `.strip()` 语义。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, "   ")
    expected = _configure_form(monkeypatch, form, app_root)
    res = _call(form, app_root)
    assert (res.path, res.form, res.source) == expected


# --- FORM_SOURCE：可写即便携 / 不可写回退（Program Files 形态） -----------------

def test_source_form_writable_app_root_is_portable(app_root, monkeypatch):
    """源码形态（非 frozen、应用根可写）：便携＝仓库根（B3 前的现行默认）。"""
    _freeze(monkeypatch, False)
    res = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(app_root))
    assert (res.path, res.form, res.source) == (
        str(app_root), "source_form", "legacy_portable")


def test_source_form_unwritable_app_root_falls_back(tmp_path, monkeypatch):
    """应用根不可写 → 回退系统用户目录。两种摆法各钉一次。"""
    _freeze(monkeypatch, False)
    missing = tmp_path / "no-such-app"     # 指向不存在路径：父目录都不可写
    res = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(missing))
    assert (res.path, res.form, res.source) == (
        pathres.user_data_dir(), "source_form", "legacy_userdata")

    existed = tmp_path / "read-only-app"   # 目录在、被判定不可写（monkeypatch）
    (existed / "personal").mkdir(parents=True)
    monkeypatch.setattr(pathres, "_writable", lambda path: False)
    res2 = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(existed))
    assert (res2.path, res2.form, res2.source) == (
        pathres.user_data_dir(), "source_form", "legacy_userdata")


# --- FORM_MCP_ONLY：与迁移前 mcp/jobws_mcp/paths.py 的规则逐字对账 --------------

def test_mcp_only_with_env(monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == os.path.abspath(str(elsewhere))
    assert (res.form, res.source) == ("mcp_only", "env")


def test_mcp_only_without_env_falls_back_to_user_data_dir():
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == pathres.user_data_dir()
    assert (res.form, res.source) == ("mcp_only", "legacy_userdata")


def test_mcp_only_relative_env_binds_to_cwd(monkeypatch):
    """A1 保持现状：相对 env 值被 abspath 绑到 cwd（A2 才收紧为拒绝）。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, os.path.join("rel", "data"))
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == os.path.abspath(os.path.join("rel", "data"))


def test_mcp_only_honours_env_mapping(tmp_path):
    """env 参数可传纯字典：纯函数测试不必 monkeypatch 进程环境。"""
    elsewhere = tmp_path / "mapped"
    res = dataroot.resolve_data_root(
        dataroot.FORM_MCP_ONLY, env={pathres.ENV_DATA_DIR: str(elsewhere)})
    assert res.path == os.path.abspath(str(elsewhere))
    assert (res.form, res.source) == ("mcp_only", "env")


def test_mcp_only_replicates_legacy_inline_rule(monkeypatch, tmp_path):
    """逐字复刻迁移前的内联实现（含空串分支）：

        env_dir = os.environ.get(ENV_DATA_DIR, "").strip()
        path = os.path.abspath(env_dir) if env_dir else pathres.user_data_dir()
    """
    for value in (None, "", "   ", str(tmp_path / "d")):
        if value is None:
            monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
        else:
            monkeypatch.setenv(pathres.ENV_DATA_DIR, value)
        legacy = os.environ.get(pathres.ENV_DATA_DIR, "").strip()
        expected = os.path.abspath(legacy) if legacy else pathres.user_data_dir()
        assert dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).path == expected


# --- 形状与契约 ---------------------------------------------------------------

def test_form_constants_are_stable():
    """form 是跨端契约词表（spec §九 的四形态）——值不许漂。"""
    assert dataroot.FORM_SOURCE == "source_form"
    assert dataroot.FORM_PORTABLE == "portable"
    assert dataroot.FORM_PACKAGED == "packaged"
    assert dataroot.FORM_MCP_ONLY == "mcp_only"


def test_unknown_form_is_rejected():
    with pytest.raises(ValueError):
        dataroot.resolve_data_root("nope")


def test_resolution_unpacks_as_path_form_source(tmp_path, monkeypatch):
    """返回值是 (path, form, source) 三元形状——A1 的调用契约。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path / "d"))
    path, form, source = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert path == os.path.abspath(str(tmp_path / "d"))
    assert (form, source) == ("mcp_only", "env")


DIAGNOSTIC_FIELDS = ("path", "source", "form", "state", "writable", "root_id",
                     "schema_version", "persisted_selection", "legacy_candidates",
                     "migration_state")


def test_describe_fields_complete_and_typed(app_root, monkeypatch):
    """诊断对象字段齐备且类型正确；A1 未实现的部分是 None/[]/"idle"（不猜值）。"""
    _freeze(monkeypatch, False)
    d = dataroot.describe(dataroot.FORM_SOURCE, str(app_root))
    assert set(d) == set(DIAGNOSTIC_FIELDS)
    assert isinstance(d["path"], str) and d["path"] == str(app_root)
    assert d["source"] in ("env", "legacy_portable", "legacy_userdata")
    assert d["source"] == "legacy_portable"        # 非 frozen、应用根可写 → 便携
    assert d["form"] == "source_form"              # 传入形态原样回显
    assert d["state"] == "ok"
    assert d["writable"] is True
    assert d["root_id"] is None
    assert d["schema_version"] is None
    assert d["persisted_selection"] is None
    assert d["legacy_candidates"] == []
    assert d["migration_state"] == "idle"


def test_describe_writable_uses_pathres_semantics(monkeypatch, tmp_path):
    """writable：存在测自身、不存在测父目录（与 pathres._writable 同语义）。"""
    existing = tmp_path / "data"
    existing.mkdir()
    ok = dataroot.describe(dataroot.FORM_MCP_ONLY,
                           env={pathres.ENV_DATA_DIR: str(existing)})
    assert ok["writable"] is True

    missing = tmp_path / "gone" / "child"     # 父目录也不存在 → 不可写
    bad = dataroot.describe(dataroot.FORM_MCP_ONLY,
                            env={pathres.ENV_DATA_DIR: str(missing)})
    assert bad["path"] == os.path.abspath(str(missing))
    assert bad["writable"] is False

    fresh = tmp_path / "fresh-root"           # 自身不存在、父目录存在且可写 → 可写
    new = dataroot.describe(dataroot.FORM_MCP_ONLY,
                            env={pathres.ENV_DATA_DIR: str(fresh)})
    assert new["writable"] is True


def test_describe_env_source_is_visible(monkeypatch, tmp_path):
    """env 生效必须可见（决策 1：env 遮蔽 persisted 时要能诊断）——source 报 env、
    form 报调用形态（mcp_only）。"""
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    d = dataroot.describe(dataroot.FORM_MCP_ONLY)
    assert d["source"] == "env" and d["form"] == "mcp_only"
    assert d["path"] == os.path.abspath(str(elsewhere))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
