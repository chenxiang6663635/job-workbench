# -*- coding: utf-8 -*-
"""原子写：先写临时文件，再 os.replace 落盘。

目的有两个：
1. 读到的一定是完整文件。写 CSV/JSON 时进程被中断（崩溃、断电、强制结束）
   会留下半截文件，而这个文件是用户唯一的数据源——半截即数据损坏。
2. 统一的临时文件前缀，让同步工具（Syncthing / 网盘客户端）能按规则排除半成品，
   避免把写了一半的文件同步到另一台机器。

在所有主流桌面系统上 os.replace 是原子操作（同分区内重命名），
故临时文件与目标文件放同一目录。
"""

from __future__ import annotations

import io
import os

# 统一前缀：同步工具可据此排除（对齐 Syncthing 的 .syncthing. 命名空间思路）
TMP_PREFIX = ".jobws_tmp_"


def _tmp_path(path):
    directory = os.path.dirname(path)
    return os.path.join(directory, TMP_PREFIX + os.path.basename(path))


def _ensure_dir(path):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)


def _commit(path, write_fn):
    """写临时文件 → flush + fsync → os.replace 落盘。"""
    _ensure_dir(path)
    tmp = _tmp_path(path)
    write_fn(tmp)
    os.replace(tmp, path)


def atomic_write_text(path, content, encoding="utf-8"):
    """原子写文本。flush + fsync 保证真正落盘后再改名。"""
    def _write(tmp):
        with io.open(tmp, "w", encoding=encoding, newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

    _commit(path, _write)


def atomic_write_bytes(path, data):
    """原子写二进制（zip / PDF）。"""
    def _write(tmp):
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    _commit(path, _write)


def atomic_write_csv(path, rows, fieldnames, encoding="utf-8-sig", newline=""):
    """原子写 CSV。默认 utf-8-sig（BOM），Excel 直接打开中文不乱码。

    追加场景（如 history.csv）不要用本函数——追加无法原子化，
    且 csv 写入器需要跨调用保持 BOM 逻辑，应在调用方按现有双模式处理。
    """
    import csv

    def _write(tmp):
        with io.open(tmp, "w", encoding=encoding, newline=newline) as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, extrasaction="ignore", restval=""
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

    _commit(path, _write)


def cleanup_tmp(directory):
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
