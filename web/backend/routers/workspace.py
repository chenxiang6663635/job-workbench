# -*- coding: utf-8 -*-
"""工作区管理：列出可用的工作区。

工作区判定标准：目录下含 `config/profile.md` 即为有效工作区
（与 tools/jd_score.py 的 resolve_profile 判定一致，保持单一事实源）。

扫描范围：应用根（ROOT）+ 可写数据根（打包后可能在系统用户目录），
两者都扫并去重——保证便携模式与回退模式下都能列出工作区。
只读扫描，不加缓存——保持 CLI 与 Web 共用同一数据源。
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from deps import ROOT, allowed_roots, resolve_default_workspace

router = APIRouter(prefix="/api/workspaces")


@router.get("")
def list_workspaces():
    """扫描含 config/profile.md 标记的目录，返回可用工作区名列表。

    返回项：
      name      目录名（相对路径，即 ?ws= 要传的值）
      isDefault 是否为当前默认工作区
    """
    default = os.path.normpath(resolve_default_workspace())
    items = []
    seen = set()

    for base in allowed_roots():
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue

        for name in entries:
            if name.startswith(".") or name in seen:
                continue
            marker = os.path.join(base, name, "config", "profile.md")
            if os.path.isfile(marker):
                full = os.path.normpath(os.path.join(base, name))
                seen.add(name)
                items.append({
                    "name": name,
                    "isDefault": default == full,
                })

    return {"items": items, "total": len(items)}
