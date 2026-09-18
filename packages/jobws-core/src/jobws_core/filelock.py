# -*- coding: utf-8 -*-
"""跨平台文件锁。

tracker.py 的 write_rows 是全量重读重写，Web UI 快速连续操作会产生并发写，
后写覆盖先写导致静默丢数据。所有写操作必须持锁。

Windows 用 msvcrt.locking，Unix 用 fcntl.flock；**两平台都必须兑现 timeout**
——裸 `flock(LOCK_EX)` 会无限阻塞，唯有 `LOCK_NB` 轮询能与 Windows 的
「超时抛错」行为对齐（2026-09-16 审计发现并订正）。

（2026-09-17 由 `tools/filelock.py` 原样迁入本包；旧路径保留为转发 shim，
见仓库 `tools/filelock.py`。）
"""

from __future__ import annotations

import contextlib
import os

try:
    import msvcrt

    IS_WINDOWS = True
except ImportError:
    import fcntl

    IS_WINDOWS = False


@contextlib.contextmanager
def file_lock(path, timeout=10.0):
    """对 path 加排他锁，with 块结束后释放。

    锁文件是 path 本身（要求 path 已存在），因此调用方须保证
    先创建目标文件再加锁。**path 应当是专用锁文件（如 `tracker.lock`），
    不要锁数据文件本身**——Windows 下 `os.open` 打开的文件不共享，锁期间
    再用 `io.open` 读同一文件会 `PermissionError`（2026-09-16 实测）。

    锁粒度：Unix 是整文件（flock 语义）；Windows 是**首个字节**——同一 path
    的所有写方锁的都是同一字节，互斥语义等价，但写成「整个文件」是错的
    （曾如此声明，2026-09-16 订正）。
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        _acquire(fd, timeout)
        yield
    finally:
        try:
            _release(fd)
        finally:
            os.close(fd)


def _acquire(fd, timeout):
    """取排他锁；timeout 秒内拿不到就抛 TimeoutError（两平台行为一致）。"""
    import time

    deadline = time.time() + timeout
    while True:
        try:
            if not IS_WINDOWS:
                # LOCK_NB 是关键：裸 flock(LOCK_EX) 会无限阻塞，timeout 形同虚设
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.time() >= deadline:
                raise TimeoutError("file lock timeout after %.1fs" % timeout)
            time.sleep(0.05)


def _release(fd):
    if not IS_WINDOWS:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return

    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        # 解锁失败在此无补救手段（fd 随后关闭、锁随之释放，效果等价）——保持
        # 静默但写明理由，避免被当作「静默吞错」误报（独立审查记录在案）。
        pass
