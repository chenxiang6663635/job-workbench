# -*- coding: utf-8 -*-
"""快照的**读侧**：清单、条目几何、校验与演练（写侧在 `snapshot_io.py`）。

拆开的理由与别处同款：`snapshot_io` 加了批末审查的四处收紧后越过 300 行水位，按纪律只能拆
（存量债只许变小，新文件也不许一上来就超）。切面也自然——这里全是"只看不写"的判定，
逐条都能单测；`snapshot_io` 那边是打包与落盘。

两处**判定顺序**是这台机器的要害（批末零上下文审查的 CRITICAL）：

- 条目路径必须**先归一化再判定**：`ws/config/./imap.json` 与 `ws//config/imap.json` 原先
  同时绕过"含 `..`"与"凭证名单精确匹配"两道闸，而落盘时由 OS 归一化后正是
  `config/imap.json`——**明文邮箱授权码被还原回工作区**。
- 末段带尾随空格 / 点的条目直接拒绝：Windows 把 `imap.json ` 与 `imap.json.` 解析成
  `imap.json`，同样能绕过精确匹配。
"""

from __future__ import annotations

import os
import posixpath
import zipfile

from apierror import ApiError

# 快照清单与文件遍历的**唯一事实源**在 system.py（它同时守着"凭证不进包"）。
from routers.system import (
    EXCLUDE_DIRS,
    EXCLUDE_PREFIX,
    EXCLUDE_REL,
    EXCLUDE_SUFFIX,
    _iter_files,
    _snapshot_dir,
)

# 上限：单份快照的条目数与解压总量。在写第一个字节之前判定（见 open_validated），
# 所以不存在"先写一半再拒"的状态。
MAX_ENTRIES = 2000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
LIST_LIMIT = 50
KEPT_EXAMPLES = 5


def safe_name(name):
    """快照名只接受"快照目录里的一个文件名"，不接受任何路径成分。"""
    raw = (name or "").strip()
    illegal = (not raw or not raw.lower().endswith(".zip") or raw in (".", "..")
               or any(part in raw for part in ("/", "\\", ":")))
    if illegal:
        raise ApiError(400, "sys.snapshotName",
                       "快照名不合法（只接受快照目录里的 .zip 文件名）", name=raw)
    return raw


def list_entries(ws):
    """快照目录里的 zip 清单，新的在前。"""
    snap_dir = _snapshot_dir(ws)
    if not os.path.isdir(snap_dir):
        return snap_dir, []
    items = []
    for name in os.listdir(snap_dir):
        if not name.endswith(".zip"):
            continue
        full = os.path.join(snap_dir, name)
        try:
            stat = os.stat(full)
        except OSError:
            continue  # 恰好被淘汰/删掉了：跳过，不让清单整体失败
        items.append({"name": name, "path": full, "size": stat.st_size,
                      "mtime": stat.st_mtime})
    # 名字参与排序：同一微秒内落两份时顺序也要稳定（清单是给用户看的）
    items.sort(key=lambda item: (item["mtime"], item["name"]), reverse=True)
    return snap_dir, items


def normalize_rel(rel):
    """条目相对路径归一化：`a/./b`、`a//b`、`a/b` 归成同一形状。"""
    return posixpath.normpath(rel.replace("\\", "/"))


def entry_rel(entry_name, ws_name):
    """条目名 → 工作区内相对路径（已归一化）；越界/不属于本工作区的一律拒绝。

    第一段等于工作区名时剥掉它（写入侧就是这么写的）；对不上则按整体处理，随后仍要通过
    同一套越界检查——`C:evil.txt` 会在"含冒号"这一步被拦下。
    """
    raw = entry_name.replace("\\", "/")
    first, _, rest = raw.partition("/")
    rel = rest if first == ws_name and rest else raw
    segments = rel.split("/")
    if ".." in segments or rel.startswith("/") or not rel or ":" in rel:
        raise ApiError(400, "sys.snapshotEntry",
                       "快照里有越出工作区的条目：%s" % entry_name, entry=entry_name)
    rel = normalize_rel(rel)
    tail = rel.split("/")[-1]
    if (rel in ("", ".", "..") or rel.startswith("../") or rel.startswith("/")
            or ":" in rel or tail != tail.rstrip(" .")):
        raise ApiError(400, "sys.snapshotEntry",
                       "快照里有越出工作区的条目：%s" % entry_name, entry=entry_name)
    return rel


def is_excluded(rel):
    """排除凭证与运行时产物（`rel` 必须是 `normalize_rel` 之后的形状）。"""
    if rel in EXCLUDE_REL:
        return True
    segments = rel.split("/")
    if any(part in EXCLUDE_DIRS for part in segments[:-1]):
        return True
    name = segments[-1]
    return (any(name.startswith(prefix) for prefix in EXCLUDE_PREFIX)
            or os.path.splitext(name)[1].lower() in EXCLUDE_SUFFIX)


def _entries_of(zf, ws_name):
    """已打开的 zip → 逐条 `(rel, ZipInfo)`；同时过完整性、上限、越界三道闸。"""
    broken = zf.testzip()
    if broken is not None:
        raise ApiError(422, "sys.snapshotCorrupt", "快照内文件校验失败：%s" % broken)
    infos = [info for info in zf.infolist() if not info.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ApiError(413, "sys.snapshotTooManyEntries",
                       "快照条目过多（%d，上限 %d）" % (len(infos), MAX_ENTRIES),
                       count=len(infos), limit=MAX_ENTRIES)
    total = sum(info.file_size for info in infos)
    if total > MAX_TOTAL_BYTES:
        raise ApiError(413, "sys.snapshotTooLarge",
                       "快照解压总量过大（%d 字节，上限 %d）" % (total, MAX_TOTAL_BYTES),
                       size=total, limit=MAX_TOTAL_BYTES)
    kept = []
    for info in infos:
        rel = entry_rel(info.filename, ws_name)
        if is_excluded(rel):
            continue
        kept.append((rel, info))
    return kept


def open_validated(path, ws_name):
    """打开并校验快照，返回 `(ZipFile, entries)`；调用方负责关闭。"""
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ApiError(422, "sys.snapshotCorrupt",
                       "快照文件读不出来（可能已损坏或被截断）：%s" % exc)
    try:
        entries = _entries_of(zf, ws_name)
    except BaseException:
        zf.close()
        raise
    return zf, entries


def validate(path, ws_name):
    """只校验不读内容：坏包在被拒时一个字都没动，没必要占着锁。"""
    zf, _entries = open_validated(path, ws_name)
    zf.close()


def read_entry(zf, info):
    """读单条目内容；解压失败折算成"快照损坏"而不是 500。"""
    try:
        blob = zf.read(info)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ApiError(422, "sys.snapshotCorrupt",
                       "快照内条目解压失败：%s（%s）" % (info.filename, exc))
    if len(blob) != info.file_size:
        raise ApiError(422, "sys.snapshotCorrupt",
                       "快照内条目长度与索引不符：%s" % info.filename)
    return blob


def current_bytes(full):
    """当前文件内容；读不出来时返回 None（按"需要覆盖"处理，但别因此炸掉演练）。"""
    try:
        with open(full, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def preview(path, ws, ws_name):
    """演练：分类快照条目与当前状态的差异，零写入。"""
    counts = {"overwrite": 0, "add": 0, "same": 0}
    total_bytes = 0
    rels = set()
    zf, entries = open_validated(path, ws_name)
    try:
        for rel, info in entries:
            rels.add(rel)  # 归一化形状，与下面 _iter_files 的口径一致
            total_bytes += info.file_size
            full = os.path.join(ws, rel)
            if not os.path.isfile(full):
                counts["add"] += 1
                continue
            if current_bytes(full) == read_entry(zf, info):
                counts["same"] += 1
            else:
                counts["overwrite"] += 1
    finally:
        zf.close()

    kept = [os.path.relpath(full, ws).replace(os.sep, "/") for full in _iter_files(ws)]
    kept = sorted(normalize_rel(rel) for rel in kept if rel not in rels)

    return {
        "overwrite": counts["overwrite"],
        "add": counts["add"],
        "same": counts["same"],
        "total": sum(counts.values()),
        "bytes": total_bytes,
        "notInSnapshot": len(kept),
        "keptExamples": kept[:KEPT_EXAMPLES],
    }
