# -*- coding: utf-8 -*-
"""CLI 默认工作区与数据根同源（B4 整改 A 的回归网）。

cross_end_audit 缺陷 A：CLI 的默认工作区锚在应用根——B3 把数据根默认切到
`<user_data_dir>/data` 后，新装场景 CLI 与 API / MCP 默认分叉。修复后
`pathres.default_workspace()` 是唯一实现，各 CLI parser 的 `--workspace`
默认值都从它取（**构建 parser 时调用**，不是模块常量——常量会在测试与长驻
进程里过期）。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"),
           os.path.join(ROOT_DIR, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from jobws_core import pathres  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)


def test_default_workspace_follows_data_root(tmp_path, monkeypatch):
    """env 指定数据根 → 默认工作区 = <数据根>/personal（调用时求值）。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    assert pathres.default_workspace() == os.path.join(str(tmp_path), "personal")


def test_default_workspace_follows_workspace_env(tmp_path, monkeypatch):
    """工作区名走 JOBWS_WORKSPACE（与 API / MCP 同口径）。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(pathres.ENV_WORKSPACE, "side")
    assert pathres.default_workspace() == os.path.join(str(tmp_path), "side")


def test_track_parser_default_matches_data_root(tmp_path, monkeypatch):
    """`jobws track` 的 --workspace 默认值 = 数据根推导（不再是仓库根）。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    import importlib
    misc = importlib.import_module("tracker._cli_misc")
    args = misc.build_parser().parse_args([])
    assert args.workspace == pathres.default_workspace()
    assert os.path.dirname(args.workspace) == os.path.abspath(str(tmp_path))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
