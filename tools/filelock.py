# -*- coding: utf-8 -*-
"""跨平台文件锁。

tracker.py 的 write_rows 是全量重读重写，Web UI 快速连续操作会产生并发写，
后写覆盖先写导致静默丢数据。所有写操作必须持锁。

Windows 用 msvcrt.locking，Unix 用 fcntl.flock。
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
    先创建目标文件再加锁。锁粒度是整个文件。
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
    if not IS_WINDOWS:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return

    import time

    deadline = time.time() + timeout
    while True:
        try:
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
        pass
