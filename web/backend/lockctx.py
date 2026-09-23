# -*- coding: utf-8 -*-
"""后端持锁的**唯一**写法（P1 后端错误面，2026-09-23 全仓审计）。

`jobws_core.filelock.file_lock` 拿不到锁时抛的是裸 `TimeoutError`（跨 Windows /
POSIX 同口径），而此前全仓没有任何一层接它 → 冒泡到 `main.py` 的兜底 handler →
界面收到 `server.error`「服务器内部错误」。可实际场景往往只是「另一个标签页 / CLI /
批量导入正在写同一份数据」：抢锁失败是**可重试的预期情况**，不该伪装成崩溃，
更不能让人以为数据坏了。

为什么包一层而不是在每个 router 里 try/except：一旦有人在某个入口单独处理，
两个入口对用户说的话就会漂（一个说"稍后重试"、一个说"内部错误"）。
"""
from contextlib import contextmanager

from jobws_core.filelock import file_lock

from apierror import ApiError


@contextmanager
def locked(path):
    """持锁；超时 → 429 `server.lockTimeout`（可重试），其余异常原样交给兜底层。"""
    try:
        with file_lock(path):
            yield
    except TimeoutError:
        # from None：内部的 "file lock timeout after 5.0s" 是日志口径，不是用户口径——
        # 用户只需要知道「有人在写、等一下再来」，详情已由兜底层的 logger 记录。
        raise ApiError(
            429, "server.lockTimeout",
            "另一处正在写同一份数据（另一个标签页、命令行或批量导入）；请稍后重试")
