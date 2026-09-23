# -*- coding: utf-8 -*-
"""读文件的上限（P2，2026-09-23 全仓审计）。

`read()` 一口气读完一个"可能很大"的东西，是本地优先工具最容易漏的一类口子：
磁盘那一侧是用户自己的文件（几十 MB 的 PDF 很常见），网络那一侧大小完全由对方
决定。这里把上限收成一处，调用点不再各写一个数字——散着写的后果是「改了一个
忘了另一个」，而护栏恰恰是补漏最慢的那种代码。

截断而不是拒绝：`read_*_capped` 返回 (内容, 是否被截断)，由调用方决定「截断
够用」还是「必须报错」——预览类接口截断即可，写回类接口必须知道被截了。
"""

import io

# 文本：2MB 足以覆盖 Markdown / HTML / CSV 的合理体量
MAX_TEXT_CHARS = 2_000_000
# 二进制：25MB 覆盖 PDF 与常见图片；再大就该走别的通道
MAX_BINARY_BYTES = 25 * 1024 * 1024


def read_text_capped(path, limit: int = MAX_TEXT_CHARS):
    """读文本文件：超过 limit 个字符只返回前 limit 个。返回 (文本, 是否被截断)。"""
    with io.open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(limit + 1)
    return text[:limit], len(text) > limit


def read_bytes_capped(path, limit: int = MAX_BINARY_BYTES):
    """读二进制文件：超过 limit 字节只返回前 limit 个。返回 (字节, 是否被截断)。"""
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    return data[:limit], len(data) > limit
