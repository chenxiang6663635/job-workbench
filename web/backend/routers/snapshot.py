# -*- coding: utf-8 -*-
"""快照还原与演练（首发前收口批 笔 2）：端点层。

实现（校验、演练、还原、还原前回滚点）在 `snapshot_io.py`，本文件只管 HTTP：
参数校验、错误码、响应组装。拆开的理由与 `atomicio`、`progress/_shared` 同款——
`system.py` 的规模水位是 328/328（只许变小），而"能还原"自带一整套校验与两份清单，
塞进去只会把水位继续撑大。
"""

from __future__ import annotations

import os
import zipfile

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import snapshot_io
from apierror import ApiError
from deps import workspace_dir

router = APIRouter(prefix="/api/system/snapshots")


class SnapshotBody(BaseModel):
    name: str


def _ws_name(ws):
    return os.path.basename(os.path.normpath(ws)) or "workspace"


def _resolve(ws, name):
    """快照名 → 已校验存在的绝对路径（名字非法 400、不存在 404）。"""
    safe = snapshot_io.safe_name(name)
    path = os.path.join(snapshot_io._snapshot_dir(ws), safe)
    if not os.path.isfile(path):
        raise ApiError(404, "sys.snapshotNotFound",
                       "快照不存在：%s" % safe, name=safe)
    return safe, path


@router.get("")
def list_snapshots(ws: str = Depends(workspace_dir)):
    """可还原的快照清单（新的在前）。"""
    snap_dir, items = snapshot_io.list_entries(ws)
    out = []
    for item in items[:snapshot_io.LIST_LIMIT]:
        try:
            with zipfile.ZipFile(item["path"]) as zf:
                files = len([info for info in zf.infolist() if not info.is_dir()])
        except (OSError, zipfile.BadZipFile):
            files = None  # 坏包照列表，演练/还原时才会被拒——清单不该整体失败
        out.append({"name": item["name"], "size": item["size"],
                    "mtime": item["mtime"], "files": files})
    return {"snapshotDir": snap_dir, "count": len(items), "snapshots": out}


@router.post("/preview")
def preview_snapshot(body: SnapshotBody, ws: str = Depends(workspace_dir)):
    """还原演练：只读。返回差异分类，不写任何字节。"""
    name, path = _resolve(ws, body.name)
    stat = os.stat(path)
    data = snapshot_io.preview(path, ws, _ws_name(ws))
    data.update({"name": name, "size": stat.st_size, "mtime": stat.st_mtime,
                 "snapshotDir": snapshot_io._snapshot_dir(ws)})
    return data


@router.post("/restore")
def restore_snapshot(body: SnapshotBody, ws: str = Depends(workspace_dir)):
    """还原快照：锁内先落回滚点，再覆盖同名 + 补齐缺失（从不删除）。"""
    name, path = _resolve(ws, body.name)
    ws_name = _ws_name(ws)
    snapshot_io.validate(path, ws_name)  # 坏包在锁外就被拒：它一个字都没动
    return snapshot_io.restore(path, ws, ws_name)
