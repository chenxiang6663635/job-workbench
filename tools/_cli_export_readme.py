# -*- coding: utf-8 -*-
"""导出产物的两份说明文件：`README.md`（人读）与 `jobws.base`（Obsidian Bases）。

为什么单独成模块：`_cli_export.py` 贴着 300 行的规模预算，而"渲染说明"与"驱动
导出"是两件事——渲染只吃数据（各目录篇数 / 材料投影结果 / 视图要显示哪些字段），
不认识工作区、也不碰文件系统，因此能单独测试、单独演进。
"""

from __future__ import annotations

import datetime


def render_readme(dirs, total, note_dirs=()):
    """导出说明：目录结构 + 怎么用 + 边界（导出是快照，不是同步）。

    材料投影里**没导出**的文件（非 UTF-8 / 超限）也列出来——产物自己说话，
    免得有人以为导出是完整的。
    """
    lines = [
        "# jobws → Obsidian 导出",
        "",
        "导出时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # 注意 `%` 比 `+` 紧：先拼好句式再格式化，别写成 A + B % total
        "共 %d 篇笔记（%s）。" % (
            total,
            "每张 CSV 一行 → 一篇 Markdown"
            + ("；另含材料正文的投影笔记" if note_dirs else ""),
        ),
        "",
        "## 目录",
        "",
    ]
    for name, count in dirs:
        lines.append("- `%s/`：%d 篇" % (name, count))
    if note_dirs:
        lines += [
            "- **材料笔记**（`--notes` 投影：正文按原意搬运 + 保留目录层级）：",
        ]
        for item in note_dirs:
            lines.append("  - `%s/`：%d 篇" % (item["dir"], item["written"]))
        skipped = [(item["dir"], rel, reason)
                   for item in note_dirs for rel, reason in item["skipped"]]
        if skipped:
            lines += ["", "### 没导出的材料", ""]
            for source_dir, rel, reason in skipped:
                lines.append("- `%s/%s`：%s" % (source_dir, rel, reason))
    lines += [
        "",
        "## 怎么用",
        "",
        "- 每篇的 **frontmatter** 是原 CSV 的全部字段——Obsidian 的 Bases / Dataview",
        "  可以按它过滤排序（例如按「当前阶段」看在跑的投递）。",
        "- `jobws.base` 是 Obsidian **Bases** 视图（较新的能力）；若你的 Obsidian",
        "  版本还不支持 Bases，忽略这个文件即可——笔记本身不依赖它。",
        "- `题库/` 下的笔记带 `#flashcard` 标签与 `题目:: 答案` 单行卡，供",
        "  **obsidian-spaced-repetition** 插件排复习。",
        "",
        "## 边界",
        "",
        "这是**快照**，不是同步：重新导出会生成一个新的带时间戳目录，旧目录不会",
        "被改写。工作区里的数据仍然是唯一真值——改数据请回工作台或 CSV。",
        "",
    ]
    return "\n".join(lines)


def render_base(tables):
    """Obsidian Bases 视图：一张按目录分组的总表（各表一个视图）。

    `tables` = `[(表名, 视图里要显示的前几列字段名), ...]`——字段由调用方算好
    传进来，这里就不再依赖 tracker 的常量表（依赖少一层，环状 import 也少一处）。
    """
    lines = ["filters:", "  or:"]
    for name, _fields in tables:
        lines.append('    - file.folder == "%s"' % name)
    lines += ["views:"]
    for name, fields in tables:
        lines += [
            '  - type: table',
            '    name: "%s"' % name,
            "    filters:",
            "      and:",
            '        - file.folder == "%s"' % name,
            "    order:",
        ]
        for field in fields:
            lines.append('      - "%s"' % field)
    lines.append("")
    return "\n".join(lines)
