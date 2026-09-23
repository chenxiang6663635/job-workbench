# -*- coding: utf-8 -*-
"""未捕获异常的「对外口径」：日志留全量，界面留必要信息。

异常详情里常带本机绝对路径（`FileNotFoundError: D:\\...\\report.csv`）。那些路径
对排查没用——日志里已经有完整 traceback、含栈帧与文件名；回给前端却有两个坏处：
一是把仓库布局与用户目录名抖到界面上，二是让一串"看着像 bug"的字符直接显示给人。

与 `apierror.py` 的关系：那里定义**结构化**错误（有 code、有参数）的类型，这里
处理**没有 code** 的那一类兜底异常的展示口径。两者一起保证「错误一律走契约」。
"""

import re

# 内部路径：Windows 盘符路径与 POSIX 家目录路径
_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s'\"]+|/(?:home|Users)/[^\s'\"]+")


def public_detail(exc):
    """去掉内部路径的异常摘要：保留类型与消息（定位所需），去掉路径（多余的暴露）。"""
    return _PATH_RE.sub("…", "%s: %s" % (type(exc).__name__, exc))
