# -*- coding: utf-8 -*-
"""`jobws export --obsidian --notes`：把工作区的 Markdown 材料投影成笔记。

为什么单独成模块：`_cli_export.py` 已经 253 行、逼近 300 行的规模预算，而这里
是另一条通道——上面那条是「CSV 行 → 笔记」，这条是「文件 → 笔记」，生成器不同、
不该塞进同一处（硬塞就会顶破预算，也会让两条通道互相纠缠）。

三条取舍：
1. **全量读取、不截断**：256 KB 截断是**只读端点**的语义（防止响应体膨胀），
   导出没有这个约束；把几万字的速记截成半篇，比不导出更糟。
2. **正文不重排、但也不是字节级副本**：材料本来就是给人读的 Markdown（表格 /
   列表 / 勾选框 / 代码块），重新排版只会丢信息——frontmatter 只补"它从哪来"。
   归一化三处：读时剥 BOM（`utf-8-sig`）、universal newlines 把 CRLF/CR 折成 LF、
   写出时收掉末尾空行。材料**自带 frontmatter** 时，它那块 `---` 会落成正文
   （导出笔记自己的 frontmatter 在前）——文档与矩阵的措辞按这个来，别写成
   "字节级原样"。
3. **单篇超 `NOTE_MAX_BYTES` 整份跳过、不截断**：截断会产出一篇看着完整、实则
   缺半截的笔记（最坏的一种"静默少给"）；宁可跳过并在产物 README 里点名。

跳过 `训练卡/`：那是本工作台的**练卡约定目录**（`bank import` 的卡源），导入后已在
「题库/」下以 flashcard 形态出现，再投影就是同一内容两处出现（手机上刷到重复卡）。
按目录名判定——换了目录名就不跳，这条要与 `template/workspace/03_面试准备/README`
的约定一起看。
"""

from __future__ import annotations

import io
import os
import re
import sys

from jobws_core import workspace_io  # noqa: E402
from _cli_export import _ILLEGAL_NAME_RE, yaml_scalar  # noqa: E402

# 要投影的材料目录（与 prep_notes / library 的板块口径同源：笔记两块 + 素材库）
NOTE_DIRS = ("03_面试准备", "04_知识库", "00_事实库")
# 训练卡是题库的卡源，导进题库后已在「题库/」下，投影时跳过
NOTE_SKIP_DIRS = ("训练卡",)
# 单篇上限（2 MiB，与 prep_notes 的读取上限同口径）：超限**跳过而不是截断**
NOTE_MAX_BYTES = 2 * 1024 * 1024

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.M)


def first_heading(text):
    """笔记标题取一级标题（没有就用文件名）。"""
    matched = _HEADING_RE.search(text)
    return matched.group(1).strip() if matched else ""


def render_note_projection(rel, text, source_dir):
    """一篇材料笔记：frontmatter（来源可追溯）+ 原文全文。"""
    title = first_heading(text) or os.path.splitext(os.path.basename(rel))[0]
    lines = [
        "---",
        "tags: [jobws/笔记]",
        "来源目录: %s" % yaml_scalar(source_dir),
        "相对路径: %s" % yaml_scalar(rel),
        "标题: %s" % yaml_scalar(title),
        "---",
        "",
        text.rstrip("\n"),
        "",
    ]
    return "\n".join(lines)


def _note_target_path(target_root, rel, used):
    """目标路径：保留原目录层级；同名（大小写不敏感）加 -2 / -3 而不是互相覆盖。"""
    parts = [(_ILLEGAL_NAME_RE.sub("-", part) or "-") for part in rel.split("/")]
    key = "/".join(parts).lower()
    used[key] = used.get(key, 0) + 1
    if used[key] > 1:
        stem, ext = os.path.splitext(parts[-1])
        parts[-1] = "%s-%d%s" % (stem, used[key], ext)
    return os.path.join(target_root, *parts)


def _read_note(source):
    """读一篇材料。超限 / 非 UTF-8 / 读不动都抛异常，由调用方记进跳过清单。"""
    if os.path.getsize(source) > NOTE_MAX_BYTES:
        raise ValueError("超过单篇上限 %d 字节" % NOTE_MAX_BYTES)
    with io.open(source, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def export_notes(ws, root, note_dirs=NOTE_DIRS):
    """把工作区里的 Markdown 材料投影进 `root`。

    返回每个源目录的结果字典：`{"dir": ..., "written": N, "skipped": [(rel, 原因)]}`。
    读不动（非 UTF-8 / 权限）与超限（`NOTE_MAX_BYTES`）的**都记下来再跳过**——
    静默少给会让人以为导出是完整的；跳过清单会写进产物 README。
    """
    results = []
    for source_dir in note_dirs:
        base = os.path.join(ws, source_dir)
        if not os.path.isdir(base):
            print("跳过：工作区里没有 %s" % source_dir, file=sys.stderr)
            continue
        target_root = os.path.join(root, source_dir)
        os.makedirs(target_root, exist_ok=True)
        used = {}
        written = 0
        skipped = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in NOTE_SKIP_DIRS and not name.startswith((".", "__"))
            )
            for name in sorted(filenames):
                # 隐藏文件与只读端点同口径跳过：`.jobws_tmp_*`（原子写临时名）、
                # `.draft.md`、AppleDouble 的 `._x.md` 都是"界面上看不见的东西"
                if name.startswith(".") or not name.lower().endswith(".md"):
                    continue
                source = os.path.join(dirpath, name)
                rel = os.path.relpath(source, base).replace(os.sep, "/")
                try:
                    text = _read_note(source)
                except (OSError, UnicodeDecodeError, ValueError) as exc:
                    reason = str(exc) or exc.__class__.__name__
                    print("警告：%s 没导出，已跳过（%s）" % (rel, reason),
                          file=sys.stderr)
                    skipped.append((rel, reason))
                    continue
                target = _note_target_path(target_root, rel, used)
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                workspace_io.atomic_write_text(
                    target, render_note_projection(rel, text, source_dir))
                written += 1
        results.append({"dir": source_dir, "written": written, "skipped": skipped})
    return results
