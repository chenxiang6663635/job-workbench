# -*- coding: utf-8 -*-
"""素材库：简历工坊与事实库的文件列表与内容查看。

只读——简历 md、事实卡 md、PDF、HTML 都由 CLI / AI 生成，
Web 只负责展示，不做编辑。保持"判断由 AI 做，脚本只做 IO"的边界。
"""

from __future__ import annotations

import io
import os

from fastapi import APIRouter, Depends, HTTPException
from deps import safe_join, workspace_dir

router = APIRouter(prefix="/api/library")

FACT_DIR = "00_事实库"
RESUME_DIR = "02_简历工坊"

# md 之外可查看的文本类文件
TEXT_EXT = {".md", ".txt", ".html"}


def _list_files(base, recursive):
    if not os.path.isdir(base):
        return []
    out = []
    for root, dirs, files in os.walk(base):
        # 跳过 __pycache__ 等运行时产物
        dirs[:] = [d for d in dirs if not d.startswith("__")]
        for name in sorted(files):
            if name.startswith("."):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            out.append({
                "rel": rel,
                "name": name,
                "size": os.path.getsize(full),
                "mtime": int(os.path.getmtime(full)),
                "kind": "text" if os.path.splitext(name)[1].lower() in TEXT_EXT else "binary",
            })
        if not recursive:
            break
    out.sort(key=lambda x: (x["rel"]))
    return out


@router.get("/{section}")
def list_library(section: str, ws: str = Depends(workspace_dir)):
    if section == "facts":
        base = safe_join(ws, FACT_DIR)
    elif section == "resumes":
        base = safe_join(ws, RESUME_DIR)
    else:
        raise HTTPException(status_code=404, detail="未知素材库分类: %s" % section)

    items = _list_files(base, recursive=True)
    return {"section": section, "items": items, "total": len(items)}


@router.get("/{section}/content")
def library_content(section: str, rel: str, ws: str = Depends(workspace_dir)):
    if section == "facts":
        base_rel = FACT_DIR
    elif section == "resumes":
        base_rel = RESUME_DIR
    else:
        raise HTTPException(status_code=404, detail="未知素材库分类: %s" % section)

    full = safe_join(ws, base_rel, rel)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="文件不存在: %s" % rel)

    ext = os.path.splitext(rel)[1].lower()
    if ext in TEXT_EXT:
        with io.open(full, "r", encoding="utf-8") as f:
            return {"rel": rel, "type": "text", "content": f.read()}

    # 二进制（PDF/图片）：返回相对路径，由前端拼 URL 加载
    return {"rel": rel, "type": "binary"}


@router.get("/{section}/file")
def library_file(section: str, rel: str, ws: str = Depends(workspace_dir)):
    """读取二进制文件字节（PDF 预览 / 图片查看）。

    通过 /api/library/{section}/file?rel=... 提供原始字节。
    """
    if section == "facts":
        base_rel = FACT_DIR
    elif section == "resumes":
        base_rel = RESUME_DIR
    else:
        raise HTTPException(status_code=404, detail="未知素材库分类: %s" % section)

    full = safe_join(ws, base_rel, rel)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="文件不存在: %s" % rel)

    ext = os.path.splitext(rel)[1].lower()
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_type = "image/%s" % ext.lstrip(".")
    else:
        media_type = "application/octet-stream"

    with open(full, "rb") as f:
        data = f.read()

    from fastapi import Response

    # 注意：不设 Content-Disposition 下载名。文件名含中文，若放入 header 会因
    # latin-1 编码限制抛 UnicodeEncodeError（HTTP header 只支持 latin-1）。
    # 这里是内联预览（iframe / img），浏览器用 URL 定位即可，不需要下载名。
    return Response(content=data, media_type=media_type)
