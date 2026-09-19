# -*- coding: utf-8 -*-
"""只读文件浏览的共享原语：确定性遍历（walk_files）与诚实读取（read_text_limited）。

背景（2026-09-18，独立调研认定）：素材库（`00_事实库`）与笔记（`03/04`）都在做
"列目录 + 读一篇文本"，两处实现近乎逐行同构（重复度约 85%）、且安全强度不一致。
本模块把公共部分收敛为一份——**只读**，没有任何写路径（写通道由 approvals 唯一提供）。

分工：本模块只做"遍历、解码、上限、路径归属判断"这些与业务无关的事；
**目录白名单 / 扩展名白名单 / 错误码**仍由各 router 自己决定（错误码是各自的契约，
共享层不替它们选——解码失败抛 TextDecodeError，由调用方转成自己的码）。
"""

from __future__ import annotations

import os

# 内容读取上限：这两处都是来读全文的（对比 MCP 资源的 20KB）；超出**截断并
# 显式告知**（truncated / bytes 字段），绝不静默把截断当全文。
CONTENT_MAX_BYTES = 256 * 1024


class TextDecodeError(ValueError):
    """非 UTF-8 文本（且非截断所致）——由调用方转成自己的错误码。"""


def walk_files(base, exts=None):
    """确定性遍历 base 下的文件（**平铺**，rel 带子目录路径、正斜杠）。

    - 跳过 `__`/`.` 开头的目录（运行时产物 / 隐藏目录——Obsidian 的 .trash 也在
      此列：删掉的笔记不该"复活"）与 `.` 开头的文件；
    - `exts` 给定时只收这些扩展名（小写比较），None 表示全收；
    - 服务端 `rel` 字典序是**唯一排序口径**（前端不再排一次）；
    - 空目录天然不出现（目录结构由 rel 的路径段还原）；0 字节文件照常列出
      （文件不能静默消失，大小交给前端做「空」标记）。
    """
    items = []
    if not os.path.isdir(base):
        return items
    # 注：遍历后 stat（getsize/getmtime）若撞上文件被外部删除/替换，OSError 会
    # 响亮上抛——并发的 CLI/Obsidian 写入场景下，宁可报错也不要给出过期列表。
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith(("__", ".")))
        for name in sorted(files):
            if name.startswith("."):
                continue
            if exts is not None and os.path.splitext(name)[1].lower() not in exts:
                continue
            full = os.path.join(root, name)
            items.append({
                "rel": os.path.relpath(full, base).replace("\\", "/"),
                "name": name,
                "size": os.path.getsize(full),
                "mtime": int(os.path.getmtime(full)),
            })
    items.sort(key=lambda x: x["rel"])
    return items


def read_text_limited(full):
    """读取文本文件（上限 CONTENT_MAX_BYTES），返回 (text, truncated, bytes)。

    - `bytes` 是**文件真实总字节**（os.path.getsize），不是返回内容长度——
      前端据 truncated 显式提示"仅显示前 256KB"；
    - OSError（权限/占用/竞态删除）原样上抛，由调用方转错误码。
    """
    size = os.path.getsize(full)
    with open(full, "rb") as handle:
        raw = handle.read(CONTENT_MAX_BYTES)
    truncated = size > CONTENT_MAX_BYTES
    return decode_text(raw, truncated), truncated, size


def decode_text(raw, truncated):
    """严格 UTF-8（含 BOM 剥离）。截断可能切坏末尾多字节字符（只影响最后最多
    3 字节）——回退到能解码的最长前缀；**非截断**场景解码失败 = 不是 UTF-8，
    抛 TextDecodeError，不用 errors="replace" 静默糊住真乱码（全仓禁静默吞错的
    同一条纪律）。"""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if truncated:
            # 从最小切法开始试 = 取**最长**可解码前缀（顺序反了会多丢完整字符：
            # b"abc\xE4" 用 cut=3 会只返回 "a"——独立审查 MINOR-1）
            for cut in (1, 2, 3):
                try:
                    return raw[:-cut].decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
        raise TextDecodeError("不是 UTF-8 编码的文本")


def inside(base, full):
    """realpath 二次确认：`deps.safe_join` 只做字符串归一化、不解析符号链接。

    注意锚点：本函数防的是 `base` **目录树内**的 junction 读穿；`base` 本身被
    替换成指向外部的链接，由调用方的 base 层检查兜住（锚点=工作区根，与 MCP 侧
    同款——见各 router 的 `_section_base`，独立审查 MINOR-2）。"""
    base_real = os.path.normcase(os.path.realpath(base))
    full_real = os.path.normcase(os.path.realpath(full))
    return full_real == base_real or full_real.startswith(base_real + os.sep)
