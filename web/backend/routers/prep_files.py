# -*- coding: utf-8 -*-
"""笔记插图：图片字节直出（从 `routers/prep.py` 拆出，2026-10-09 图片端点批）。

为什么单独成件：`prep.py` 贴着 300 行规模闸门，而「正文」与「插图」的防护口径
本就不同——正文是文本、超限**截断并如实告知**（截断的 Markdown 仍可读）；插图是
字节、超限**拒绝 413**（截断的图片是坏图，不如不显示）。拆开之后两处各自的纪律
一眼读完（同款先例：`info.py` / `limits.py` 都是为水位拆出的件）。

三层防护的**实现**仍只有一份：section 白名单与 realpath 归属检查从 `routers.prep`
复用（同款先例：`resources.py` 复用 `tools_readonly._job_dir`），本模块只加
「扩展名白名单 + 媒体类型」这一层自己的决策。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response

from apierror import ApiError
from deps import safe_join, workspace_dir
from iocaps import ensure_within, read_bytes_capped
from ro_files import inside
from routers.prep import _resolve_section, _section_base

router = APIRouter(prefix="/api/prep")

# 图片（笔记插图）：窄白名单，**不含 SVG**——它是可执行脚本载体，直出等于给 XSS
# 开门；笔记树里其余二进制（附件 / 导出物）同样不在「笔记浏览」的语义内（同
# prep.TEXT_EXT 的立场：是设计决策而非错误）。
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


@router.get("/{section}/file")
def prep_file(section: str, rel: str, ws: str = Depends(workspace_dir)):
    """读取笔记里引用的图片（**只读字节**；写通道不在本模块）。

    与 `/prep/{section}/content` 同款三层防护（safe_join → realpath 归属 →
    扩展名白名单），差异只在白名单与超限口径（见文件头）。不设
    Content-Disposition：中文文件名会撞 header 的 latin-1 限制（library 同款
    说明）；这里是内联展示（img），浏览器按 URL 定位即可。
    """
    base_rel = _resolve_section(section)
    base = _section_base(ws, base_rel)
    full = safe_join(ws, base_rel, rel)
    if not inside(base, full):
        raise ApiError(400, "path.escape", "路径越出工作区")
    ext = os.path.splitext(rel)[1].lower()
    if ext not in IMAGE_EXT:
        raise ApiError(400, "prep.notImage",
                       "只支持图片（png/jpg/jpeg/gif/webp/bmp）: %s" % rel, rel=rel)
    if not os.path.isfile(full):
        raise ApiError(404, "prep.fileNotFound", "文件不存在: %s" % rel, rel=rel)
    try:
        ensure_within(full, rel)
        data, _truncated = read_bytes_capped(full)
    except OSError as exc:
        raise ApiError(500, "prep.readFailed", "文件读取失败: %s（%s）" % (rel, exc),
                       rel=rel)
    return Response(content=data, media_type=_IMAGE_MEDIA_TYPES[ext])
