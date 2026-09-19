# -*- coding: utf-8 -*-
"""版本谱系：该版本投了哪些岗位。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from jobws_core import tracker
from deps import workspace_dir

router = APIRouter()




# ---------------------------------------------------------------------------
# 版本谱系：每个简历版本投了哪些岗位、各处于什么阶段（只读展示层）
# ---------------------------------------------------------------------------

@router.get("/lineage")
def version_lineage(ws: str = Depends(workspace_dir)):
    """按简历版本聚合投递记录：母版 → 按岗派生 → 哪版投了哪家。

    数据源就是 tracker.csv 的「简历版本」列，纯只读聚合，无新数据文件。
    """
    rows = tracker.read_rows(ws)
    groups = {}
    for row in rows:
        version = (row.get("简历版本") or "").strip() or "（未填版本）"
        groups.setdefault(version, []).append({
            "id": row.get("id", ""),
            "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""),
            "当前阶段": row.get("当前阶段", ""),
            "投递日期": row.get("投递日期", ""),
        })

    items = [
        {"version": v, "applications": apps, "total": len(apps)}
        for v, apps in sorted(groups.items())
    ]
    return {"items": items, "total": len(items)}
