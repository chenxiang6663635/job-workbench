# -*- coding: utf-8 -*-
"""`jobws export --obsidian … --sync-to <库目录>`：把新快照**镜像**进固定的 Obsidian 库。

为什么需要它：导出目录带时间戳（「不覆盖」是纪律，历史快照要留档），但手机端真正
要用的是**一个固定名字的库目录**——每次把新快照的内容覆盖进去，同时保住库里的
`.obsidian/`（插件与设置）与笔记里的复习注释（进度在注释里，见边界 6——不在
`.obsidian/`，这是 2026-09-20 查证官方文档后的更正）。

契约（分两步，CLI 按此编排）：
1. `sync_plan(...)`：守卫 + 计算镜像计划，返回 (ops, lines)。**只读**；守卫不过抛
   RuntimeError（CLI → 「同步失败」、退出码 1）；计划先打印给用户看。
2. `sync_execute(...)`：执行计划（新增/更新按字节原子复制、删除按清单删、清掉因删除
   而变空的目录），返回 (counts, lines)。

安全边界（都有测试钉住）：
1. **只碰白名单顶层条目**（由调用方传入：八张表目录 + README/jobws.base + 材料目录）；
   库里 `.obsidian/` 与白名单外的文件不在任何读写删路径上；
2. 白名单条目内部按**镜像**语义：快照里没有的旧文件会删——这是「托管目录」的设计，
   但因为不可逆，**CLI 侧有删除就要求 `--yes` 确认**（本模块只如实执行计划）；
3. 白名单条目在快照里缺失时**跳过而不删库里的**（例如某材料目录本来就不存在）；
4. 目标必须**已存在**（且是目录）、**在工作区之外**（与导出同一条守卫）；
5. 复制走 `workspace_io.atomic_write_bytes`（按目标唯一命名的临时文件 + Windows
   `os.replace` 退避重试）——不在这自造更弱的原子写原语；
6. **复习进度优先于镜像**：spaced-repetition 把排程写进笔记本身（每张卡下面追加
   `<!--SR:!到期日,间隔,易度-->`）。比较时先剥掉这类注释再比：字节不同但"剥完一致"
   的文件**跳过、不覆盖**——镜像若把它当"更新"，手机上刷出来的进度会被电脑快照
   整批清零。只有正文真的改了才更新（那一张卡的进度会归零，属可接受代价）。
"""

from __future__ import print_function

import io
import os
import re

from _cli_export import _inside  # noqa: E402  （与导出同一条「工作区之外」守卫）
from jobws_core import tracker  # noqa: E402  （解析工作区，供守卫用）
from jobws_core import workspace_io  # noqa: E402  （原子写：唯一临时名 + 退避重试）


def _walk_rel(base):
    """目录 → {相对路径(正斜杠): 绝对路径}。

    隐藏目录/文件跳过——这与只读端点、材料投影是三处同口径实现（改口径要三处一起）。
    """
    out = {}
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(n for n in dirnames if not n.startswith((".", "__")))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            out[os.path.relpath(full, base).replace(os.sep, "/")] = full
    return out


def _same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


# spaced-repetition 的排程注释：`<!--SR:!到期日,间隔,易度-->`（同行模式也匹配；
# 插件实际只把注释插在卡片行之后——独占下一行或行尾，不插行中间）
_SR_COMMENT_RE = re.compile(r"<!--SR:[^>]*-->")


def _strip_sr_notes(text):
    """"正文指纹"：删掉复习注释、注释单独占的行与所有空行，再去行尾空白。

    为什么空行也不计：注释插在卡片行后面，是否顺带留下空行取决于插件版本 / 同行模式——
    空行没有信息量，两边统一不算，比较才对得上。代价是"只改了空行"的差异检测不出来，
    可以接受（产物是生成的，改了内容必然改到文字行）。
    """
    lines = []
    for line in text.splitlines():
        cleaned = _SR_COMMENT_RE.sub("", line).rstrip()
        if cleaned.strip() == "":
            continue
        lines.append(cleaned)
    return "\n".join(lines)


def _same_content(a, b):
    """两文件"正文层面"是否一致（剥掉复习注释后比）。字节不同时才走到这里。

    读不出 UTF-8（二进制 / 损坏）就退回字节比较——不猜；回退的后果 = 该文件照旧
    按字节判"更新"并覆盖（它已不可解析，保它没有意义）。
    """
    try:
        with io.open(a, "r", encoding="utf-8") as fa:
            text_a = fa.read()
        with io.open(b, "r", encoding="utf-8") as fb:
            text_b = fb.read()
    except (OSError, UnicodeDecodeError):
        return _same_bytes(a, b)
    return _strip_sr_notes(text_a) == _strip_sr_notes(text_b)


def _classify(src, dst):
    """文件级判定：'未变' / '仅进度' / '更新'（'更新' = 正文真的变了，需要覆盖）。"""
    if _same_bytes(src, dst):
        return "未变"
    if _same_content(src, dst):
        return "仅进度"  # 只差复习注释/空白：保留目的端——进度在那边
    return "更新"


def _check_target(target, workspace):
    """守卫：目标必须是已存在的目录，且在工作区之外。"""
    if os.path.exists(target) and not os.path.isdir(target):
        raise RuntimeError("--sync-to 的目标是一个文件，不是目录：%s" % target)
    if not os.path.isdir(target):
        raise RuntimeError("--sync-to 的库目录不存在（先在 Obsidian 里建好它）：%s" % target)
    if _inside(os.path.realpath(target),
               os.path.realpath(tracker.resolve_ws(workspace))):
        raise RuntimeError("--sync-to 的库目录必须在工作区之外：%s" % target)


def sync_plan(snapshot_root, target, names, workspace, include_notes=False):
    """守卫 + 计算镜像计划。返回 (ops, lines)：ops = [(动作, 相对路径), ...]。

    动作 ∈ {新增, 更新, 删除}；本函数**只读**。计划由 CLI 先打印、再决定是否执行
    （有删除时 CLI 要求 --yes）。白名单条目在快照里缺失时跳过、不删库里的对应物。
    "字节不同、剥掉复习注释与空白后一致"的文件**不进 ops**（视为未变、保留库里的版本），
    只在 lines 里报个数——那是手机上刷出来的进度，覆盖掉不可接受。
    """
    _check_target(target, workspace)
    ops = []
    kept = 0  # 只差注释/空白 → 保留库里的（进度在那边）
    for name in names:
        src_entry = os.path.join(snapshot_root, name)
        dst_entry = os.path.join(target, name)
        if os.path.isfile(src_entry):
            if not os.path.isfile(dst_entry):
                ops.append(("新增", name))
            else:
                verdict = _classify(src_entry, dst_entry)
                if verdict == "更新":
                    ops.append(("更新", name))
                elif verdict == "仅进度":
                    kept += 1
            continue
        if not os.path.isdir(src_entry):
            continue
        src_files = _walk_rel(src_entry)
        dst_files = _walk_rel(dst_entry)
        for rel in sorted(src_files):
            if rel not in dst_files:
                ops.append(("新增", "%s/%s" % (name, rel)))
                continue
            verdict = _classify(src_files[rel], dst_files[rel])
            if verdict == "更新":
                ops.append(("更新", "%s/%s" % (name, rel)))
            elif verdict == "仅进度":
                kept += 1
        for rel in sorted(dst_files):
            if rel not in src_files:
                ops.append(("删除", "%s/%s" % (name, rel)))
    counts = {"新增": 0, "更新": 0, "删除": 0}
    for action, _rel in ops:
        counts[action] += 1
    lines = ["同步计划：新增 %d / 更新 %d / 删除 %d" % (
        counts["新增"], counts["更新"], counts["删除"])]
    for action, rel in ops:
        lines.append("  %s %s" % (action, rel))
    if kept:
        lines.append("保留复习进度：%d 篇笔记只差排程注释或空白（空行 / 行尾空格），"
                     "未覆盖（正文有改动的才会更新）" % kept)
    if not include_notes:
        from _cli_export_notes import NOTE_DIRS  # 函数内 import：避免环状依赖
        stale = [d for d in NOTE_DIRS
                 if d not in names and os.path.isdir(os.path.join(target, d))]
        if stale:
            lines.append("提示：库目录里有上次 --notes 同步的材料目录（%s），"
                         "本次没开 --notes，它们不会更新也不会删除。" % "、".join(stale))
    return ops, lines


def sync_execute(snapshot_root, target, names, ops):
    """执行计划：新增/更新按字节原子复制；删除按清单删，并清掉因此变空的目录。"""
    counts = {"新增": 0, "更新": 0, "删除": 0}
    touched = set()
    for action, rel in ops:
        entry, _, rel_in_entry = rel.partition("/")
        parts = rel_in_entry.split("/") if rel_in_entry else []
        src = os.path.join(snapshot_root, entry, *parts)
        dst = os.path.join(target, entry, *parts)
        if action == "删除":
            if os.path.isfile(dst):
                os.remove(dst)
                touched.add(os.path.dirname(dst))
        else:
            with open(src, "rb") as handle:
                workspace_io.atomic_write_bytes(dst, handle.read())
        counts[action] += 1
    # 只清理「因本次删除而变空」的目录（从被删文件的父目录向上，到条目根为止）——
    # 不做全局空目录清扫：没进计划的目录不该消失
    for dirpath in sorted(touched, key=len, reverse=True):
        entry_root = None
        for name in names:
            cand = os.path.join(target, name)
            if dirpath.startswith(cand + os.sep) or dirpath == cand:
                entry_root = cand if entry_root is None or len(cand) > len(entry_root) else entry_root
        stop = entry_root or target
        probe = dirpath
        while probe.startswith(stop + os.sep) and probe != stop:
            try:
                os.rmdir(probe)  # 非空会抛 OSError → 停
            except OSError:
                break
            probe = os.path.dirname(probe)
    # 空条目壳也要在（比如还没有题的「题库/」）：有目录壳才不会让人以为没导出
    for name in names:
        if os.path.isdir(os.path.join(snapshot_root, name)):
            os.makedirs(os.path.join(target, name), exist_ok=True)
    lines = ["已同步 → %s（新增 %d / 更新 %d / 删除 %d）"
             % (target, counts["新增"], counts["更新"], counts["删除"])]
    return counts, lines
