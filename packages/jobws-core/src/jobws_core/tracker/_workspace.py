# -*- coding: utf-8 -*-
"""CLI 侧的工作区解析：现役数据根 + 默认工作区 + `--workspace` 缺省值。

为什么单独成件（2026-10-16 #313）：`_core.py` 撞了 300 行规模闸门，而这三个函数
是同一件事（把「根决策」从 `dataroot` 消费下来），与 CSV / 锁 / 路径常量无关。

分层纪律（#313 + E 三项）：**根选择只由 `dataroot` 决定**
（`env > persisted > legacy`）；`pathres` 只负责「在给定根内解析工作区名 + 校验」。
2026-10-16 前 CLI 走 `pathres.resolve_workspace_root`，那条链没有 persisted——
设置页记住的根 CLI 不认，同名工作区下会静默读写另一个根。
"""

from __future__ import annotations

import os

from jobws_core import dataroot  # noqa: E402
from jobws_core import pathres  # noqa: E402


def resolved_data_root():
    """CLI 侧的现役数据根（唯一来源：`dataroot`，含 persisted）。"""
    return dataroot.resolve_data_root(dataroot.form_for_process(),
                                      pathres.resolve_root()).path


def default_workspace():
    """默认工作区 = `<现役数据根>/<工作区名>`（不用模块常量：解析链依赖 env）。"""
    return pathres.default_workspace(data_root=resolved_data_root())


def resolve_workspace_arg(value=None):
    """CLI `--workspace` 缺省解析：显式值原样；缺省走现役数据根。"""
    if value and str(value).strip():
        return value
    return default_workspace()
