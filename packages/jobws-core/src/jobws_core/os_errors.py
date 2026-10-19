# -*- coding: utf-8 -*-
"""OSError 的 errno → **用户能动手**的一句话。

为什么要有这一层：`str(OSError)` 是「绝对路径 + 英文 errno 文本 + 第三方库措辞」的
三合一，把它拼进返回值会把本地目录结构一起送出去（CodeQL
`py/stack-trace-exposure`）。翻译成固定文案后，原文只进日志。

**接口刻意只收 `int`（errno），不收异常对象**：函数一旦拿到异常对象，返回值就带着
污点——CodeQL 认不出我们这张映射表是 sanitizer（与 #2 SSRF / #194 同类：自定义校验器
不被识别）。在调用点把 `exc` 折成 `exc.errno`（一个 int），污点就断在那里。
"""

from __future__ import annotations

import errno

_OS_ERROR_HINTS = {
    errno.ENOSPC: "磁盘空间不足",
    errno.EACCES: "没有写入权限（可能被杀毒软件或权限设置拦住）",
    errno.EPERM: "没有权限",
    errno.EROFS: "目标在只读位置（写保护？）",
    errno.ENAMETOOLONG: "路径太长",
    errno.EBUSY: "目标正被其他程序占用",
}

FALLBACK = "详见应用日志"


def os_error_reason(errno_value):
    """errno（int）→ 用户能动手的一句话；认不出的给 `FALLBACK`。"""
    return _OS_ERROR_HINTS.get(errno_value, FALLBACK)
