# -*- coding: utf-8 -*-
"""素材库：事实库的文件列表与内容查看。

只读——事实卡 md 由 CLI / AI 生成，Web 只负责展示，不做编辑。
保持"判断由 AI 做，脚本只做 IO"的边界。

简历相关文件（手写 HTML / 生成 PDF / 数据驱动 JSON）已于 2026-09-03
整体迁往简历工坊（/api/resume/templates），素材库不再重复展示。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from apierror import ApiError
from deps import safe_join, workspace_dir
from iocaps import MAX_BINARY_BYTES, read_bytes_capped
from ro_files import TextDecodeError, inside, read_text_limited, walk_files

router = APIRouter(prefix="/api/library")

FACT_DIR = "00_事实库"

# md 之外可查看的文本类文件
TEXT_EXT = {".md", ".txt", ".html"}


def _section_base(ws, base_rel):
    """section 根目录 = safe_join + realpath 归属检查（锚点=**工作区根**）：
    section 目录本身被替换成指向外部的链接时整体拒绝——与 MCP 侧、与笔记同款
    （独立审查 MINOR-2；目录树**内**的 junction 另由 `inside(base, full)` 兜住）。"""
    base = safe_join(ws, base_rel)
    if not inside(ws, base):
        raise ApiError(400, "path.escape", "路径越出工作区")
    return base


@router.get("/{section}")
def list_library(section: str, ws: str = Depends(workspace_dir)):
    if section != "facts":
        raise ApiError(404, "lib.unknownSection", "未知素材库分类: %s" % section,
                       section=section)
    base = _section_base(ws, FACT_DIR)
    # 遍历与排序 2026-09-18 收敛到共享原语（ro_files.walk_files，与笔记同源）；
    # kind 是素材库自己的分流（文本内联看 / 二进制拼 URL 加载）——
    # 隐藏目录规则随共享层对齐（.obsidian 等不再出现）
    items = walk_files(base)
    for item in items:
        item["kind"] = ("text" if os.path.splitext(item["name"])[1].lower() in TEXT_EXT
                        else "binary")
    return {"section": section, "items": items, "total": len(items)}


@router.get("/{section}/content")
def library_content(section: str, rel: str, ws: str = Depends(workspace_dir)):
    if section != "facts":
        raise ApiError(404, "lib.unknownSection", "未知素材库分类: %s" % section,
                       section=section)
    base_rel = FACT_DIR
    base = _section_base(ws, base_rel)

    full = safe_join(ws, base_rel, rel)
    if not inside(base, full):
        # 参数与该码在 deps.safe_join 的抛点保持一致（无 params）
        raise ApiError(400, "path.escape", "路径越出工作区")
    if not os.path.isfile(full):
        raise ApiError(404, "lib.fileNotFound", "文件不存在: %s" % rel, rel=rel)

    ext = os.path.splitext(rel)[1].lower()
    if ext in TEXT_EXT:
        try:
            text, truncated, size = read_text_limited(full)
        except TextDecodeError:
            raise ApiError(500, "lib.readFailed", "不是 UTF-8 编码的文本文件: %s" % rel,
                           rel=rel)
        except OSError as exc:
            raise ApiError(500, "lib.readFailed", "文件读取失败: %s（%s）" % (rel, exc),
                           rel=rel)
        # 截断诚实（2026-09-18 补齐，对齐笔记）：bytes 报文件真实总字节，
        # truncated 供前端显式提示"仅显示前 256KB"
        return {"rel": rel, "type": "text", "content": text,
                "truncated": truncated, "bytes": size}

    # 二进制（PDF/图片）：返回相对路径，由前端拼 URL 加载
    return {"rel": rel, "type": "binary"}


@router.get("/{section}/file")
def library_file(section: str, rel: str, ws: str = Depends(workspace_dir)):
    """读取二进制文件字节（PDF 预览 / 图片查看）。

    通过 /api/library/{section}/file?rel=... 提供原始字节。
    """
    if section != "facts":
        raise ApiError(404, "lib.unknownSection", "未知素材库分类: %s" % section,
                       section=section)
    base_rel = FACT_DIR
    base = _section_base(ws, base_rel)

    full = safe_join(ws, base_rel, rel)
    if not inside(base, full):
        raise ApiError(400, "path.escape", "路径越出工作区")
    if not os.path.isfile(full):
        raise ApiError(404, "lib.fileNotFound", "文件不存在: %s" % rel, rel=rel)

    ext = os.path.splitext(rel)[1].lower()
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_type = "image/%s" % ext.lstrip(".")
    else:
        media_type = "application/octet-stream"

    # 超限**拒绝**（413）而不是截断：这个端点不支持 Range，浏览器要的是整份文件——
    # 截断后以 200 返回，用户拿到的是一个坏掉的 PDF，且界面上看不出原因。
    if os.path.getsize(full) > MAX_BINARY_BYTES:
        raise ApiError(413, "file.tooLarge", "文件过大，无法在此预览",
                       rel=rel, mb=MAX_BINARY_BYTES // (1024 * 1024))
    data, _truncated = read_bytes_capped(full)

    from fastapi import Response

    # 注意：不设 Content-Disposition 下载名。文件名含中文，若放入 header 会因
    # latin-1 编码限制抛 UnicodeEncodeError（HTTP header 只支持 latin-1）。
    # 这里是内联预览（iframe / img），浏览器用 URL 定位即可，不需要下载名。
    return Response(content=data, media_type=media_type)
