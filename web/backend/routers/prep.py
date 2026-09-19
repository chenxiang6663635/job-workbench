# -*- coding: utf-8 -*-
"""笔记：`03_面试准备/` 与 `04_知识库/` 的只读浏览（目录列表 + 内容读取）。

工作区语义里这两层是「训练材料」——03 放表达（自我介绍 / 项目表达 / 行为面），
04 放知识（速查卡 / 面试速记），见各自 README。Web 侧**只读**：Markdown 由用户
在编辑器 / Obsidian 里写，界面只负责"看得舒服"。

两条硬约束（都有先例）：
1. **目录写死常量**（`deps.DIR_PREP` / `deps.DIR_KB`），不接受任何形式的目录参数
   —— `progress/questions.py:111-114` 记录过一次真实漏洞：曾把目录做成查询参数，
   `os.path.join` 遇绝对路径会丢掉工作区，一个绝对路径参数就能让服务端去扫任意
   目录并把正文回进响应。
2. **读路径三层防护**：`safe_join`（拦 `..` 与绝对路径）→ realpath 二次确认
   （`safe_join` 不解析符号链接，Windows 上 junction 仍能读穿，对齐 MCP 侧
   `resources.py` 的强度）→ 扩展名白名单。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from apierror import ApiError
from deps import DIR_KB, DIR_PREP, safe_join, workspace_dir

router = APIRouter(prefix="/api/prep")

# section 白名单：只认这两层，映射到写死的目录常量（"interview"/"knowledge"
# 即前端契约，与本模块同源）
SECTION_DIRS = {"interview": DIR_PREP, "knowledge": DIR_KB}

# 只列 / 只读 .md：这两个目录的约定就是 Markdown（模板、README 都是 .md）。
# 其他文件（图片等）不在"笔记浏览"的语义内——是设计决策而非错误，列表里不出现。
TEXT_EXT = {".md"}

# 内容读取上限：笔记页就是来看全文的（对比 MCP 资源的 20KB）；超出**截断并
# 显式告知**（truncated / bytes 字段），绝不静默把截断当全文。
CONTENT_MAX_BYTES = 256 * 1024


def _resolve_section(section):
    """section 白名单 → 写死的目录常量（不认识就 404，不猜也不拼路径）。"""
    base_rel = SECTION_DIRS.get(section)
    if base_rel is None:
        raise ApiError(404, "prep.unknownSection", "未知笔记分类: %s" % section,
                       section=section)
    return base_rel


def _inside(base, full):
    """realpath 二次确认：`safe_join` 只做字符串归一化、不解析符号链接——
    工作区里一个指向外部的 junction 仍能读穿（与 MCP 侧同款防护）。"""
    base_real = os.path.normcase(os.path.realpath(base))
    full_real = os.path.normcase(os.path.realpath(full))
    return full_real == base_real or full_real.startswith(base_real + os.sep)


def _decode(raw, truncated, rel):
    """严格 UTF-8（含 BOM 剥离）。

    截断可能把末尾的多字节字符切坏（只影响最后最多 3 字节）——回退到能解码的
    最长前缀；**非截断**场景解码失败 = 文件不是 UTF-8，明确报错，不用
    `errors="replace"` 静默糊住真乱码（全仓禁静默吞错的同一条纪律）。
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if truncated:
            for cut in (3, 2, 1):
                try:
                    return raw[:-cut].decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
        raise ApiError(500, "prep.readFailed", "不是 UTF-8 编码的文本文件: %s" % rel,
                       rel=rel)


@router.get("/{section}")
def list_prep(section: str, ws: str = Depends(workspace_dir)):
    """列出该层的全部 Markdown（**平铺**，rel 带子目录路径；树由前端建）。

    服务端 `rel` 字典序是**唯一排序口径**，前端不再排一次；空目录天然不出现在
    平铺结果里（目录结构由 rel 的路径段还原，空目录因此自动隐藏）；0 字节文件
    照常列出（前端显示"空"标记——文件不能静默消失）。
    """
    base_rel = _resolve_section(section)
    base = safe_join(ws, base_rel)
    items = []
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith("__"))
            for name in sorted(files):
                if name.startswith("."):
                    continue
                if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                    continue
                full = os.path.join(root, name)
                items.append({
                    "rel": os.path.relpath(full, base).replace("\\", "/"),
                    "name": name,
                    "size": os.path.getsize(full),
                    "mtime": int(os.path.getmtime(full)),
                })
    items.sort(key=lambda x: x["rel"])
    return {"section": section, "items": items, "total": len(items)}


@router.get("/{section}/content")
def prep_content(section: str, rel: str, ws: str = Depends(workspace_dir)):
    """读取一篇笔记的正文（**不落盘**；写通道不在本模块）。

    文件不存在 / 非 md / 读不动分别给明确错误码——少给比报错更危险。
    超 256KB 截断：`bytes` 报**文件真实总字节**（不是返回内容长度），
    `truncated` 供前端显式提示"仅显示前 256KB"。
    """
    base_rel = _resolve_section(section)
    base = safe_join(ws, base_rel)
    full = safe_join(ws, base_rel, rel)
    if not _inside(base, full):
        # 参数与 deps.safe_join 的同码抛点保持一致（无 params——该码文案无占位符）
        raise ApiError(400, "path.escape", "路径越出工作区")
    if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
        raise ApiError(400, "prep.notMarkdown", "只支持 .md 文件: %s" % rel, rel=rel)
    if not os.path.isfile(full):
        raise ApiError(404, "prep.fileNotFound", "文件不存在: %s" % rel, rel=rel)
    try:
        size = os.path.getsize(full)
        with open(full, "rb") as handle:
            raw = handle.read(CONTENT_MAX_BYTES)
    except OSError as exc:
        raise ApiError(500, "prep.readFailed", "文件读取失败: %s（%s）" % (rel, exc),
                       rel=rel)
    truncated = size > CONTENT_MAX_BYTES
    return {"rel": rel, "content": _decode(raw, truncated, rel),
            "truncated": truncated, "bytes": size}
