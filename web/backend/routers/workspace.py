# -*- coding: utf-8 -*-
"""工作区管理：列出仓库根下可用的工作区。

工作区判定标准：仓库根下含 `config/profile.md` 的目录即为有效工作区
（与 tools/jd_score.py 的 resolve_profile 判定一致，保持单一事实源）。
只读扫描，不加缓存——保持 CLI 与 Web 共用同一数据源。
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from deps import ROOT, resolve_default_workspace

router = APIRouter(prefix="/api/workspaces")


@router.get("")
def list_workspaces():
    """扫描仓库根下含 config/profile.md 标记的目录，返回可用工作区名列表。

    返回项：
      name      目录名（相对仓库根，即 ?ws= 要传的值）
      isDefault 是否为当前默认工作区
    """
    default = resolve_default_workspace()
    items = []
    try:
        entries = sorted(os.listdir(ROOT))
    except OSError:
        entries = []

    for name in entries:
        if name.startswith("."):
            continue
        marker = os.path.join(ROOT, name, "config", "profile.md")
        if os.path.isfile(marker):
            full = os.path.normpath(os.path.join(ROOT, name))
            items.append({
                "name": name,
                "isDefault": os.path.normpath(default) == full,
            })

    return {"items": items, "total": len(items)}
