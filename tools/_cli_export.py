# -*- coding: utf-8 -*-
"""导出：把工作区的八张 CSV 导成 **Obsidian 可读的 Markdown 笔记**。

为什么有这个命令：数据在这台机器上，但"能读"和"好读"是两件事——CSV 在表格里
是一行，在自己的笔记库里才是一篇。导出的形态刻意是**每行一笔记 + frontmatter**：
frontmatter 让 Obsidian 的 Bases / Dataview 能按字段过滤排序，正文表格给人读。

三条纪律：
1. **只读工作区**：本命令一行 CSV 都不改（导出是快照，重跑不会污染原数据）。
2. **不覆盖**：输出目录带时间戳（`obsidian-export-<YYYYmmdd-HHMMSS>`）；已存在
   同名目录就报错退出——静默覆盖导出的历史是数据丢失（与 `init` 不给 --force
   就拒绝同一条）。
3. **写不坏的字段值**：frontmatter 的值一律用**双引号**包裹并转义引号/反斜杠/
   换行——YAML 里冒号、井号、引号开头的字符串最容易把整篇笔记读坏，统一加引号
   是最省事且不会出错的做法（代价只是引号多了点）。

八张表：投递记录 / 时间线 / 面试 / 宣讲会 / 邮件 / 联系人 / Offer / 题库。
题库笔记额外带 spaced-repetition 的卡片语法（`#flashcard` + `题目:: 答案`）。

`--notes` 时另把 `03_面试准备` / `04_知识库` / `00_事实库` 的 Markdown 投影成
笔记：保留目录层级、**全量读取不截断**（256 KB 截断是只读端点的语义，带进导出会
把几万字的速记截成半篇）、正文按原意搬运（剥 BOM、折 CRLF、收尾空行）。训练卡
目录不重复投影（那些卡已经在题库里），隐藏文件与超限文件跳过并写进产物 README。

命令层只管参数与退出码；导出的每一步都是可单测的纯函数（见 tests/
test_export_obsidian.py）。
"""

from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from jobws_core import question_bank  # noqa: E402
from jobws_core import tracker  # noqa: E402
from jobws_core import workspace_io  # noqa: E402

from _cli_export_readme import render_base, render_readme  # noqa: E402

# 目录名 → (CSV 字段名列表, 读取函数, 标题字段, 里层子目录)
# 目录名用中文：与工作区里 01_岗位池 这类命名同款，进 Obsidian 后一眼认得出。
TABLES = [
    ("投递记录", "FIELDS", tracker.read_rows, ("公司", "岗位")),
    ("时间线", "HISTORY_FIELDS", tracker.read_history, ("id", "字段")),
    ("面试", "INTERVIEW_FIELDS", tracker.read_interviews, ("公司", "岗位", "轮次")),
    ("宣讲会", "TALK_FIELDS", tracker.read_talks, ("公司",)),
    ("邮件", "MAIL_FIELDS", tracker.read_mails, ("主题",)),
    ("联系人", "CONTACT_FIELDS", tracker.read_contacts, ("姓名",)),
    ("Offer", "OFFER_FIELDS", tracker.read_offers, ("公司", "岗位")),
    ("题库", "QUESTION_FIELDS", question_bank.read_questions, ("题目",)),
]

# Windows 文件名非法字符与路径分隔符（字段值里可能出现 `/`，如「研发/测试」）
_ILLEGAL_NAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]')
_MAX_NAME_LEN = 60



def yaml_scalar(value):
    """YAML 标量：一律双引号 + 转义（见模块 docstring 纪律 3）。"""
    text = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return '"%s"' % text


def safe_name(row, title_fields, fallback):
    """笔记文件名（不含 .md）：标题字段拼起来后清掉非法字符。

    同名冲突由调用方加序号后缀解决——宁可 `xxx-2.md`，也不能覆盖前一篇。
    """
    parts = [(row.get(field) or "").strip() for field in title_fields]
    title = " ".join(p for p in parts if p) or fallback
    title = _ILLEGAL_NAME_RE.sub("-", title).strip(" .")
    if not title:
        title = fallback
    return title[:_MAX_NAME_LEN]


def render_note(fields, row, kind):
    """一篇笔记：frontmatter（给 Bases/Dataview）+ 正文表格（给人读）。"""
    lines = ["---"]
    if kind == "题库":
        # spaced-repetition 插件按标签认卡片
        lines.append("tags: [flashcard, jobws/题库]")
    for field in fields:
        lines.append("%s: %s" % (field, yaml_scalar(row.get(field))))
    lines.append("---")
    lines.append("")
    title = " ".join(
        (row.get(f) or "").strip() for f in TABLE_TITLE_FIELDS[kind]
    ).strip() or kind
    lines.append("# %s" % title)
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    for field in fields:
        cell = (row.get(field) or "").replace("|", "\\|").replace("\n", " ")
        lines.append("| %s | %s |" % (field, cell))
    if kind == "题库":
        lines.append("")
        lines.append("## 复习卡（spaced-repetition）")
        # 单行卡语法：`题目:: 答案`——插件把它当一张卡来排复习
        lines.append("%s:: %s" % (
            (row.get("题目") or "").replace("\n", " ").strip(),
            (row.get("答案要点") or "").replace("\n", " ").strip(),
        ))
    lines.append("")
    return "\n".join(lines)


# 标题字段按目录名取（render_note 用）
TABLE_TITLE_FIELDS = dict((name, fields) for name, _c, _r, fields in TABLES)


def field_names(const_name):
    """字段名列表：从 tracker 的常量表里取（不在本模块抄一份列名）。"""
    return list(getattr(tracker, const_name))


# --- 材料投影（`--notes`）---------------------------------------------------
# 实现在 `_cli_export_notes.py`：那是**另一条通道**（文件 → 笔记，不是 CSV 行 →
# 笔记），且本文件已逼近 300 行的规模预算，故不并在这里。


def now_stamp():
    """导出目录的时间戳（拆成一个函数：测试要固定住它才能钉「不覆盖」这条）。"""
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def export_obsidian(workspace, target_dir, include_notes=False):
    """导出到 `<target_dir>/obsidian-export-<时间戳>/`，返回 (root, 笔记数)。

    目录不存在就建（用户指定的导出根目录）；导出目录同名已存在则抛 RuntimeError。
    `include_notes` 为真时，另把 03/04/00 三个材料目录投影成笔记（正文按原意搬运）。
    """
    ws = tracker.resolve_ws(workspace)
    if not os.path.isdir(ws):
        raise RuntimeError("工作区不存在：%s" % ws)
    # 导出目录必须在工作区**之外**（矩阵里写死的承诺：不改工作区）。除了污染工作区，
    # 更坏的形态是目标落在材料目录里：材料投影会把刚写出的导出目录当成材料再抄一遍
    # （嵌套复制、README 篇数虚报）。一行守卫消灭这条路径，别指望用户不这么用。
    if _inside(os.path.realpath(target_dir), os.path.realpath(ws)):
        raise RuntimeError(
            "导出目录必须在工作区之外（否则会污染工作区，并被材料投影重复收录）：%s"
            % target_dir)
    stamp = now_stamp()
    root = os.path.join(target_dir, "obsidian-export-%s" % stamp)
    if os.path.exists(root):
        raise RuntimeError("导出目录已存在（不覆盖，换一个时间再导出）：%s" % root)
    os.makedirs(root)

    total = 0
    dirs = []
    for name, const_name, reader, title_fields in TABLES:
        try:
            rows = reader(ws)
        except OSError as exc:
            # 单张表读不动不该让整次导出失败——写进 README，而不是静默少一张
            rows = []
            print("警告：%s 读不到，已跳过（%s）" % (name, exc), file=sys.stderr)
        fields = field_names(const_name)
        sub = os.path.join(root, name)
        os.makedirs(sub)
        used = {}
        for index, row in enumerate(rows or [], start=1):
            base = safe_name(row, title_fields, "%s-%03d" % (name, index))
            used[base] = used.get(base, 0) + 1
            # 重名加序号：同公司同岗位的两条投递是常态，不能互相覆盖
            filename = base if used[base] == 1 else "%s-%d" % (base, used[base])
            path = os.path.join(sub, "%s.md" % filename)
            workspace_io.atomic_write_text(path, render_note(fields, row, name))
            total += 1
        dirs.append((name, len(rows or [])))

    note_dirs = []
    if include_notes:
        # 函数内 import：投影模块要用这里的 yaml_scalar / _ILLEGAL_NAME_RE，
        # 顶层互引就是循环依赖
        from _cli_export_notes import export_notes
        note_dirs = export_notes(ws, root)
        total += sum(item["written"] for item in note_dirs)
    workspace_io.atomic_write_text(
        os.path.join(root, "README.md"), render_readme(dirs, total, note_dirs))
    # Bases 视图只显示每张表的前几列（字段由这里算好传进去，渲染模块不依赖 tracker）
    workspace_io.atomic_write_text(
        os.path.join(root, "jobws.base"),
        render_base([(name, field_names(const_name)[:6])
                     for name, const_name, _reader, _titles in TABLES]))
    return root, total


def _inside(path, root):
    """`path` 是否就是 `root` 或落在它之下（两侧都应是 realpath）。"""
    return path == root or path.startswith(root + os.sep)


# 产物说明（README / jobws.base）的渲染已拆到 `_cli_export_readme.py`：本文件贴着
# 300 行规模预算，而"渲染说明"只吃数据、不碰文件系统，适合独立演进而非继续堆这里。


def cmd_export(args):
    """`jobws export --obsidian <目录>`：导出成 Obsidian 笔记。"""
    workspace = getattr(args, "workspace", None)
    target = (getattr(args, "obsidian", "") or "").strip()
    if not target:
        print("用法：jobws export --obsidian <导出目录>", file=sys.stderr)
        return 2
    if not os.path.isdir(target):
        print("导出目录不存在：%s（先建好它，或换一个目录）" % target,
              file=sys.stderr)
        return 1
    try:
        root, total = export_obsidian(workspace, target,
                                      include_notes=bool(getattr(args, "notes", False)))
    except RuntimeError as exc:
        print("导出失败：%s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("导出失败（写入出错）：%s" % exc, file=sys.stderr)
        return 1
    print("已导出 %d 篇笔记 → %s" % (total, root))
    print("README 与 jobws.base 在同一目录下（Bases 视图需要较新的 Obsidian）。")

    sync_to = (getattr(args, "sync_to", "") or "").strip()
    if sync_to:
        # 白名单 = 本次导出真正会产生的顶层条目；sync 只碰它们——库里的 .obsidian/
        # 与白名单外的文件不在任何读写删路径上
        names = [name for name, _c, _reader, _titles in TABLES] + ["README.md", "jobws.base"]
        include_notes = bool(getattr(args, "notes", False))
        if include_notes:
            from _cli_export_notes import NOTE_DIRS  # 函数内 import：避免环状依赖
            names += list(NOTE_DIRS)
        try:
            from _cli_export_sync import sync_execute, sync_plan  # 函数内 import：同上
            ops, lines = sync_plan(root, sync_to, names, workspace,
                                   include_notes=include_notes)
            for line in lines:
                print(line)  # 计划先见光，再决定是否执行（删除不可逆）
            if getattr(args, "dry_run", False):
                print("（--dry-run：库目录一个字节都没动）")
                return 0
            deletions = len([op for op in ops if op[0] == "删除"])
            if deletions and not getattr(args, "yes", False):
                print("同步未执行：计划里有 %d 个删除（不可逆）。确认无误请加 --yes 重跑；"
                      "只想预览用 --dry-run。" % deletions, file=sys.stderr)
                return 1
            _counts, done_lines = sync_execute(root, sync_to, names, ops)
            for line in done_lines:
                print(line)
            return 0
        except RuntimeError as exc:
            print("同步失败：%s" % exc, file=sys.stderr)
            return 1
        except OSError as exc:
            print("同步失败（写入出错）：%s" % exc, file=sys.stderr)
            return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws export",
        description="导出工作区（目前只有 --obsidian：导成 Obsidian 笔记）")
    parser.add_argument("--obsidian", metavar="目录",
                        help="把八张 CSV 导成 Obsidian 笔记（每行一笔记 + frontmatter）")
    parser.add_argument("--notes", action="store_true",
                        help="另把 03_面试准备 / 04_知识库 / 00_事实库 的 Markdown "
                             "投影成笔记（保留目录层级；正文按原意搬运，不截断）")
    parser.add_argument("--sync-to", metavar="库目录",
                        help="把新快照镜像进这个**固定**的 Obsidian 库目录（保留其 .obsidian/："
                             "插件与复习进度不受影响；库目录必须已存在且在工作区之外）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印同步计划，不改库目录（配合 --sync-to）")
    parser.add_argument("--yes", action="store_true",
                        help="同步计划里有删除时必须携带（删除不可逆；--dry-run 只预览）")
    parser.add_argument("--workspace", default=None)
    args = parser.parse_args(argv)
    return cmd_export(args)
