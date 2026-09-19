# -*- coding: utf-8 -*-
"""文件锁（全仓写安全基石）：此前零测试覆盖——2026-09-16 全仓库审计发现后补。

钉三件事：
1. **并发「读-改-写」不丢行**：`tracker.write_rows` 是**全量重读重写**，
   不持锁时后写覆盖先写 → 静默丢数据（tools/filelock.py 模块 docstring 的原话）；
2. **持锁期间另一方必须超时失败**，而不是无限阻塞（Unix 分支曾用裸
   `flock(LOCK_EX)`，timeout 形同虚设——两平台行为必须一致）；
3. **锁会释放**：with 块结束后能立刻再拿到，不留死锁。
"""

import io
import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from jobws_core import filelock  # noqa: E402


def _read_rows(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return [line for line in fh.read().splitlines() if line]


def _append_under_lock(lock_path, data_path, tag, count):
    """模拟 write_rows 的全量重读重写：不持锁时并发必然互相覆盖。

    锁的是**专用锁文件**（与 `tracker.lock` 同形态）——Windows 下 os.open 不共享，
    把数据文件本身当锁会导致自己在锁里读不了它。
    """
    for i in range(count):
        with filelock.file_lock(lock_path):
            rows = _read_rows(data_path)
            # 放大竞态窗口：不做这一步，线程可能恰好串行执行，
            # 「没锁也能过」会让这条测试变成假绿
            time.sleep(0.001)
            rows.append("%s-%d" % (tag, i))
            with io.open(data_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")


def test_concurrent_read_modify_write_loses_nothing(tmp_path):
    lock_path = os.path.join(str(tmp_path), "tracker.lock")
    path = os.path.join(str(tmp_path), "rows.csv")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("")
    with io.open(lock_path, "w", encoding="utf-8") as fh:
        fh.write("")

    threads = [
        threading.Thread(target=_append_under_lock, args=(lock_path, path, "a", 40)),
        threading.Thread(target=_append_under_lock, args=(lock_path, path, "b", 40)),
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    rows = _read_rows(path)
    assert len(rows) == 80, "并发写丢行（锁失效）：实际 %d 行" % len(rows)
    assert len(set(rows)) == 80, "出现重复行（读改写被另一个写方覆盖）"


def test_second_acquire_times_out_while_held(tmp_path):
    path = os.path.join(str(tmp_path), "lock.csv")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("x")

    with filelock.file_lock(path, timeout=0.2):
        # 另一个 fd 抢锁：必须在 timeout 内抛 TimeoutError，而不是无限阻塞
        # （Unix 裸 flock 曾在此处挂死；Windows 一直是超时抛错）
        fd = os.open(path, os.O_RDWR)
        try:
            with pytest.raises(TimeoutError):
                filelock._acquire(fd, 0.2)
        finally:
            os.close(fd)


def test_lock_is_released_after_block(tmp_path):
    """释放后必须能立刻被别人拿到——**不能靠 close 兜底**。

    先前的写法是连续两个 `with file_lock(...)`：Unix 下就算 `_release` 是空操作，
    `finally` 里的 `os.close(fd)` 也会顺带释放 flock，用例照样通过（假绿）。
    这一版显式放开 fd，用**第二个 fd** 去抢——拿得到才算 `_release` 真的生效。
    """
    path = os.path.join(str(tmp_path), "lock.csv")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("x")

    first = os.open(path, os.O_RDWR)
    try:
        filelock._acquire(first, 0.2)
        filelock._release(first)

        second = os.open(path, os.O_RDWR)
        try:
            filelock._acquire(second, 0.2)  # 没抛 TimeoutError = 锁确实放开了
            filelock._release(second)
        finally:
            os.close(second)
    finally:
        os.close(first)
