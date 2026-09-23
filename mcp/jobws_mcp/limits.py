# -*- coding: utf-8 -*-
"""列表类工具的条数上限（2026-09-23 二轮审计）。

这些工具的设计前提是「列表不要一次拉全表」（`server.py` 的工具描述与 README 都这么
写），而 `limit=0` 此前会被解释成"不限制"——宿主或模型一步就能拿走整张表，体积前提
直接失效。这里把取值夹进 1..MAX_LIMIT：越界不放大、也不静默当成"没有限制"。

单独一个模块的理由是规模：`tools_readonly.py` 是登记过的水位文件（只许变小），
而四个列表工具都要这一小段逻辑——塞进去就等于抬水位。
"""

DEFAULT_LIMIT = 20
MAX_LIMIT = 200


def limit_rows(rows, limit):
    """按 `limit` 截断（非法或越界一律夹进 1..MAX_LIMIT）。"""
    try:
        count = int(limit)
    except (TypeError, ValueError):
        count = DEFAULT_LIMIT
    return rows[:max(1, min(count, MAX_LIMIT))]
