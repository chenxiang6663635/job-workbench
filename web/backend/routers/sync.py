# -*- coding: utf-8 -*-
"""工作区同步（批 8）：GUI 端（桌面版 / 浏览器 dev 同一套前端）感知「外部是否写过数据」。

单独一个路由文件而不是塞进 system.py：system.py 是水位文件（登记 328 行、
只许变小），新增端点会破坏它的登记线；而「同步」本身也是独立职责。

只 stat 不读内容（size + mtime 摘要，见 tools/workspace_io.dir_fingerprint）——
指纹没变就不必重拉；前端聚焦重拉与轻量轮询都按它决定要不要刷新。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import workspace_dir

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/workspace-version")
def workspace_version(ws: str = Depends(workspace_dir)):
    """工作区数据指纹。

    前端取用时加 `cache: "no-store"`（见 web/frontend/src/hooks/useWorkspaceSync.ts），
    避免轮询吃到启发式缓存、永远读到「没变化」。
    """
    from jobws_core import workspace_io  # 函数内 import：与 deps 的既有惯例一致

    return {"fingerprint": workspace_io.dir_fingerprint(ws)}
