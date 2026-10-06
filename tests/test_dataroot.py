# -*- coding: utf-8 -*-
"""数据根唯一解析器（A1）的行为锁：单入口 + 诊断对象 + 词表。

为什么单独钉（spec: docs/specs/2026-10-04-single-canonical-data-root.md，A1）：
A1 把「四端各自决定传不传应用根」收口成 `jobws_core.dataroot` 的四种 `form`。
本文件经历两次**有意识的**契约更新（每处都注明依据，这不是漂移）：
- A3：env 相对值不再被 `os.path.abspath()` 绑到 cwd，而是按决策 1 **拒绝**；
- **B3：无 env、无 persisted 时的默认 = `<user_data_dir>/data`（决策 6）**；
  旧默认位置已有真实工作区的原样保留（`legacy_*`，不搬迁）；「非打包即便携」
  降级为显式 `portable.txt`（判定细节在 `pathres`，这里锁来源词表与形状）。
仍然不变的两条：
- env 空串（含纯空白）视为未设置；
- env 是任何形态下的最高优先级。
"""

import io
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
    """一个「应用根」：personal/ 骨架存在且可写（仓库根 / 便携目录都是这个形态）。"""
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
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)


def _freeze(monkeypatch, frozen):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def _plant_workspace(root):
    """摆一个「真实工作区」（与 dataroot_probe.SIGNALS 同源的两个信号文件）。"""
    ws = root / "personal" / "config"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "profile.md").write_text("# 档案\n", encoding="utf-8")


def _configure_form(monkeypatch, form, app_root):
    """按 form 摆出该形态的进程环境，返回 env 未设置时的预期 (path, form, source)。

    B3 语义（spec 决策 6 + §九目标矩阵）：夹具的应用根只有 personal/ **空骨架**
    （无信号文件 = 未初始化）→ 四种 form 的默认都是 `<user_data_dir>/data`、
    来源 `legacy_userdata`（矩阵里新默认就记这个词——「传统默认」层）。
    便携标记形态是例外：显式标记 → 应用根、`legacy_portable`。
    """
    if form == dataroot.FORM_SOURCE:
        _freeze(monkeypatch, False)
        return (pathres.default_data_root(), form, "legacy_userdata")
    if form == dataroot.FORM_PORTABLE:
        _freeze(monkeypatch, True)
        (app_root / pathres.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
        return (str(app_root), form, "legacy_portable")
    if form == dataroot.FORM_PACKAGED:
        _freeze(monkeypatch, True)   # 无 portable.txt → 新默认（哪怕应用根可写）
        return (pathres.default_data_root(), form, "legacy_userdata")
    assert form == dataroot.FORM_MCP_ONLY
    return (pathres.default_data_root(), form, "legacy_userdata")


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


# --- FORM_SOURCE：B3 的三格（legacy 保留 / 新默认 / 不问可写性） -----------------

def test_source_form_legacy_workspace_in_app_root_is_kept(app_root, monkeypatch):
    """旧安装（数据在仓库根、有真实工作区）：原样保留，不静默换根（决策 5）。"""
    _freeze(monkeypatch, False)
    _plant_workspace(app_root)
    res = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(app_root))
    assert (res.path, res.form, res.source) == (
        str(app_root), "source_form", "legacy_portable")


def test_source_form_fresh_gets_the_new_default(app_root, monkeypatch):
    """新装（应用根只有空骨架）：`<user_data_dir>/data`（决策 6 的目标格）。"""
    _freeze(monkeypatch, False)
    res = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(app_root))
    assert (res.path, res.form, res.source) == (
        pathres.default_data_root(), "source_form", "legacy_userdata")


def test_source_form_resolution_does_not_ask_writability(app_root, monkeypatch, tmp_path):
    """B3 起解析不问可写性（「可写」是能力不是选择）：应用根不可写也走新默认。

    （旧规则的「应用根不可写 → user_data_dir」连同「可写即便携」一起退役。）
    """
    _freeze(monkeypatch, False)
    missing = tmp_path / "no-such-app"     # 指向不存在路径
    res = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(missing))
    assert (res.path, res.source) == (pathres.default_data_root(), "legacy_userdata")

    monkeypatch.setattr(pathres, "_writable", lambda path: False)
    res2 = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(app_root))
    assert res2.path == pathres.default_data_root()


# --- FORM_MCP_ONLY：env > persisted > legacy 保留 / 新默认 -----------------------

def test_mcp_only_with_env(monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(elsewhere))
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == os.path.abspath(str(elsewhere))
    assert (res.form, res.source) == ("mcp_only", "env")


def test_mcp_only_fresh_install_gets_the_new_default():
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == pathres.default_data_root()
    assert (res.form, res.source) == ("mcp_only", "legacy_userdata")


def test_mcp_only_legacy_workspace_in_user_data_is_kept(tmp_path, monkeypatch):
    """旧 MCP-only 用户（数据在 user_data_dir 本体）：原样保留（B3 不静默换根）。"""
    _ = tmp_path
    ws = os.path.join(pathres.user_data_dir(), "personal", "config")
    os.makedirs(ws, exist_ok=True)
    with io.open(os.path.join(ws, "profile.md"), "w", encoding="utf-8") as fh:
        fh.write("# 档案\n")
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert (res.path, res.source) == (pathres.user_data_dir(), "legacy_userdata")


def test_mcp_only_relative_env_is_rejected(monkeypatch):
    """A3 收紧（spec 决策 1）：相对 env 值 fail-fast，不再 abspath 绑到 cwd。

    矩阵覆盖见 tests/test_dataroot_persisted.py 的四 form 参数化；这里只钉
    MCP-only 这一格（A1 的旧断言与实现都曾允许相对值）。
    """
    monkeypatch.setenv(pathres.ENV_DATA_DIR, os.path.join("rel", "data"))
    with pytest.raises(ValueError):
        dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)


def test_mcp_only_honours_env_mapping(tmp_path):
    """env 参数可传纯字典：纯函数测试不必 monkeypatch 进程环境。"""
    elsewhere = tmp_path / "mapped"
    res = dataroot.resolve_data_root(
        dataroot.FORM_MCP_ONLY, env={pathres.ENV_DATA_DIR: str(elsewhere)})
    assert res.path == os.path.abspath(str(elsewhere))
    assert (res.form, res.source) == ("mcp_only", "env")


def test_mcp_only_matches_resolve_default_root(monkeypatch):
    """与 `pathres.resolve_default_root()` 逐字对账（B3 的兜底同源）。"""
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    expected_path, _mode = pathres.resolve_default_root()
    res = dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY)
    assert res.path == expected_path
    assert res.source == "legacy_userdata"


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
    """诊断对象字段齐备且类型正确；B3 的默认根是「正常首启」（uninitialized）。"""
    _freeze(monkeypatch, False)
    d = dataroot.describe(dataroot.FORM_SOURCE, str(app_root))
    assert set(d) == set(DIAGNOSTIC_FIELDS)
    assert isinstance(d["path"], str) and d["path"] == pathres.default_data_root()
    assert d["source"] == "legacy_userdata"        # 新默认记在「传统默认」层
    assert d["form"] == "source_form"              # 传入形态原样回显
    assert d["state"] == "uninitialized"           # 根可写、工作区未建 = 正常首启
    assert d["writable"] is True                   # 走到最近已存在祖先测可写
    assert d["root_id"] is None
    assert d["schema_version"] is None
    assert d["persisted_selection"] is None
    assert d["legacy_candidates"] == []            # 全部候选都无工作区 → 空列表
    assert d["migration_state"] == "idle"


def test_describe_writable_uses_pathres_semantics(monkeypatch, tmp_path):
    """writable：走到最近的已存在祖先测它（B3 起，两边同语义）。

    「missing 深层路径」在 B3 前判 False（只看一层父目录）；新默认深一层后，
    问题的实质是「makedirs(parents=) 能不能成」——所以走到最近真实祖先。
    """
    existing = tmp_path / "data"
    existing.mkdir()
    ok = dataroot.describe(dataroot.FORM_MCP_ONLY,
                           env={pathres.ENV_DATA_DIR: str(existing)})
    assert ok["writable"] is True

    deep = tmp_path / "a" / "b" / "c"         # 中间层全缺 → 走到 tmp（可写）→ True
    deep_ok = dataroot.describe(dataroot.FORM_MCP_ONLY,
                                env={pathres.ENV_DATA_DIR: str(deep)})
    assert deep_ok["writable"] is True

    blocked = tmp_path / "blocked"            # 祖先存在但被判定不可写 → False
    blocked.mkdir()
    monkeypatch.setattr(dataroot, "_writable", lambda path: False)
    bad = dataroot.describe(dataroot.FORM_MCP_ONLY,
                            env={pathres.ENV_DATA_DIR: str(blocked)})
    assert bad["writable"] is False


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
