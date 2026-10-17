# -*- coding: utf-8 -*-
"""#313 复现：持久化数据根选择 B 后，CLI 的默认工作区落在哪个根。

`pathres.resolve_workspace_root()` 的解析链是
`JOBWS_DATA_DIR → portable.txt → legacy 保留 → 新默认`，**不含 persisted**；
而 `dataroot.resolve_data_root()`（Web / MCP 用的）是
`env → persisted → legacy`。本文件只取证这两条链在同一环境下是否一致。

红 = CLI 与 Web/MCP 的「现役数据根」不同源（#313）；
绿 = 两边同源，可关闭该单。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"),
           os.path.join(ROOT_DIR, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from jobws_core import dataroot, pathres, tracker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """照 `tests/test_cli_default_workspace.py` 的隔离范式。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)


def _mk_ws(root):
    """造一个可被识别的真实工作区（legacy 判定要 config/profile.md）。"""
    cfg = os.path.join(str(root), "personal", "config")
    os.makedirs(cfg, exist_ok=True)
    with open(os.path.join(cfg, "profile.md"), "w", encoding="utf-8") as fh:
        fh.write("# 档案\n")


def test_cli_default_workspace_follows_persisted_selection(tmp_path):
    """persisted=B，且 A 与 B **都有**同名 `personal`：CLI 必须落在 B。

    这正是「设置页记住 B、CLI 却读写 A」的场景（#313 的发行风险形态）。
    """
    app, data = tmp_path / "app", tmp_path / "data"
    _mk_ws(app)
    _mk_ws(data)
    dataroot.write_persisted_selection(str(data), source="user")

    # 对照组：统一解析器（Web / MCP）确实给出 B——证明选择本身有效
    resolved = dataroot.resolve_data_root(dataroot.FORM_SOURCE, str(app))
    assert os.path.normpath(resolved.path) == os.path.normpath(str(data))
    assert resolved.source == "persisted"

    # 被测：CLI 的默认工作区（`tracker.default_workspace` = `pathres.default_workspace`）
    assert os.path.normpath(tracker.default_workspace()) == \
        os.path.normpath(os.path.join(str(data), "personal"))


def test_cli_workspace_arg_default_follows_persisted_selection(tmp_path):
    """`--workspace` 缺省值走 **tracker 门面**（CLI 各入口消费它），同样必须落在 B。

    注意分层（#313）：`pathres.resolve_workspace_arg` 是 legacy 层、不读 persisted；
    `pathres` 不能反向 import `dataroot`（会成环），所以缺省解析上移到
    `tracker.resolve_workspace_arg`，四个 CLI 入口统一走它。
    """
    app, data = tmp_path / "app", tmp_path / "data"
    _mk_ws(app)
    _mk_ws(data)
    dataroot.write_persisted_selection(str(data), source="user")

    got = tracker.resolve_workspace_arg(None)

    assert os.path.normpath(got) == \
        os.path.normpath(os.path.join(str(data), "personal"))
