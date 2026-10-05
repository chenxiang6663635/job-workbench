# -*- coding: utf-8 -*-
"""`jobws.info` 工具（A2）：版本 / 工作区 / 数据根诊断的字段契约。

为什么不用 SDK：`info.payload()` 是纯函数（返回 dict），字段断言脱离 MCP SDK
也能跑；注册名（`jobws.info`，宿主可见）用假 mcp 对象单独钉住，真通道由
`test_stdio_smoke.py` 的工具清单断言覆盖。

环境隔离：`APPDATA` / `XDG_DATA_HOME` 指到 tmp（persisted 探测不落真实用户
目录），`JOBWS_DATA_DIR` 指到工作区（MCP 的 data_root 只认它）。
"""

import io
import json
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import info  # noqa: E402


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    """一个初始化过的工作区；数据根与用户目录都隔离到 tmp。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    target = os.path.join(str(tmp_path), "personal")
    os.makedirs(os.path.join(target, "config"))
    with io.open(os.path.join(target, "config", "profile.md"), "w", encoding="utf-8") as f:
        f.write("# 档案\n")
    return target


def test_payload_carries_versions_workspace_and_diagnostic(ws, tmp_path):
    data = info.payload(ws)

    assert data["serverVersion"], "服务版本不能为空（未安装时回退 '0'）"
    assert data["coreVersion"], "领域包版本不能为空"
    assert data["workspace"] == ws
    diag = data["dataRoot"]
    for key in ("path", "source", "form", "state", "writable",
                "persisted_selection", "legacy_candidates"):
        assert key in diag, key
    assert diag["form"] == "mcp_only"           # MCP 的调用形态，不随环境变
    assert diag["source"] == "env"              # JOBWS_DATA_DIR 生效要可见
    assert diag["path"] == os.path.normpath(str(tmp_path))
    assert diag["state"] == "ok"
    assert diag["writable"] is True
    assert diag["persisted_selection"] is None
    by_path = {c["path"]: c["has_workspace"] for c in diag["legacy_candidates"]}
    assert by_path[os.path.normpath(str(tmp_path))] is True


def test_register_uses_dotted_tool_name(ws):
    """宿主看到的工具名是 `jobws.info`（探针与矩阵都按这个名字对账）。"""
    class _FakeMCP(object):
        def __init__(self):
            self.names = []

        def tool(self, name=None):
            def deco(fn):
                self.names.append(name or fn.__name__)
                return fn
            return deco

    fake = _FakeMCP()
    info.register(fake, ws)

    assert fake.names == ["jobws.info"]


def test_data_root_follows_persisted_selection(tmp_path, monkeypatch):
    """A3：`FORM_MCP_ONLY` 也读 Job Workbench 的持久化选择——不再只靠宿主 env。

    隔离用户目录、**不设** `JOBWS_DATA_DIR`，种一份 `state/data-root.json`：
    `paths.data_root()` 与 `jobws.info` 的 `source` 都要报 `persisted`。
    """
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)

    root = tmp_path / "picked-root"
    root.mkdir()
    sel = os.path.join(str(tmp_path / "appdata"), "job-workbench",
                       "state", "data-root.json")
    os.makedirs(os.path.dirname(sel), exist_ok=True)
    with io.open(sel, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"format": 1, "data_root": str(root),
                             "root_id": "sel-id"}))

    from jobws_mcp import paths
    assert paths.data_root() == os.path.normpath(str(root))

    diag = info.payload(os.path.join(str(root), "personal"))["dataRoot"]
    assert diag["source"] == "persisted"
    assert diag["path"] == os.path.normpath(str(root))


def test_ambiguous_hint_is_empty_when_clean(ws):
    assert info.ambiguous_hint(ws) == ""


def test_ambiguous_hint_appears_when_two_candidates_exist(ws, tmp_path):
    # 第二处候选：用户目录下再来一个像工作区的目录
    other = os.path.join(str(tmp_path), "appdata", "job-workbench", "ws-user", "config")
    os.makedirs(other)
    with io.open(os.path.join(other, "profile.md"), "w", encoding="utf-8") as f:
        f.write("# 档案\n")

    hint = info.ambiguous_hint(ws)

    assert hint, "歧义时必须给一行提示（详情走 jobws.info 的结构化输出）"
    assert "jobws.info" in hint
    assert str(tmp_path) not in hint, "提示不进宿主系统提示词里带本机路径"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
