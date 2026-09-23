# -*- coding: utf-8 -*-
"""IMAP 拉取参数的范围闸门（2026-09-23 二轮审计）。

为什么单独一层：`/api/imap/fetch` 的 `since_days` 此前没有上限，而
`date - timedelta(days=10**8)` 会抛 `OverflowError`——它不属于 `ImapFetchError`，
冒泡出去就是 500「服务器内部错误」。用户其实是手滑多打了几个零，得到的却是
"程序坏了"。与 `due_within` 那条闸门同一个理由：**范围问题要说人话**。

判定与 `tools/imap_fetch.py` 里的常量同源（`MAX_SINCE_DAYS` / `MAX_LIMIT`），
放在这里是因为契约层的 `routers/imap.py` 已经贴着规模上限，塞不下这段。
"""

from apierror import ApiError

import imap_fetch


def check_fetch_range(since_days, limit):
    """越界抛 422（`err.imap.rangeInvalid`）；合法则直接返回。"""
    if since_days < 0 or since_days > imap_fetch.MAX_SINCE_DAYS:
        raise ApiError(422, "imap.rangeInvalid",
                       "时间窗必须是 0 到 %d 天之间的整数（0 = 不限）"
                       % imap_fetch.MAX_SINCE_DAYS,
                       field="since_days", max=imap_fetch.MAX_SINCE_DAYS)
    if limit is not None and (limit < 1 or limit > imap_fetch.MAX_LIMIT):
        raise ApiError(422, "imap.rangeInvalid",
                       "拉取数量必须是 1 到 %d 之间的整数" % imap_fetch.MAX_LIMIT,
                       field="limit", max=imap_fetch.MAX_LIMIT)
