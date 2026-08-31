# -*- coding: utf-8 -*-
"""请求依赖：工作区解析与路径安全。

路径穿越防护：API 收到的任何相对路径（岗位目录名等）先归一化，
再确认仍在工作区内。本地单用户虽无攻击面，但这是要分发的产品的原型，
习惯从一开始养成。
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Query

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_WORKSPACE = os.path.join(ROOT, "personal")

# 各模块在工作区下的固定相对位置（与 CLI 约定一致）
DIR_JOBS = "01_岗位池"
DIR_TRACKING = "05_投递追踪"


def workspace_dir(ws: str = Query(default=None, description="工作区相对仓库根的路径")) -> str:
    """解析工作区绝对路径。缺省 personal/。

    接受相对仓库根的路径（供未来多工作区切换），拒绝绝对路径——
    后端只服务仓库内的目录，不允许任意位置读写。
    """
    if not ws:
        return DEFAULT_WORKSPACE

    if os.path.isabs(ws):
        raise HTTPException(status_code=400, detail="workspace 必须是相对路径")

    full = os.path.normpath(os.path.join(ROOT, ws))
    if not full.startswith(ROOT + os.sep):
        raise HTTPException(status_code=400, detail="workspace 越出仓库范围")

    if not os.path.isdir(full):
        raise HTTPException(status_code=404, detail="工作区不存在: %s（先运行 tools/init_workspace.py）" % ws)

    return full


def safe_join(workspace: str, *parts: str) -> str:
    """拼接 workspace 下的相对路径，越界即拒绝。

    parts 中不允许绝对路径与 .. 逃逸；返回归一化后的绝对路径，
    且保证以 workspace 为前缀。
    """
    for p in parts:
        if os.path.isabs(p) or ".." in p.split(os.sep) + p.split("/"):
            raise HTTPException(status_code=400, detail="非法路径片段: %r" % p)

    full = os.path.normpath(os.path.join(workspace, *parts))
    if not (full == workspace or full.startswith(workspace + os.sep)):
        raise HTTPException(status_code=400, detail="路径越出工作区")

    return full
