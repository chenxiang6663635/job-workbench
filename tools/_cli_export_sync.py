# -*- coding: utf-8 -*-
"""`jobws export --obsidian … --sync-to <库目录>`：把新快照**镜像**进固定的 Obsidian 库。

为什么需要它：导出目录带时间戳（「不覆盖」是纪律，历史快照要留档），但手机端真正
要用的是**一个固定名字的库目录**——每次把新快照的内容覆盖进去，同时保住库里的
`.obsidian/`（Spaced Repetition 插件和它的复习进度都在里面）。手动做这件事既繁琐
又容易把 `.obsidian/` 一起删掉，所以给一条命令。

镜像语义与安全边界（三条，都有测试钉住）：
1. **只碰白名单里的顶层条目**（八张表目录 + `README.md` / `jobws.base` + 材料目录，
   由调用方传入）：库里其它文件——你自己的笔记、`.obsidian/`——一个字节都不动；
2. 白名单条目内部按**镜像**语义：快照里没有的旧文件会被删掉（否则题库里删过的题
   会永远留在手机上），删除清单会打印出来；
3. 目标必须**已存在**且**在工作区之外**（与导出同一条守卫）。
"""

from __future__ import print_function

import os

from _cli_export import _inside  # noqa: E402  （与导出同一条「工作区之外」守卫）
from jobws_core import tracker  # noqa: E402  （解析工作区，供守卫用）


def _atomic_copy(src, dst):
    """按字节复制（临时文件 + os.replace：中断不会留下半截文件）。"""
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = os.path.join(parent, ".jobws_tmp_sync.tmp")
    with open(src, "rb") as rf, open(tmp, "wb") as wf:
        wf.write(rf.read())
    os.replace(tmp, dst)


def _walk_rel(base):
    """目录 → {相对路径(正斜杠): 绝对路径}；隐藏目录/文件跳过（与只读端点同口径）。"""
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


def plan_sync(snapshot_root, target, names):
    """计算镜像计划：返回 [(动作, 相对路径), ...]，动作 ∈ {新增, 更新, 删除}。

    纯函数（不写任何东西），CLI 与测试都直接用它断言。白名单条目在快照里缺失时
    **跳过而不删库里的**（例如某个材料目录本来就不存在——删了反而像丢数据）。
    """
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
    return ops


def apply_sync(snapshot_root, target, names, ops):
    """执行计划：新增/更新按字节复制，删除按清单删；删完顺手清掉空目录。"""
    # 空目录也要镜像（比如还没有题的「题库/」）：库里有目录壳，才不会让人以为没导出
    for name in names:
        if os.path.isdir(os.path.join(snapshot_root, name)):
            os.makedirs(os.path.join(target, name), exist_ok=True)
    counts = {"新增": 0, "更新": 0, "删除": 0}
    for action, rel in ops:
        entry, _, rel_in_entry = rel.partition("/")
        parts = rel_in_entry.split("/") if rel_in_entry else []
        src = os.path.join(snapshot_root, entry, *parts)
        dst = os.path.join(target, entry, *parts)
        if action == "删除":
            if os.path.isfile(dst):
                os.remove(dst)
        else:
            _atomic_copy(src, dst)
        counts[action] += 1
    for name in names:
        entry = os.path.join(target, name)
        if not os.path.isdir(entry):
            continue
        for dirpath, dirnames, filenames in os.walk(entry, topdown=False):
            if not dirnames and not filenames and dirpath != entry:
                os.rmdir(dirpath)
    return counts


def sync_to_vault(snapshot_root, target, names, workspace, dry_run=False):
    """把快照镜像进库目录，返回要打印的行（CLI 逐行打印）。

    前置检查不过就抛 RuntimeError（CLI 按「同步失败」、退出码 1 处理）：
    - 目标必须**已存在**（库目录是你先在 Obsidian 里建好的，不是我们替你造的）；
    - 目标必须**在工作区之外**（与导出同一条守卫：写进工作区会污染材料，还会被
      材料投影重复收录）。
    """
    if not os.path.isdir(target):
        raise RuntimeError("--sync-to 的库目录不存在（先在 Obsidian 里建好它）：%s" % target)
    if _inside(os.path.realpath(target),
               os.path.realpath(tracker.resolve_ws(workspace))):
        raise RuntimeError("--sync-to 的库目录必须在工作区之外：%s" % target)
    ops = plan_sync(snapshot_root, target, names)
    counts = {"新增": 0, "更新": 0, "删除": 0}
    for action, _rel in ops:
        counts[action] += 1
    lines = ["同步计划：新增 %d / 更新 %d / 删除 %d" % (
        counts["新增"], counts["更新"], counts["删除"])]
    for action, rel in ops:
        lines.append("  %s %s" % (action, rel))
    if dry_run:
        lines.append("（--dry-run：库目录一个字节都没动）")
        return lines
    if ops:
        counts = apply_sync(snapshot_root, target, names, ops)
    lines.append("已同步 → %s（新增 %d / 更新 %d / 删除 %d；`.obsidian/` 与白名单外的文件未动）"
                 % (target, counts["新增"], counts["更新"], counts["删除"]))
    return lines
