# -*- coding: utf-8 -*-
"""删除类令牌的歧义闸（B4 整改 C 的回归网）。

cross_end_audit 缺陷 C：CLI 破坏性操作（删除令牌签发）不查 ambiguous，
而 API 同场景拒绝（`deps.require_unambiguous_data_root`）。修复后判据与 API
同源（同一个 `dataroot.detect_state`），唯一具位点：
- `_cli_delete._preview_and_register`——五张从表 + 投递主表删除的**唯一令牌
  出口**；
- `_cli_bank` 的 delete 分支。
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


def _plant(root, name="personal"):
    """在 root 下摆一个「像真实工作区」的信号（决定 has_workspace）。"""
    ws = root / name / "config"
    ws.mkdir(parents=True)
    (ws / "profile.md").write_text("# 档案\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(pathres.ENV_WORKSPACE, raising=False)


def _guard():
    import importlib
    return importlib.import_module("_cli_doctor")


def test_single_candidate_passes(tmp_path, monkeypatch):
    """单候选（只有 env 根有工作区）→ 无歧义，闸放行。"""
    root = tmp_path / "only"
    _plant(root)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(root))
    monkeypatch.setattr(pathres, "_APP_ROOT", str(tmp_path / "approot"))
    assert _guard().destructive_guard_reason() is None


def test_two_candidates_rejected(tmp_path, monkeypatch):
    """两候选各含工作区 → 闸给出可读理由（与 API 的 sys.dataRootAmbiguous 同判）。"""
    a, b = tmp_path / "a", tmp_path / "b"
    _plant(a)
    _plant(b)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(a))
    monkeypatch.setattr(pathres, "_APP_ROOT", str(b))
    reason = _guard().destructive_guard_reason()
    assert reason, "两候选必须拒绝"
    assert "多个像真实工作区的数据根" in reason


def test_delete_tail_refuses_without_token(tmp_path, monkeypatch):
    """接线点：`_preview_and_register` 在歧义时拒绝且**不签发令牌**。"""
    a, b = tmp_path / "a", tmp_path / "b"
    _plant(a)
    _plant(b)
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(a))
    monkeypatch.setattr(pathres, "_APP_ROOT", str(b))
    import importlib
    delete = importlib.import_module("tracker._cli_delete")
    ws = os.path.join(str(a), "personal")
    plan = {"payload": {}, "summary": "s", "diff": [], "targets": []}
    assert delete._preview_and_register("mail.delete", plan, ws) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
