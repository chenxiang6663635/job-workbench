# -*- coding: utf-8 -*-
"""数据根守卫（A2）：unavailable fail-closed 与 ambiguous 破坏性拒绝的 HTTP 面。

两个闸（spec §四）：
- `sys.dataRootUnavailable`（503）：persisted 选择失效时，一切经 `workspace_dir`
  的数据端点拒绝；**诊断端点（`/api/system/paths`）必须照常可用**——用户被
  fail-closed 拦下时，首先需要能看到「为什么」；
- `sys.dataRootAmbiguous`（503）：多候选且都含真实工作区时，**破坏性**入口
  （快照还原、删除预览）拒绝；读与普通写不受影响（spec 决策 3 的档位）。

刻意**不测**的东西：CLI 侧的 unavailable 守卫（在 `tools/jobws.py`，由
`tests/test_cli_doctor.py` 与 CLI 冒烟覆盖）；MCP 侧（新增的 jobws.info 是
只读诊断，不设闸）。
"""

import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import pathres  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    # 用户数据目录隔离（快照与 persisted 都走它）；两个平台变量都设，免得 CI 读到真实目录
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入）
    return TestClient(main.app)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _plant_selection(text):
    _write(os.path.join(pathres.user_data_dir(), "state", "data-root.json"), text)


def _make_ambiguous(tmp_path):
    """造「两处都像真实工作区」：应用根下的 ws-ok 与用户目录下的 ws-user。"""
    _write(os.path.join(str(tmp_path), WS, "05_投递追踪", "tracker.csv"),
           "id,公司\n1,示例\n")
    _write(os.path.join(pathres.user_data_dir(), "ws-user", "config", "profile.md"),
           "# 档案\n")


# --- unavailable：读 / 写 / 破坏性全部拒绝 -------------------------------------

def test_data_endpoint_fails_closed_when_unavailable(client, tmp_path):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    res = client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 503, res.text
    assert res.json()["error_code"] == "sys.dataRootUnavailable"


def test_write_endpoint_fails_closed_when_unavailable(client, tmp_path):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    res = client.post("/api/system/backup", params={"ws": WS})

    assert res.status_code == 503, res.text
    assert res.json()["error_code"] == "sys.dataRootUnavailable"


def test_paths_endpoint_still_reachable_when_unavailable(client, tmp_path):
    """诊断端点不能一起被闸住：否则用户看不到「为什么失败」（补救的入口）。"""
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    res = client.get("/api/system/paths", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert res.json()["dataRootDiagnostic"]["state"] == "unavailable"


# --- ambiguous：读放行、破坏性拒绝 ---------------------------------------------

def test_read_allowed_when_ambiguous(client, tmp_path):
    _make_ambiguous(tmp_path)

    res = client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 200, res.text


def test_snapshot_restore_rejected_when_ambiguous(client, tmp_path):
    _make_ambiguous(tmp_path)

    res = client.post("/api/system/snapshots/restore", params={"ws": WS},
                      json={"name": "whatever.zip"})

    assert res.status_code == 503, res.text
    assert res.json()["error_code"] == "sys.dataRootAmbiguous"


def test_delete_preview_rejected_when_ambiguous(client, tmp_path):
    _make_ambiguous(tmp_path)

    res = client.get("/api/applications/preview-delete",
                     params={"ws": WS, "id": "A001"})

    assert res.status_code == 503, res.text
    assert res.json()["error_code"] == "sys.dataRootAmbiguous"


def test_delete_preview_works_normally_when_not_ambiguous(client):
    """守卫不误伤：干净环境里删除预览照常（找不到 id 是 400，不是 503）。"""
    res = client.get("/api/applications/preview-delete",
                     params={"ws": WS, "id": "A999"})

    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "app.deleteFailed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
