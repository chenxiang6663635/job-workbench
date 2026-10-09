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


@pytest.mark.parametrize("bad", ["..", "..\\evil", "a/../b", "C:foo", "D:\\abs", "/abs/path"])
def test_default_workspace_rejects_escapes(tmp_path, monkeypatch, bad):
    """JOBWS_WORKSPACE 越界写法必须 fail-closed（2026-10-08 审计 1.1-3）。

    此前 CLI 是唯一静默口：`../x` 或绝对路径会让默认工作区静默读写数据根之外
    的目录；Web 已 400 `ws.outOfRange`、MCP 由 `within_any` 兜住——现在同一道闸。
    """
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(pathres.ENV_WORKSPACE, bad)
    with pytest.raises(pathres.WorkspaceOutOfRange) as excinfo:
        pathres.default_workspace()
    message = str(excinfo.value)
    assert "JOBWS_WORKSPACE" in message and "数据根" in message, message


def test_default_workspace_still_allows_nested_name(tmp_path, monkeypatch):
    """根内的嵌套相对名（a/b）不算越界——拒绝的是越界写法，不是子目录。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(pathres.ENV_WORKSPACE, "side/inner")
    assert pathres.default_workspace() == os.path.join(str(tmp_path), "side", "inner")


def test_cli_maps_escaped_workspace_env_to_exit_2(tmp_path, monkeypatch, capsys):
    """端到端：坏配置由入口译成退出码 2 + 可读文案，而不是抛裸栈。"""
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(pathres.ENV_WORKSPACE, "../evil")
    import jobws  # tools/jobws.py：唯一 CLI 入口

    code = jobws.main(["track", "list"])
    captured = capsys.readouterr()
    assert code == 2, (code, captured)
    assert "JOBWS_WORKSPACE" in captured.out + captured.err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
