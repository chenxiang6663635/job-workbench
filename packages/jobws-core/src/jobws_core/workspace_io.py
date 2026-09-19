# -*- coding: utf-8 -*-
"""共享写入原语：原子写 / 目录指纹 / 锁名工厂（批 8，四端唯一入口）。

为什么单独一个模块：CLI（tools/）、MCP（mcp/jobws_mcp/）、桌面端后端（web/backend/）
原本各自实现同一件事——原子写有 3 份（web/backend/atomicio.py、tracker/_core.py 的
CSV 版、prefs.py 的 mkstemp 版），还有 1 处裸写（report.py 的看板落盘）；锁路径有
6 处手拼（其中 tracker.lock 在 applications.py 里出现 4 次）。批 8 收敛到这里：
四端一律 import 本模块，禁止再各写一套。

与 web/backend/atomicio.py 的关系：本模块 = 那份 + tracker 的 CSV 版 + Windows
重试的合并体；backend 那份保留为薄转发（既有 import 路径零改动）。

纪律（与 filelock 同款立场）：
- path 应当是数据文件（如 tracker.csv），锁文件请用 lock_path() 拿专用路径；
- 临时文件与目标同目录（os.replace 同分区才原子）；
- 指纹只看 (size, mtime_ns)，不做全内容哈希——它是"变了没有"的判据，不是校验和。

（2026-09-17 由 `tools/workspace_io.py` 原样迁入本包；旧路径保留为转发 shim。）
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import time

# 统一前缀：同步工具（Syncthing / 网盘客户端）可据此排除半成品，
# 导出与快照也用它排除（web/backend/routers/system.py 的 EXCLUDE_PREFIX 同源）。
TMP_PREFIX = ".jobws_tmp_"

# Windows 上 os.replace 会因目标被独占（Excel 打开 CSV、杀软扫描、索引器）抛
# PermissionError；短暂退避重试是这类冲突的标准解法。
_REPLACE_RETRIES = 5
_REPLACE_BACKOFF_SECONDS = 0.05

# 锁名表：与四端既有实现逐字一致（改这里等于改全仓约定）。
# kind → (工作区相对目录, 锁文件名)
_LOCK_KINDS = {
    "tracking": ("05_投递追踪", "tracker.lock"),
    "jobs": ("01_岗位池", ".jobs.lock"),
    "resume": ("02_简历工坊", "resume.lock"),
    "imap": ("config", "imap.lock"),
    "provider": ("config", "provider.lock"),
}

# 默认纳入指纹的业务目录（读不到就跳过，不报错——空工作区也要有稳定指纹）
# 04_知识库 于 2026-09-18 补入：笔记页（只读浏览）依赖指纹实现"外部编辑后刷新"，
# 不补的话在 Obsidian 改完速查卡切回来还是旧内容。
DEFAULT_TRACKED_DIRS = ("05_投递追踪", "01_岗位池", "02_简历工坊", "03_面试准备", "04_知识库")

# 纳入指纹的文件类型（业务数据都是这些；锁与临时文件天然排除）
DEFAULT_EXTS = (".csv", ".md", ".json")


# --- 原子写 ---------------------------------------------------------------


def _tmp_path(path: str) -> str:
    return os.path.join(os.path.dirname(path), TMP_PREFIX + os.path.basename(path))


def _ensure_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)


def _replace_with_retry(tmp: str, path: str, retries: int, sleep) -> None:
    """os.replace + 短暂退避重试；全部失败后抛最后一次异常。"""
    last = None
    for attempt in range(max(1, retries)):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:  # 目标被占用：退避后再试
            last = exc
            sleep(_REPLACE_BACKOFF_SECONDS * (attempt + 1))
    raise last  # type: ignore[misc]


def _commit(path: str, write_fn, retries: int, sleep) -> None:
    """写临时文件 → flush + fsync → os.replace 落盘（重试见上）。

    失败（含重试耗尽与写入异常）时清掉临时文件：残留虽被导出与指纹排除，
    但会长期堆在用户工作区里（独立审查 m1）。
    """
    _ensure_dir(path)
    tmp = _tmp_path(path)
    try:
        write_fn(tmp)
        _replace_with_retry(tmp, path, retries, sleep)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: str,
    content: str,
    encoding: str = "utf-8",
    retries: int = _REPLACE_RETRIES,
    sleep=time.sleep,
) -> None:
    """原子写文本。flush + fsync 保证真正落盘后再改名。"""

    def _write(tmp: str) -> None:
        with io.open(tmp, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    _commit(path, _write, retries, sleep)


def atomic_write_bytes(
    path: str,
    data: bytes,
    retries: int = _REPLACE_RETRIES,
    sleep=time.sleep,
) -> None:
    """原子写二进制（zip / PDF / 图标）。"""

    def _write(tmp: str) -> None:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    _commit(path, _write, retries, sleep)


def atomic_write_csv(
    path: str,
    rows,
    fieldnames,
    encoding: str = "utf-8-sig",
    newline: str = "",
    retries: int = _REPLACE_RETRIES,
    sleep=time.sleep,
) -> None:
    """原子写 CSV。默认 utf-8-sig（BOM），Excel 直接打开中文不乱码。

    restval="" + None→"" 双保险：旧文件缺新增列时补空列，None 不会落盘成 "None"。
    追加场景（如 history.csv）不要用本函数——追加无法原子化，按调用方双模式处理。
    """

    def _write(tmp: str) -> None:
        with io.open(tmp, "w", encoding=encoding, newline=newline) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, extrasaction="ignore", restval=""
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
            handle.flush()
            os.fsync(handle.fileno())

    _commit(path, _write, retries, sleep)


def cleanup_tmp(directory: str) -> int:
    """清理目录里残留的临时文件（上次崩溃留下的）。返回清理数量。"""
    if not os.path.isdir(directory):
        return 0
    removed = 0
    for name in os.listdir(directory):
        if name.startswith(TMP_PREFIX):
            full = os.path.join(directory, name)
            try:
                os.remove(full)
                removed += 1
            except OSError:
                pass
    return removed


# --- 锁名工厂 --------------------------------------------------------------


def lock_path(workspace: str, kind: str) -> str:
    """统一锁文件路径（纯计算，不建目录——建不建由调用方决定）。

    kind 见 _LOCK_KINDS：tracking / jobs / resume / imap / provider。
    未知 kind 直接报错：宁可炸在开发期，不要悄悄锁错文件。
    """
    if kind not in _LOCK_KINDS:
        raise ValueError(
            "未知锁类型：%s（可选：%s）" % (kind, " / ".join(sorted(_LOCK_KINDS)))
        )
    rel, name = _LOCK_KINDS[kind]
    return os.path.join(workspace, rel, name)


# --- 目录指纹 --------------------------------------------------------------


def dir_fingerprint(
    workspace: str,
    rel_dirs=None,
    exts=DEFAULT_EXTS,
) -> str:
    """工作区数据指纹：对纳入目录下所有数据文件的 (相对路径, size, mtime_ns) 取摘要。

    用途：桌面端判断"外部（CLI / MCP / 插件）是否写过数据"——变了才重拉，
    没变就不打扰。只看 size+mtime 而非内容哈希：一次 stat 的开销，够用且便宜。
    空工作区 / 目录缺失时返回稳定值（同一空状态 → 同一指纹）。
    """
    roots = rel_dirs if rel_dirs is not None else DEFAULT_TRACKED_DIRS
    entries = []
    for rel in roots:
        base = os.path.join(workspace, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                # 排除簿记文件：临时文件、锁、以及 "." 开头的（如 .schema.json——
                # 自检补写它会造成假阳性「数据变了」，独立审查 m4）
                if name.startswith(".") or name.endswith(".lock"):
                    continue
                if not name.endswith(tuple(exts)):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    stat = os.stat(full)
                except OSError:
                    continue  # 扫描间隙被删：跳过一次，下次指纹自会变化
                rel_path = os.path.relpath(full, workspace).replace("\\", "/")
                entries.append("%s|%d|%d" % (rel_path, stat.st_size, stat.st_mtime_ns))
    digest = hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()
    return digest[:16]
