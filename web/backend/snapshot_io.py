# -*- coding: utf-8 -*-
"""快照的校验、演练与还原（HTTP 层之外的实现）。

拆出来的理由与 `atomicio` 同款：`routers/snapshot.py` 是协议层（端点 + 响应组装），
这里的每一个函数都能被单独调用与单测——校验规则（完整性、越界、条目数与解压总量）
尤其需要这种可测性，它们是"坏包不许留半截改动"这条承诺的兑现处。

三条纪律：

- **演练零写入**：`preview` 只读。「我先演练一下」如果会留下痕迹，演练就没有意义。
- **还原不删东西**：只覆盖同名 + 补齐缺失，快照里没有的当前文件保留不动，
  条数如实回报并列出示例——单机场景里"删除"是唯一不可逆的动作。
- **先落回滚点**：还原前自动打一份当前状态的快照，它是"还原错了"的唯一退路。

快照内条目的路径口径与写入侧（`routers.system._iter_files`）一致：**相对工作区父目录**，
因此第一段是工作区名（`ws-ok/01_岗位池/a.md`）。这不是装饰——还原时按它确定落点，
对不上就拒绝，而不是猜。
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime

import atomicio
from jobws_core import workspace_io
from lockctx import locked
from apierror import ApiError

# 快照清单与文件遍历的**唯一事实源**在 system.py（它同时守着"凭证不进包"）：
# 拷一份到这里等于给将来的漂移预授权。它带下划线是因为 system.py 的水位不允许
# 再加一个公开别名——宁可跨模块读一个私有名，也不要两份清单。
from routers.system import (
    EXCLUDE_DIRS,
    EXCLUDE_PREFIX,
    EXCLUDE_REL,
    EXCLUDE_SUFFIX,
    _iter_files,
    _snapshot_dir,
)

# 上限：单份快照的条目数与解压总量。真数据是 Markdown/CSV，256MB 已远超实际；
# 设它们是为了坏包/炸弹不至于把后端拖死。
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


def _entry_rel(entry_name, ws_name):
    """条目名 → 工作区内相对路径；越界/不属于本工作区的一律拒绝。

    规则：第一段等于工作区名时剥掉它（写入侧就是这么写的）；对不上则按整体处理，
    随后仍要通过同一套越界检查——`C:evil.txt` 会在"含冒号"这一步被拦下。
    """
    raw = entry_name.replace("\\", "/")
    first, _, rest = raw.partition("/")
    rel = rest if first == ws_name and rest else raw
    segments = rel.split("/")
    bad = (".." in segments or rel.startswith("/") or not rel or ":" in rel)
    if bad:
        raise ApiError(400, "sys.snapshotEntry",
                       "快照里有越出工作区的条目：%s" % entry_name, entry=entry_name)
    return rel


def _is_excluded(rel):
    """还原侧同样排除凭证与运行时产物（快照是用户可手改的文件，入口要自证）。"""
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
        raise ApiError(422, "sys.snapshotCorrupt",
                       "快照内文件校验失败：%s" % broken)
    infos = [info for info in zf.infolist() if not info.is_dir()]
    if len(infos) > MAX_ENTRIES:
        # 与"解压总量超限"分成两个 code：它们的参数集合不同（条目数没有 size），
        # 合成一个 code 会让 `test_error_code_params` 的"同码同参"断言失败——
        # 那条断言不是形式主义：同一个 code 在两处传不同参数，必有一处文案缺值。
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
        rel = _entry_rel(info.filename, ws_name)
        if _is_excluded(rel):
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
            rels.add(rel)
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

    kept = [os.path.relpath(full, ws).replace(os.sep, "/")
            for full in _iter_files(ws)]
    kept = sorted(rel for rel in kept if rel not in rels)

    return {
        "overwrite": counts["overwrite"],
        "add": counts["add"],
        "same": counts["same"],
        "total": sum(counts.values()),
        "bytes": total_bytes,
        "notInSnapshot": len(kept),
        "keptExamples": kept[:KEPT_EXAMPLES],
    }


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _pack(ws, snap_dir, prefix):
    """把当前工作区打成一份快照（还原前的回滚点复用它，口径与备份一致）。"""
    if not os.path.isdir(snap_dir):
        os.makedirs(snap_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    tmp_path = os.path.join(snap_dir, atomicio.TMP_PREFIX + "pre-%s.zip" % stamp)
    target = os.path.join(snap_dir, "%s-%s.zip" % (prefix, stamp))
    count = 0
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full in _iter_files(ws):
                zf.write(full, os.path.relpath(full, os.path.dirname(ws)))
                count += 1
        os.replace(tmp_path, target)
    except OSError as exc:
        _unlink(tmp_path)
        raise ApiError(500, "sys.snapshotFailed",
                       "还原前的留痕写不出来（%s）——已中止，工作区未做任何改动" % exc)
    return os.path.basename(target), count


def restore(path, ws, ws_name):
    """还原：锁内先落回滚点，再覆盖同名 + 补齐缺失（从不删除）。"""
    snap_dir = _snapshot_dir(ws)
    tracking = workspace_io.lock_path(ws, "tracking")
    jobs = workspace_io.lock_path(ws, "jobs")
    for lock_file in (tracking, jobs):
        os.makedirs(os.path.dirname(lock_file), exist_ok=True)

    # 锁序：tracking → jobs。全仓没有第二处同时持两把锁的代码路径，因此不会互等。
    with locked(tracking), locked(jobs):
        rollback, rollback_files = _pack(ws, snap_dir, "%s-pre" % ws_name)
        counts = {"restored": 0, "added": 0, "same": 0}
        written = 0
        zf, entries = open_validated(path, ws_name)
        try:
            for rel, info in entries:
                full = os.path.join(ws, rel)
                blob = read_entry(zf, info)
                written += len(blob)
                if written > MAX_TOTAL_BYTES:
                    # 与上面那条同码同参（size + limit）：索引里报的体积可以撒谎，
                    # 这条是按**实际读出来的字节**再核一次
                    raise ApiError(413, "sys.snapshotTooLarge",
                                   "快照解压总量超出上限（已读 %d 字节，上限 %d）"
                                   % (written, MAX_TOTAL_BYTES),
                                   size=written, limit=MAX_TOTAL_BYTES)
                existed = os.path.isfile(full)
                if existed and current_bytes(full) == blob:
                    counts["same"] += 1
                    continue
                parent = os.path.dirname(full)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                workspace_io.atomic_write_bytes(full, blob)
                counts["restored" if existed else "added"] += 1
        finally:
            zf.close()

    return {
        "ok": True,
        "restored": counts["restored"],
        "added": counts["added"],
        "same": counts["same"],
        "preRestoreSnapshot": rollback,
        "preRestoreFiles": rollback_files,
        "snapshotDir": snap_dir,
    }
