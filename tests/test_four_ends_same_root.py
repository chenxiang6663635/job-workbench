# -*- coding: utf-8 -*-
"""四端同根对账（B4 整改的集成网）。

cross_end_audit 缺口 1：此前只有核心层的 `test_dataroot*` 与各端单测，没有
「同一夹具下各端读到同一个根」的对账。本测试用一条夹具（env 指定数据根 +
隔离用户目录 + 应用根指到空目录）同时问三方：

- **CLI 面**：`pathres.default_workspace()`（各命令 --workspace 默认值来源）
- **API 面**：`dataroot.describe(form_for_process(), ROOT)`（`/api/system/paths`
  与 `deps` 守卫的同调用）
- **MCP 面**：`jobws_mcp.info.payload()`（`jobws.info` 的同源实现）

三方 path / source / state 必须一致。桌面端设置页读的是同一诊断对象
（前端另有契约测试），不重复起 Electron。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"), os.path.join(ROOT_DIR, "mcp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from jobws_core import dataroot, pathres  # noqa: E402


@pytest.fixture()
def data_root(tmp_path, monkeypatch):
    """一块「配置齐备」的测试地：数据根唯一（env 指定）、用户目录与应用根都空。"""
    appdata = tmp_path / "appdata"
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(appdata))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(appdata))
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)
    root = tmp_path / "data-root"
    ws = root / "personal" / "config"
    ws.mkdir(parents=True)
    (ws / "profile.md").write_text("# 档案\n", encoding="utf-8")
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(root))
    monkeypatch.setattr(pathres, "_APP_ROOT", str(tmp_path / "approot"))
    return root


def test_cli_api_mcp_agree_on_one_fixture(data_root):
    # ① CLI 面：默认工作区的父目录 = 数据根
    default_ws = pathres.default_workspace()
    assert os.path.dirname(default_ws) == os.path.abspath(str(data_root))

    # ② API 面（/api/system/paths 的同调用）
    api_diag = dataroot.describe(dataroot.form_for_process(), pathres.resolve_root())
    assert api_diag["path"] == os.path.abspath(str(data_root))
    assert api_diag["source"] == "env"

    # ③ MCP 面（jobws.info 的同源实现——工作区名参与状态判定）
    import importlib
    info = importlib.import_module("jobws_mcp.info")
    mcp_diag = info.payload(default_ws)["dataRoot"]
    assert mcp_diag["path"] == api_diag["path"], "MCP 与 API 必须同根"
    assert mcp_diag["source"] == api_diag["source"] == "env"
    assert mcp_diag["state"] == api_diag["state"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
