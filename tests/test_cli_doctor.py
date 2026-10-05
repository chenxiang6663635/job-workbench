# -*- coding: utf-8 -*-
"""`jobws doctor`（A2）：三态的人读 / JSON 呈现与退出码。

为什么单独一个文件：`tests/test_dataroot_states.py` 锁的是 dataroot 层的判据；
这里锁 **CLI 呈现面**——退出码（unavailable 非零，其余 0）、`--json` 的字段
（照抄 `ResolvedDataRootDiagnostic` 的十个键）、文本模式下状态词可读。
"""

import io
import json
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT_DIR, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import _cli_doctor  # noqa: E402
from jobws_core import pathres  # noqa: E402

FIELDS = {"path", "source", "form", "state", "writable", "root_id",
          "schema_version", "persisted_selection", "legacy_candidates",
          "migration_state"}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """系统用户数据目录、数据根 env、应用根都指到临时目录。

    应用根也要隔离：conftest 把 pathres 的应用根注入成**真实仓库根**，而
    doctor 会把它当作一个候选——开发机上它有真实 personal/，会让三个用例
    全部变成 ambiguous（本机跑得出来、CI 跑不出来的那类假红）。
    """
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setattr(pathres, "_APP_ROOT", str(tmp_path))


def _run(capsys, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["doctor"] + argv)
    code = _cli_doctor.main()
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _profile_workspace(root, name="personal"):
    d = os.path.join(str(root), name, "config")
    os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(d, "profile.md"), "w", encoding="utf-8") as f:
        f.write("# 档案\n")


def _plant_selection(text):
    path = os.path.join(pathres.user_data_dir(), "state", "data-root.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_json_fields_and_exit_zero_when_ok(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    _profile_workspace(root)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(root))

    code, out = _run(capsys, monkeypatch, ["--json"])

    assert code == 0, out
    data = json.loads(out)
    assert set(data) == FIELDS, sorted(set(data) ^ FIELDS)
    assert data["state"] == "ok"
    assert data["path"] == os.path.normpath(str(root))


def test_json_unavailable_exits_nonzero(tmp_path, monkeypatch, capsys):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    code, out = _run(capsys, monkeypatch, ["--json"])

    assert code != 0, out
    assert json.loads(out)["state"] == "unavailable"


def test_ambiguous_and_uninitialized_still_exit_zero(tmp_path, monkeypatch, capsys):
    env_root = tmp_path / "env-root"
    _profile_workspace(env_root, "ws-env")
    _profile_workspace(pathres.user_data_dir(), "ws-user")   # 第二处候选
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(env_root))

    code, out = _run(capsys, monkeypatch, ["--json"])
    assert code == 0, out
    assert json.loads(out)["state"] == "ambiguous"

    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path / "fresh"))
    code, out = _run(capsys, monkeypatch, ["--json"])
    assert code == 0, out
    assert json.loads(out)["state"] == "uninitialized"


def test_text_output_mentions_state_and_path(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    _profile_workspace(root)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(root))

    code, out = _run(capsys, monkeypatch, [])

    assert code == 0, out
    assert "数据根" in out and "ok" in out and str(root) in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
