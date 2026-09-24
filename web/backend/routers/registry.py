# -*- coding: utf-8 -*-
"""路由注册表（2026-09-23 从 `main.py` 外提）。

为什么要外提：`web/backend/main.py` 没有水位豁免（逻辑文件上限 300 行），而收口批的三笔各自
都要加一行 `include_router`——三次都把余量吃在一个"纯登记"上，下一次再加路由就只能改结构。
把登记段搬出来之后，`main.py` 只剩"启动后端"这一件事，这张表也有了单一位置：加一个路由是
在这里加一行，而不是在入口文件的中间插一行。

顺序是**有约束的**，别随手重排：
- `application_delete` 必须在 `applications` 之后（它是 `/api/applications/<id>` 上的删除预览，
  注册顺序影响路径优先级）；
- `imap_facts` / `snapshot` / `diagnostics` / `reminders` 各自单开模块，是因为宿主路由
  （`imap.py` / `system.py` / `dashboard.py`）的水位只许变小——理由留在各自模块的 docstring 里。
"""

from __future__ import annotations

from routers import (
    application_delete,
    applications,
    approvals,
    dashboard,
    diagnostics,
    imap,
    imap_facts,
    jobs,
    library,
    prep,
    progress,
    provider,
    reminders,
    resume,
    snapshot,
    sync,
    system,
    workspace,
)

# 注册顺序即生效顺序（同前缀路径的优先级由它决定）
MODULES = (
    dashboard,
    applications,
    application_delete,  # 投递删除预览（批 D；applications.py 水位只许降故拆出）
    approvals,
    jobs,
    progress,
    library,
    workspace,
    provider,
    imap,
    imap_facts,  # 邮件解析（批 9；imap.py 水位只许降故单开）
    resume,
    system,
    snapshot,  # 快照还原与演练（收口批 笔 2；system.py 水位只许降故单开）
    diagnostics,  # 诊断包导出（笔 3；同上）
    reminders,  # 到点提醒的轻端点（笔 5；同上）
    sync,  # 批 8：工作区版本指纹（GUI 端同步用）
    prep,  # 笔记：03_面试准备 / 04_知识库 只读浏览
)


def register(app):
    """把全部路由挂到 app 上（单一位置，见模块 docstring 的顺序约束）。"""
    for module in MODULES:
        app.include_router(module.router)
