# -*- coding: utf-8 -*-
"""数据根诊断块：`/api/system/paths` 的既有字段不许动，新字段只增不改。

A1（单一解析器 + 诊断对象）的落地证据：`dataRootDiagnostic` 由
`jobws_core.dataroot.describe()` 产出，本文件钉两件事——
1. 既有字段（dataRoot / mode / snapshot* / 版本 …）一个不少、一个不改名；
2. 诊断块的字段名与取值随解析结果变化（便携与 env 两种形态各一遍）。

为什么单开一个文件而不改 `test_open_folder_api.py`：那个文件钉的是
「open-folder 的预设键与数据根口径」，本文件钉的是诊断块的**契约面**；
两者失败时应指向不同结论，混在一起会让失败信息变模糊。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import pathres  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"

# A1 之前就存在的字段：一个不许少、一个不许改名（只增不减的回归网）
EXISTING_FIELDS = {
    "workspace", "dataRoot", "mode", "snapshotDir", "snapshotCount",
    "lastBackup", "appVersion", "platform", "telemetry", "note",
}

# 诊断块字段（spec §五；`form` 刻意不叫 `mode`——既有 `mode` 是解析结果）
DIAGNOSTIC_FIELDS = {
    "path", "source", "form", "state", "writable", "root_id",
    "schema_version", "persisted_selection", "legacy_candidates",
    "migration_state",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    # APPDATA 隔离：快照目录走系统用户目录，不隔离会读到开发机上的真实快照
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入，避免读到真实仓库根）
    return TestClient(main.app)


def _paths(client):
    res = client.get("/api/system/paths", params={"ws": WS})
    assert res.status_code == 200
    return res.json()


def test_existing_fields_unchanged(tmp_path, client):
    """既有字段一个不少。B3 起「非打包即便携」退役：无 env 的默认是新默认
    `<user_data_dir>/data`，mode 随之从 portable 变为 user（dataRoot ≠ 应用根）。"""
    data = _paths(client)
    assert EXISTING_FIELDS <= set(data), sorted(EXISTING_FIELDS - set(data))
    assert data["dataRoot"] == os.path.normpath(pathres.default_data_root())
    assert data["mode"] == "user"
    assert data["telemetry"] is False


def test_diagnostic_block_default(tmp_path, client):
    """默认根的诊断块：新默认 + 未初始化（正常首启）。"""
    data = _paths(client)
    diag = data["dataRootDiagnostic"]
    assert set(diag) == DIAGNOSTIC_FIELDS, sorted(set(diag) ^ DIAGNOSTIC_FIELDS)
    assert diag["path"] == data["dataRoot"]
    assert diag["form"] == "source_form"          # 非打包 = 源码形态
    assert diag["source"] == "legacy_userdata"    # 新默认记在「传统默认」层
    assert diag["state"] == "uninitialized"       # 根可写、工作区未建
    assert diag["writable"] is True
    assert diag["root_id"] is None
    assert diag["schema_version"] is None
    assert diag["persisted_selection"] is None
    assert diag["legacy_candidates"] == []
    assert diag["migration_state"] == "idle"


def test_diagnostic_block_portable(tmp_path, client):
    """显式便携标记（B3：两种形态同一判据）→ 数据根回到应用根、mode=portable。"""
    with open(os.path.join(deps.ROOT, pathres.PORTABLE_MARKER), "w",
              encoding="utf-8") as fh:
        fh.write("portable")
    data = _paths(client)
    assert data["dataRoot"] == os.path.normpath(str(tmp_path))
    assert data["mode"] == "portable"
    diag = data["dataRootDiagnostic"]
    assert diag["source"] == "legacy_portable"
    assert diag["form"] == "source_form"


def test_diagnostic_block_env(tmp_path, client, monkeypatch):
    alt = tmp_path / "alt-root"
    monkeypatch.setenv("JOBWS_DATA_DIR", str(alt))
    data = _paths(client)
    assert data["mode"] == "user"                 # 既有语义不变：此时不再等于应用根
    diag = data["dataRootDiagnostic"]
    assert diag["path"] == os.path.normpath(str(alt))
    assert diag["source"] == "env"
    assert diag["form"] == "source_form"          # form 是调用形态，不随 env 变
