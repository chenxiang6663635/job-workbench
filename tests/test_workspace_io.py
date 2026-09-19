# -*- coding: utf-8 -*-
"""共享写入原语（tools/workspace_io.py）的回归测试。

批 8 目标：CLI / MCP / 后端（桌面端）四端共用同一套"原子写 + 指纹 + 锁名"，
本文件钉住这套原语的对外承诺：
- 原子写三类（text / bytes / csv）真字节落盘、无临时残留；
- Windows 下 os.replace 被占用时按重试次数退避重试，超限才抛；
- 目录指纹只看 size+mtime（不做全内容哈希），文件增删改都会使它变化；
- 锁名工厂与四端既有路径逐字一致（tracker / jobs / resume / imap / provider）。
"""
from __future__ import annotations

import csv
import io
import os
import sys
import time

import pytest

# 自插 sys.path：不能指望"别的测试模块先被导入时顺手插好"——单独跑本文件也要能过
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import workspace_io  # noqa: E402


# --- 原子写 ---------------------------------------------------------------


def test_atomic_write_text_roundtrip(tmp_path):
    target = tmp_path / "sub" / "note.md"
    workspace_io.atomic_write_text(str(target), "第一行\n第二行\n")
    with io.open(str(target), "r", encoding="utf-8", newline="") as handle:
        assert handle.read() == "第一行\n第二行\n"
    # 目录被自动创建、无临时残留
    assert os.listdir(str(target.parent)) == ["note.md"]


def test_atomic_write_bytes_roundtrip(tmp_path):
    target = tmp_path / "out" / "blob.bin"
    payload = bytes(range(256))
    workspace_io.atomic_write_bytes(str(target), payload)
    with open(str(target), "rb") as handle:
        assert handle.read() == payload
    assert os.listdir(str(target.parent)) == ["blob.bin"]


def test_atomic_write_csv_bom_and_restval(tmp_path):
    target = tmp_path / "tracker.csv"
    rows = [{"id": "A001", "公司": "云帆", "备注": None}]
    workspace_io.atomic_write_csv(str(target), rows, ["id", "公司", "备注"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    assert text.startswith("id,公司,备注")
    # None 落盘为空串，不是 "None"；BOM 让 Excel 直接可读
    with open(str(target), "rb") as handle:
        assert handle.read(3) == b"\xef\xbb\xbf"
    assert "None" not in text


def test_atomic_write_replaces_old_content(tmp_path):
    target = tmp_path / "data.csv"
    workspace_io.atomic_write_csv(str(target), [{"a": "1"}], ["a"])
    workspace_io.atomic_write_csv(str(target), [{"a": "2"}], ["a"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "2"}]


# --- Windows 共享冲突重试 --------------------------------------------------


def test_replace_retries_on_permission_error(tmp_path, monkeypatch):
    """os.replace 第一次抛 PermissionError（被 Excel 之类占用），重试后应成功。"""
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "being used by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(workspace_io.os, "replace", flaky)
    target = tmp_path / "busy.csv"
    workspace_io.atomic_write_text(str(target), "ok", sleep=lambda _s: None)
    assert calls["n"] == 2
    assert target.read_text(encoding="utf-8") == "ok"


def test_replace_raises_after_retries_exhausted(tmp_path, monkeypatch):
    def always_busy(src, dst):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(workspace_io.os, "replace", always_busy)
    with pytest.raises(PermissionError):
        workspace_io.atomic_write_text(
            str(tmp_path / "x.txt"), "ok", retries=2, sleep=lambda _s: None
        )


# --- 目录指纹 --------------------------------------------------------------


def test_dir_fingerprint_changes_on_write(tmp_path):
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\nA001\n", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    time.sleep(0.01)
    (tracking / "tracker.csv").write_text("id\nA001\nA002\n", encoding="utf-8")
    second = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])
    assert first != second


def test_dir_fingerprint_ignores_temp_and_lock(tmp_path):
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\n", encoding="utf-8")
    base = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    (tracking / (workspace_io.TMP_PREFIX + "tracker.csv")).write_text("half", encoding="utf-8")
    (tracking / "tracker.lock").write_text("", encoding="utf-8")
    assert workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"]) == base


def test_dir_fingerprint_missing_workspace_is_stable(tmp_path):
    empty = workspace_io.dir_fingerprint(str(tmp_path / "nope"), rel_dirs=["05_投递追踪"])
    again = workspace_io.dir_fingerprint(str(tmp_path / "nope"), rel_dirs=["05_投递追踪"])
    assert empty == again and len(empty) == 16


def test_default_tracked_dirs_include_fact_base(tmp_path):
    """00_事实库 纳入默认指纹（素材库去债批，2026-09-18）：素材库与笔记同为
    只读浏览——外部生成/更新的事实卡，切回来也要能看到（不补就永远看旧内容）。"""
    assert "00_事实库" in workspace_io.DEFAULT_TRACKED_DIRS

    workspace = tmp_path / "ws"
    facts = workspace / "00_事实库"
    facts.mkdir(parents=True)
    (facts / "事实卡.md").write_text("# 一", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace))  # 不带 rel_dirs → 默认集合

    time.sleep(0.01)
    (facts / "事实卡.md").write_text("# 一\n# 二", encoding="utf-8")
    assert workspace_io.dir_fingerprint(str(workspace)) != first


# --- 锁名工厂 --------------------------------------------------------------


def test_lock_path_names_match_four_ends(tmp_path):
    ws = str(tmp_path / "personal")
    assert workspace_io.lock_path(ws, "tracking").replace("\\", "/").endswith(
        "/05_投递追踪/tracker.lock"
    )
    assert workspace_io.lock_path(ws, "jobs").replace("\\", "/").endswith(
        "/01_岗位池/.jobs.lock"
    )
    assert workspace_io.lock_path(ws, "resume").replace("\\", "/").endswith(
        "/02_简历工坊/resume.lock"
    )
    assert workspace_io.lock_path(ws, "imap").replace("\\", "/").endswith("/config/imap.lock")
    assert workspace_io.lock_path(ws, "provider").replace("\\", "/").endswith(
        "/config/provider.lock"
    )
    # prep：笔记勾选框写回（2026-09-18）——03/04 共用一把锁
    assert workspace_io.lock_path(ws, "prep").replace("\\", "/").endswith(
        "/03_面试准备/.prep.lock"
    )


def test_lock_path_unknown_kind_raises(tmp_path):
    with pytest.raises(ValueError):
        workspace_io.lock_path(str(tmp_path), "nope")


def test_lock_path_does_not_create_dirs(tmp_path):
    """锁路径是纯计算：调用方自己决定何时建目录（与既有 tracker._lock_path 对齐）。"""
    ws = str(tmp_path / "personal")
    workspace_io.lock_path(ws, "tracking")
    assert not os.path.exists(os.path.join(ws, "05_投递追踪"))
