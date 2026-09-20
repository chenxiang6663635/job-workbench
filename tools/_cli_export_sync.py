# -*- coding: utf-8 -*-
"""`jobws export --obsidian … --sync-to <库目录>`：把新快照**镜像**进固定的 Obsidian 库。

为什么需要它：导出目录带时间戳（「不覆盖」是纪律，历史快照要留档），但手机端真正
要用的是**一个固定名字的库目录**——每次把新快照的内容覆盖进去，同时保住库里的
`.obsidian/`（Spaced Repetition 插件和它的复习进度都在里面）。

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
   `os.replace` 退避重试）——不在这自造更弱的原子写原语。
"""

from __future__ import print_function

import os

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
    """
    _check_target(target, workspace)
    ops = []
    for name in names:
        src_entry = os.path.join(snapshot_root, name)
        dst_entry = os.path.join(target, name)
        if os.path.isfile(src_entry):
            if not os.path.isfile(dst_entry):
                ops.append(("新增", name))
            elif not _same_bytes(src_entry, dst_entry):
                ops.append(("更新", name))
            continue
        if not os.path.isdir(src_entry):
            continue
        src_files = _walk_rel(src_entry)
        dst_files = _walk_rel(dst_entry)
        for rel in sorted(src_files):
            if rel not in dst_files:
                ops.append(("新增", "%s/%s" % (name, rel)))
            elif not _same_bytes(src_files[rel], dst_files[rel]):
                ops.append(("更新", "%s/%s" % (name, rel)))
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
