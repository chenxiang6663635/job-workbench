# -*- coding: utf-8 -*-
"""`jobws data-root`（A3）：show / set / clear 与「三态下都必须可用」。

为什么单独一个文件：`tests/test_dataroot_persisted.py` 锁域层读写；这里锁
**CLI 呈现面与分发层**——退出码、`--json`、错误文案，以及 spec 决策 4 的硬
约束：失效态（unavailable）下 `set` / `clear` 仍是可用明路（`tools/jobws.py`
的数据根守卫必须对本命令组豁免）。这是 A2 未覆盖、A3 钉死的一条。
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

import jobws  # noqa: E402
from jobws_core import pathres  # noqa: E402

FIELDS = {"path", "source", "form", "state", "writable", "root_id",
          "schema_version", "persisted_selection", "legacy_candidates",
          "migration_state"}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """系统用户数据目录、数据根 env、应用根都指到临时目录（不落开发机真实目录）。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setattr(pathres, "_APP_ROOT", str(tmp_path / "app"))
    (tmp_path / "app" / "personal").mkdir(parents=True)


def _run(monkeypatch, capsys, argv):
    """经过**统一入口**调用一次命令（与用户 / CI 的真实路径一致）。"""
    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        code = jobws.main()
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _selection_path():
    return os.path.join(pathres.user_data_dir(), "state", "data-root.json")


def _plant_selection(text):
    path = _selection_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# --- show ----------------------------------------------------------------------

def test_show_json_fields_and_exit_zero(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code == 0, out
    data = json.loads(out)
    assert set(data) == FIELDS, sorted(set(data) ^ FIELDS)
    assert data["source"] in ("env", "persisted", "legacy_portable", "legacy_userdata")


def test_show_unavailable_exits_nonzero(monkeypatch, capsys, tmp_path):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))
    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code != 0, out
    assert json.loads(out)["state"] == "unavailable"


# --- set -----------------------------------------------------------------------

def test_set_writes_selection_and_show_reports_persisted(monkeypatch, capsys, tmp_path):
    root = tmp_path / "data"
    root.mkdir()

    code, out = _run(monkeypatch, capsys, ["data-root", "set", str(root)])
    assert code == 0, out
    assert os.path.isfile(_selection_path())
    with io.open(_selection_path(), "r", encoding="utf-8") as fh:
        assert json.load(fh)["data_root"] == str(root)

    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code == 0, out
    data = json.loads(out)
    assert data["source"] == "persisted"
    assert data["path"] == str(root)
    assert data["root_id"]


def test_set_json_emits_diagnostic(monkeypatch, capsys, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    code, out = _run(monkeypatch, capsys, ["data-root", "set", str(root), "--json"])
    assert code == 0, out
    assert json.loads(out)["source"] == "persisted"


def test_set_relative_path_is_rejected_without_writing(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, ["data-root", "set", os.path.join("rel", "x")])
    assert code != 0, out
    assert "绝对路径" in out, out
    assert not os.path.exists(_selection_path()), "非法输入不该落盘"


# --- clear ---------------------------------------------------------------------

def test_clear_is_idempotent_and_returns_to_default(monkeypatch, capsys, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    _run(monkeypatch, capsys, ["data-root", "set", str(root)])

    code, out = _run(monkeypatch, capsys, ["data-root", "clear"])
    assert code == 0, out
    assert not os.path.exists(_selection_path())

    code, out = _run(monkeypatch, capsys, ["data-root", "clear"])
    assert code == 0, out

    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code == 0, out
    assert json.loads(out)["source"] != "persisted"


# --- 补救通道：失效态下 set / clear 仍可用 -------------------------------------

def test_set_and_clear_work_while_stale_and_guard_is_exempt(monkeypatch, capsys, tmp_path):
    _plant_selection(json.dumps({"data_root": str(tmp_path / "gone")}))

    # 数据类命令照常被守门拦住（fail-closed 的证据）
    code, out = _run(monkeypatch, capsys, ["track", "--workspace", str(tmp_path), "list"])
    assert code == 1, out
    assert "dataRootUnavailable" in out, out

    # 但补救通道本身不能被拦：重选数据根
    good = tmp_path / "good"
    good.mkdir()
    code, out = _run(monkeypatch, capsys, ["data-root", "set", str(good)])
    assert code == 0, out

    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code == 0, out
    assert json.loads(out)["state"] != "unavailable"

    # 清除选择同样可用（回到 legacy 默认）
    code, out = _run(monkeypatch, capsys, ["data-root", "clear"])
    assert code == 0, out
    assert not os.path.exists(_selection_path())


# --- 用法层 --------------------------------------------------------------------

def test_help_and_missing_subcommand(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, ["data-root", "--help"])
    assert code == 0, out
    assert "show" in out and "set" in out and "clear" in out and "migrate" in out

    code, out = _run(monkeypatch, capsys, ["data-root"])
    assert code == 2, out


# --- migrate（B1）：默认 dry-run / --apply / 幂等 / 用法错误 ---------------------

def _source_root():
    """迁移的源根 = 当前生效的数据根（与被测 CLI 同一条解析链）。"""
    from jobws_core import dataroot
    return dataroot.resolve_data_root(
        dataroot.form_for_process(), pathres.resolve_root()).path


def _mk_ws_file(root):
    """给源工作区放一个文件（迁移要有东西可搬；dry-run 断言目标未被创建）。"""
    ws = os.path.join(root, "personal")
    os.makedirs(os.path.join(ws, "config"), exist_ok=True)
    with io.open(os.path.join(ws, "config", "profile.md"), "w",
                 encoding="utf-8", newline="\n") as fh:
        fh.write("# 档案\n")
    return ws


def test_migrate_dry_run_plans_without_writing(monkeypatch, capsys, tmp_path):
    _mk_ws_file(_source_root())
    target = str(tmp_path / "out")
    code, out = _run(monkeypatch, capsys, ["data-root", "migrate", target])
    assert code == 0, out
    assert "dry-run" in out, out
    assert not os.path.exists(_selection_path()), "dry-run 不该写选择文件"
    assert not os.path.exists(target), "dry-run 不该建目标目录"


def test_migrate_apply_switches_and_show_follows(monkeypatch, capsys, tmp_path):
    _mk_ws_file(_source_root())
    target = str(tmp_path / "out")
    code, out = _run(monkeypatch, capsys,
                     ["data-root", "migrate", target, "--apply", "--json"])
    assert code == 0, out
    result = json.loads(out)
    assert result["status"] == "done", result
    assert os.path.isfile(os.path.join(target, "personal", "config", "profile.md"))

    code, out = _run(monkeypatch, capsys, ["data-root", "show", "--json"])
    assert code == 0, out
    data = json.loads(out)
    assert data["source"] == "persisted", out
    assert data["path"] == target


def test_migrate_is_idempotent_when_already_current(monkeypatch, capsys, tmp_path):
    _mk_ws_file(_source_root())
    target = str(tmp_path / "out")
    assert _run(monkeypatch, capsys,
                ["data-root", "migrate", target, "--apply"])[0] == 0
    code, out = _run(monkeypatch, capsys, ["data-root", "migrate", target])
    assert code == 0, out
    assert "无需迁移" in out, out


def test_migrate_rejects_relative_target(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys,
                     ["data-root", "migrate", os.path.join("rel", "x")])
    assert code == 2, out
    assert "绝对路径" in out, out


def test_migrate_rejects_conflicting_flags(monkeypatch, capsys, tmp_path):
    code, out = _run(monkeypatch, capsys,
                     ["data-root", "migrate", str(tmp_path), "--resume"])
    assert code == 2, out
    assert "三选一" in out, out


def test_migrate_rejects_target_inside_source(monkeypatch, capsys, tmp_path):
    code, out = _run(monkeypatch, capsys,
                     ["data-root", "migrate", os.path.join(_source_root(), "inner")])
    assert code == 2, out
    assert "源数据根内部" in out, out


def test_migrate_resume_and_rollback_without_transaction_are_noops(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, ["data-root", "migrate", "--resume"])
    assert code == 0, out
    assert "没有在途事务" in out, out
    code, out = _run(monkeypatch, capsys, ["data-root", "migrate", "--rollback"])
    assert code == 0, out
    assert "没有在途事务" in out, out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
