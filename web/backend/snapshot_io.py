# -*- coding: utf-8 -*-
"""快照的**写侧**：打包回滚点与还原（读侧在 `snapshot_entries.py`）。

三条纪律：**演练零写入**（在读侧）、**还原只覆盖 + 补齐、从不删除**、**还原前先落回滚点**。

批末零上下文独立审查后的三处收紧（都有用例）：

1. **还原取全仓全部工作区锁**（`_LOCK_KINDS` 六种），不只 tracking + jobs——简历、笔记、
   Provider / IMAP 配置都在快照范围内，"只护两把"等于"我存简历时别人在还原"。
2. **中途失败要把回滚点名报出来**（`sys.snapshotRestoreFailed`）：回滚点是这条链唯一的
   退路，失败时不说等于没有——用户会对着一个半覆盖的工作区去系统目录里按时间猜。
3. 打包的临时文件**不以 `.zip` 结尾**、异常路径也清理：否则半成品会被列成"可还原的快照"。
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime

import atomicio
from jobws_core import workspace_io
from lockctx import locked
from apierror import ApiError

from snapshot_entries import _iter_files, _snapshot_dir, open_validated, read_entry, current_bytes

# 还原的锁序：全仓没有第二处同时持多把锁的代码路径，固定顺序即可避免互等
LOCK_ORDER = ("tracking", "jobs", "resume", "prep", "provider", "imap")


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def pack(ws, snap_dir, prefix):
    """把当前工作区打成一份快照（还原前的回滚点复用它，口径与备份一致）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    tmp_path = os.path.join(snap_dir, atomicio.TMP_PREFIX + "pre-%s" % stamp)
    target = os.path.join(snap_dir, "%s-%s.zip" % (prefix, stamp))
    count = 0
    try:
        if not os.path.isdir(snap_dir):
            os.makedirs(snap_dir)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full in _iter_files(ws):
                zf.write(full, os.path.relpath(full, os.path.dirname(ws)))
                count += 1
        os.replace(tmp_path, target)
    except BaseException:
        _unlink(tmp_path)
        raise ApiError(500, "sys.snapshotFailed",
                       "还原前的留痕写不出来——已中止，工作区未做任何改动")
    return os.path.basename(target), count


def _write_entries(ws, entries, zf, rollback):
    """锁内的写循环；中途失败要把回滚点名与已写计数一并报出来。"""
    counts = {"restored": 0, "added": 0, "same": 0}
    for rel, info in entries:
        full = os.path.join(ws, rel)
        blob = read_entry(zf, info)
        existed = os.path.isfile(full)
        if existed and current_bytes(full) == blob:
            counts["same"] += 1
            continue
        written = counts["restored"] + counts["added"]
        try:
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            workspace_io.atomic_write_bytes(full, blob)
        except OSError as exc:
            raise ApiError(500, "sys.snapshotRestoreFailed",
                           "还原中途失败（已写 %d 个文件）：%s；回滚点：%s"
                           % (written, exc, rollback),
                           rollback=rollback, written=written)
        counts["restored" if existed else "added"] += 1
    return counts


def _all_locks(paths):
    """按固定顺序同时持有多把锁（用 ExitStack 是为了让顺序显式可读）。"""
    from contextlib import ExitStack

    stack = ExitStack()
    for path in paths:
        stack.enter_context(locked(path))
    return stack


def restore(path, ws, ws_name):
    """还原：锁内先落回滚点，再覆盖同名 + 补齐缺失（从不删除）。"""
    snap_dir = _snapshot_dir(ws)
    locks = [workspace_io.lock_path(ws, kind) for kind in LOCK_ORDER]
    for lock_file in locks:
        os.makedirs(os.path.dirname(lock_file), exist_ok=True)

    with _all_locks(locks):
        rollback, rollback_files = pack(ws, snap_dir, "%s-pre" % ws_name)
        zf, entries = open_validated(path, ws_name)
        try:
            counts = _write_entries(ws, entries, zf, rollback)
        finally:
            zf.close()

    return {
        "ok": True,
        "restored": counts["restored"],
        "added": counts["added"],
        "same": counts["same"],
        "preRestoreSnapshot": rollback,
        "preRestoreFiles": rollback_files,
        "snapshotDir": snap_dir,
    }
