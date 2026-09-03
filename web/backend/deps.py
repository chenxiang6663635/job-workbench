# -*- coding: utf-8 -*-
"""请求依赖：工作区解析与路径安全。

路径穿越防护：API 收到的任何相对路径（岗位目录名等）先归一化，
再确认仍在工作区内。本地单用户虽无攻击面，但这是要分发的产品的原型，
习惯从一开始养成。
"""

from __future__ import annotations

import os
import sys

from fastapi import HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pathres  # noqa: E402

# 应用根（只读资源）。打包后 exe 同级，解包为仓库根。
ROOT = pathres.resolve_root()
DEFAULT_WORKSPACE_NAME = "personal"

# 各模块在工作区下的固定相对位置（与 CLI 约定一致）
DIR_JOBS = "01_岗位池"
DIR_TRACKING = "05_投递追踪"
DIR_RESUME = "02_简历工坊"

# 默认工作区环境变量。CLI --workspace 会优先覆盖它，其次回退 personal/。
ENV_WORKSPACE = "JOBWS_WORKSPACE"


def data_root():
    """可写的数据根目录（personal/ 的父目录）。

    打包后若 exe 装在不可写位置（如 Program Files），会回退到系统用户目录，
    故工作区可能不在 ROOT 内。见 pathres.resolve_workspace_root。
    """
    return pathres.resolve_workspace_root(ROOT)[0]


def allowed_roots():
    """允许作为工作区父目录的根：应用根 + 可写数据根（去重）。"""
    roots = [ROOT, data_root()]
    out = []
    for r in roots:
        r = os.path.normpath(r)
        if r not in out:
            out.append(r)
    return out


def resolve_default_workspace(root=None):
    """解析默认工作区绝对路径。

    基于可写数据根目录（而非应用根），保证打包后数据落在可写位置。
    优先级：环境变量 JOBWS_WORKSPACE（相对路径）→ 数据根下的 personal/。
    返回绝对路径（可能指向不存在的目录，调用方负责判断）。
    """
    if root is None:
        root = data_root()
    name = os.environ.get(ENV_WORKSPACE, "").strip() or DEFAULT_WORKSPACE_NAME
    return os.path.normpath(os.path.join(root, name))


def workspace_dir(ws: str = Query(default=None, description="工作区相对路径")) -> str:
    """解析工作区绝对路径。缺省用可配置的默认工作区（personal/）。

    接受相对路径（供多工作区切换），拒绝绝对路径——后端只服务
    应用根或数据根之下的目录，不允许任意位置读写。
    """
    if not ws:
        return resolve_default_workspace()

    if os.path.isabs(ws):
        raise HTTPException(status_code=400, detail="workspace 必须是相对路径")

    full = os.path.normpath(os.path.join(ROOT, ws))
    # 打包后工作区可能落在系统用户目录（数据根），故两个根都允许
    if not any(full.startswith(r + os.sep) for r in allowed_roots()):
        raise HTTPException(status_code=400, detail="workspace 越出允许范围")

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
