# -*- coding: utf-8 -*-
"""快照还原与演练（首发前收口批 笔 2）。

背景：备份早已能落盘（`POST /api/system/backup` + 时间机器淘汰），但**没有还原入口、
没有演练**，也没有人来测这条链——`tests/` 里此前对 `backup` / `_prune` / `_apply_retention`
零覆盖。本文件把三件事一次钉住：

1. **演练零写入**：`preview` 只读，任何字节与 mtime 都不许变（否则"我先演练一下"就不再安全）。
2. **还原语义**：覆盖同名 + 补齐缺失，**不删除**快照里没有的当前文件；且还原前自动落一份
   可回滚的快照——单机场景里"删除"是唯一不可逆动作，宁可少做。
3. **安全面**：zip-slip（`..` / 绝对路径 / 盘符相对路径）、zip 炸弹（条目数与解压总量上限）、
   凭证与运行时产物不还原、快照名不许穿越、坏包显式报错而不是留半截数据。

快照里条目的路径口径与 `_iter_files` 一致：**相对工作区父目录**，因此第一段是工作区名
（例如 `ws-ok/01_岗位池/a.md`）——这不是装饰，还原时按它确定落点。
"""

import contextlib
import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    # 默认工作区指向本用例的工作区：否则不带 ?ws= 的请求会静默落到 personal/
    # （第一版就是这么红的——所有用例都报"快照不存在"，而快照明明写下去了）
    monkeypatch.setenv("JOBWS_WORKSPACE", WS)
    # 用户数据目录：Windows 看 APPDATA、POSIX 看 XDG_DATA_HOME——**两个都要设**，
    # 否则 CI（Ubuntu）上快照会写进真实用户目录，而用例去临时目录里找（首跑就这么红）
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _snapshot_entries():
    """惰性取模块：实现尚未落地时让测试**失败**（而不是整文件收集期报错）。"""
    import snapshot_entries

    return snapshot_entries


def _ws(tmp_path):
    return tmp_path / WS


def _write(tmp_path, rel, text):
    path = _ws(tmp_path) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _snap_dir(_tmp_path=None):
    """快照目录：**问应用要**（`pathres.snapshot_root()`），不按平台猜。

    Windows 落在 `%APPDATA%\\job-workbench\\snapshots`、POSIX 落在 `$XDG_DATA_HOME/job-workbench/snapshots`；
    按平台猜路径会让用例在 CI（Ubuntu）上去临时目录里找一份写在别处的快照。
    """
    from jobws_core import pathres

    return Path(pathres.snapshot_root()) / WS


def _make_snapshot(tmp_path, files, name="ws-ok-20260923-220000-000000.zip"):
    """手搓一份快照 zip：files 为 {工作区内相对路径: 文本}。"""
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    target = snap_dir / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, text in files.items():
            zf.writestr("%s/%s" % (WS, rel), text)
    return target


def _fingerprint(root):
    """目录指纹：逐文件的相对路径 → (字节, mtime_ns)。"""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            with open(full, "rb") as handle:
                blob = handle.read()
            out[rel] = (blob, os.stat(full).st_mtime_ns)
    return out


# ---- 演出（preview）--------------------------------------------------------


def test_preview_writes_nothing_at_all(tmp_path, client):
    """演练必须零写入：字节与 mtime 全等，且不产生新文件。"""
    _write(tmp_path, "01_岗位池/a.md", "当前内容")
    _write(tmp_path, "extra.md", "快照里没有我")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "快照内容"})

    before = _fingerprint(_ws(tmp_path))
    time.sleep(0.01)

    res = client.post("/api/system/snapshots/preview", json={"name": "ws-ok-20260923-220000-000000.zip"})
    assert res.status_code == 200, res.text

    after = _fingerprint(_ws(tmp_path))
    assert before == after, "演练不许改动工作区（含 mtime）"


def test_preview_classifies_overwrite_add_same_and_kept(tmp_path, client):
    """分类要能被用户读懂：覆盖 / 新增 / 不变 / 快照外（保留不动）。"""
    _write(tmp_path, "01_岗位池/a.md", "旧")
    _write(tmp_path, "01_岗位池/same.md", "一致")
    _write(tmp_path, "extra.md", "快照里没有")
    _make_snapshot(tmp_path, {
        "01_岗位池/a.md": "新",
        "01_岗位池/same.md": "一致",
        "02_简历工坊/new.md": "补进来的",
    })

    res = client.post("/api/system/snapshots/preview", json={"name": "ws-ok-20260923-220000-000000.zip"})
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["overwrite"] == 1, data
    assert data["add"] == 1, data
    assert data["same"] == 1, data
    assert data["notInSnapshot"] == 1, data
    assert data["total"] == 3, data
    # 保留不动的那些要能被列出来，否则"还原≠回到那一刻"这件事说不清
    assert data["keptExamples"] == ["extra.md"], data


# ---- 还原（restore）--------------------------------------------------------


def test_restore_overwrites_and_adds_but_never_deletes(tmp_path, client):
    _write(tmp_path, "01_岗位池/a.md", "旧")
    _write(tmp_path, "extra.md", "快照里没有")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "新", "02_简历工坊/new.md": "补进来的"})

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-20260923-220000-000000.zip"})
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["ok"] is True
    assert data["restored"] == 1, data
    assert data["added"] == 1, data
    assert (_ws(tmp_path) / "01_岗位池" / "a.md").read_text(encoding="utf-8") == "新"
    assert (_ws(tmp_path) / "02_简历工坊" / "new.md").read_text(encoding="utf-8") == "补进来的"
    assert (_ws(tmp_path) / "extra.md").exists(), "快照里没有的文件不得被删除"


def test_restore_writes_a_rollback_snapshot_first(tmp_path, client):
    """还原前先落一份当前状态的快照——它是"还原错了"的唯一退路。"""
    _write(tmp_path, "01_岗位池/a.md", "旧")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "新"}, name="ws-ok-20260923-220000-000000.zip")

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-20260923-220000-000000.zip"})
    data = res.json()

    rollback = data["preRestoreSnapshot"]
    assert rollback and rollback != "ws-ok-20260923-220000-000000.zip"
    path = _snap_dir(tmp_path) / rollback
    assert path.is_file(), "回滚快照必须真的落盘：%s" % rollback
    with zipfile.ZipFile(path) as zf:
        assert zf.read("%s/01_岗位池/a.md" % WS).decode("utf-8") == "旧", "回滚快照必须是还原前的内容"


def test_restore_skips_credentials_and_runtime_products(tmp_path, client):
    """凭证（明文授权码/API key）与运行时产物不进还原——它们本来就不该在快照里，
    但快照是用户可手改的文件，所以入口也要拦。"""
    _write(tmp_path, "01_岗位池/a.md", "旧")
    _make_snapshot(tmp_path, {
        "01_岗位池/a.md": "新",
        "config/imap.json": '{"password": "leaked"}',
        "config/imap.lock": "POISON",  # 非空：这样"空壳锁文件"与"还原了内容"能区分开
        "01_岗位池/note.pyc": "x",
    })

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-20260923-220000-000000.zip"})
    assert res.status_code == 200, res.text
    assert not (_ws(tmp_path) / "config" / "imap.json").exists(), "授权码不得被还原进工作区"
    assert not (_ws(tmp_path) / "01_岗位池" / "note.pyc").exists()
    # 锁文件**可能**存在——那是"取全仓六把锁"的副产物（见 test_restore_waits_on_every_workspace_lock），
    # 不是还原了 zip 里的条目：所以断言它必须是空的，而不是不存在（zip 里那份内容非空）
    lock = _ws(tmp_path) / "config" / "imap.lock"
    assert not lock.exists() or lock.read_bytes() == b"", "运行时产物不该被还原（锁文件只应是空壳）"


# ---- 安全面 ---------------------------------------------------------------


@pytest.mark.parametrize("evil", ["../evil.txt", "ws-ok/../../evil.txt", "C:evil.txt", "/abs/evil.txt"])
def test_restore_rejects_entry_outside_workspace(tmp_path, client, evil):
    """zip-slip：`..` / 盘符相对路径 / 绝对路径一律拒绝，且不许落任何字节。"""
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    target = snap_dir / "ws-ok-evil.zip"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr(evil, "pwned")

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-evil.zip"})
    assert res.status_code in (400, 422), res.text
    assert res.json().get("error_code", "").startswith("sys."), res.text
    assert not (tmp_path / "evil.txt").exists(), "越界条目不许落地"


def test_preview_also_rejects_traversal_entries(tmp_path, client):
    """演练不能成为绕过口：坏包在演练阶段就该被拒。"""
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snap_dir / "ws-ok-evil.zip", "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    res = client.post("/api/system/snapshots/preview", json={"name": "ws-ok-evil.zip"})
    assert res.status_code in (400, 422), res.text


def test_restore_rejects_bomb_by_entry_count(tmp_path, client):
    """条目数上限：坏包不许把后端拖死（炸弹的另一半是解压总量上限）。"""
    module = _snapshot_entries()
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snap_dir / "ws-ok-bomb.zip", "w") as zf:
        for i in range(module.MAX_ENTRIES + 1):
            zf.writestr("%s/f%05d.md" % (WS, i), "")

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-bomb.zip"})
    assert res.status_code == 413, res.text
    # 条目数与解压总量是两个 code：它们的参数集合不同（条目数没有 size）
    assert res.json()["error_code"] == "sys.snapshotTooManyEntries", res.text


def test_restore_rejects_corrupt_zip_and_leaves_workspace_untouched(tmp_path, client):
    _write(tmp_path, "01_岗位池/a.md", "旧")
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "ws-ok-broken.zip").write_bytes(b"this is not a zip file")

    before = _fingerprint(_ws(tmp_path))
    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-broken.zip"})
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "sys.snapshotCorrupt", res.text
    assert _fingerprint(_ws(tmp_path)) == before, "坏包不许留下半截改动"


def test_snapshot_name_cannot_escape_snapshot_dir(tmp_path, client):
    res = client.post("/api/system/snapshots/restore", json={"name": "../../evil.zip"})
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "sys.snapshotName", res.text


def test_unknown_snapshot_is_404(tmp_path, client):
    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-missing.zip"})
    assert res.status_code == 404, res.text
    assert res.json()["error_code"] == "sys.snapshotNotFound", res.text


@pytest.mark.parametrize("kind", ["tracking", "jobs", "resume", "prep", "provider", "imap"])
def test_restore_waits_on_every_workspace_lock(tmp_path, client, monkeypatch, kind):
    """还原会写整仓，必须在**全部六把**工作区锁内跑：占住任一把 → 429 可重试（不是 500）。

    批末独立审查指出的缺口：只护 tracking + jobs 等于"我存简历 / 写笔记时别人在还原"——
    快照里本来就含 `02_简历工坊/**`、`03_面试准备/**` 与 `config/preferences.json`，
    两侧都做原子写，结果是静默丢更新。所以逐个 kind 都要验一遍。
    """
    import lockctx
    from jobws_core import workspace_io
    from jobws_core.filelock import file_lock

    _write(tmp_path, "01_岗位池/a.md", "旧")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "新"})

    lock_file = workspace_io.lock_path(str(_ws(tmp_path)), kind)
    os.makedirs(os.path.dirname(lock_file), exist_ok=True)

    real = lockctx.file_lock

    @contextlib.contextmanager
    def _short(path, timeout=10.0):
        with real(path, timeout=0.05):
            yield

    monkeypatch.setattr(lockctx, "file_lock", _short)

    with file_lock(lock_file):
        res = client.post(
            "/api/system/snapshots/restore",
            json={"name": "ws-ok-20260923-220000-000000.zip"})

    assert res.status_code == 429, res.text
    assert res.json()["error_code"] == "server.lockTimeout", res.text


@pytest.mark.parametrize(
    "entry",
    ["ws-ok/config/./imap.json", "ws-ok//config/imap.json", "ws-ok/config/../config/imap.json"],
)
def test_restore_cannot_be_tricked_into_writing_credentials(tmp_path, client, entry):
    """归一化绕过（批末审查 CRITICAL）：`config/./imap.json` 这类写法原先同时躲过"含 .."
    与"凭证名单精确匹配"，而落盘时由 OS 归一化成 `config/imap.json` —— 明文授权码被还原。"""
    _write(tmp_path, "01_岗位池/a.md", "旧")
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snap_dir / "ws-ok-creds.zip", "w") as zf:
        zf.writestr(entry, '{"password": "leaked"}')
        zf.writestr("%s/01_岗位池/a.md" % WS, "新")

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-creds.zip"})
    assert res.status_code in (200, 400), res.text
    assert not (_ws(tmp_path) / "config" / "imap.json").exists(), "凭证不得被还原进工作区"


@pytest.mark.parametrize("tail", ["imap.json ", "imap.json.", "imap.json  "])
def test_restore_rejects_windows_trailing_tail_aliases(tmp_path, client, tail):
    """Windows 把 `imap.json ` / `imap.json.` 解析成 `imap.json`——同一套绕过，直接拒绝。"""
    _write(tmp_path, "01_岗位池/a.md", "旧")
    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snap_dir / "ws-ok-tail.zip", "w") as zf:
        zf.writestr("%s/config/%s" % (WS, tail), '{"password": "leaked"}')

    res = client.post("/api/system/snapshots/restore", json={"name": "ws-ok-tail.zip"})
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "sys.snapshotEntry", res.text
    assert not (_ws(tmp_path) / "config" / "imap.json").exists()


def test_preview_normalizes_entry_paths_before_diffing(tmp_path, client):
    """演练的「保留不动」集合要按归一化形状比：否则 `./a.md` 会被报成"快照外"，
    而这个数字正是用户按下"还原"前的唯一凭据（批末审查 MAJOR）。"""
    _write(tmp_path, "01_岗位池/a.md", "一致")
    _make_snapshot(tmp_path, {"01_岗位池/./a.md": "一致"})

    res = client.post("/api/system/snapshots/preview",
                      json={"name": "ws-ok-20260923-220000-000000.zip"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["same"] == 1, data
    assert data["notInSnapshot"] == 0, data
    assert data["keptExamples"] == [], data


def test_restore_reports_the_rollback_point_when_it_fails_midway(tmp_path, client, monkeypatch):
    """中途失败（杀软/Excel 占着目标文件、磁盘满）必须把**回滚点名**报出来——它是这条路
    唯一的退路；只给一句"服务器内部错误"等于让用户去系统目录里按时间猜（批末审查 MAJOR）。"""
    from jobws_core import workspace_io

    _write(tmp_path, "01_岗位池/a.md", "旧")
    _write(tmp_path, "02_简历工坊/b.md", "旧")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "新", "02_简历工坊/b.md": "新"})

    real = workspace_io.atomic_write_bytes
    calls = {"n": 0}

    def flaky(path, data, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("目标文件被占用")
        return real(path, data, *args, **kwargs)

    monkeypatch.setattr(workspace_io, "atomic_write_bytes", flaky)

    res = client.post("/api/system/snapshots/restore",
                      json={"name": "ws-ok-20260923-220000-000000.zip"})

    assert res.status_code == 500, res.text
    body = res.json()
    assert body["error_code"] == "sys.snapshotRestoreFailed", body
    rollback = body["error_params"]["rollback"]
    assert body["error_params"]["written"] == 1, body
    assert (_snap_dir(tmp_path) / rollback).is_file(), "回滚快照必须真的存在：%s" % rollback
    with zipfile.ZipFile(_snap_dir(tmp_path) / rollback) as zf:
        assert zf.read("%s/01_岗位池/a.md" % WS).decode("utf-8") == "旧"


# ---- 清单与淘汰 -----------------------------------------------------------


def test_list_snapshots_is_newest_first_with_file_counts(tmp_path, client):
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "1"}, name="ws-ok-old.zip")
    _make_snapshot(tmp_path, {"01_岗位池/a.md": "2", "01_岗位池/b.md": "2"},
                   name="ws-ok-new.zip")
    (  _snap_dir(tmp_path) / "notes.txt").write_text("不是快照", encoding="utf-8")
    # 显式岔开 mtime：同一秒落两份时"新的在前"没有可判定的事实（不靠巧合断言）
    now = time.time()
    os.utime(_snap_dir(tmp_path) / "ws-ok-old.zip", (now - 100, now - 100))
    os.utime(_snap_dir(tmp_path) / "ws-ok-new.zip", (now, now))

    res = client.get("/api/system/snapshots")
    assert res.status_code == 200, res.text
    names = [item["name"] for item in res.json()["snapshots"]]
    assert names == ["ws-ok-new.zip", "ws-ok-old.zip"], names
    assert [item["files"] for item in res.json()["snapshots"]] == [2, 1]


def test_retention_keeps_one_per_window_and_removes_the_rest(tmp_path):
    """时间机器淘汰的既有行为（本轮补测）：同一窗口内过密的快照被删。"""
    from routers import system

    snap_dir = _snap_dir(tmp_path)
    snap_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for offset, name in ((0, "a.zip"), (10, "b.zip"), (20, "c.zip")):
        path = snap_dir / name
        with zipfile.ZipFile(path, "w"):
            pass
        os.utime(path, (now - offset, now - offset))

    kept, removed = system._apply_retention(str(snap_dir))
    assert (kept, removed) == (1, 2), (kept, removed)
    assert (snap_dir / "a.zip").exists(), "最新的那份必须留下"
