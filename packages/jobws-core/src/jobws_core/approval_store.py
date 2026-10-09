# -*- coding: utf-8 -*-
"""令牌簿记的**文件层**：原子写 / 读取 / 取走（claim）/ 还原（restore）/ 过期清理。

从 `approval.py` 拆出（2026-10-09 审计 1.1-4 的三处修正撞上 300 行规模水位，
按「超线即拆」把字节层与协议层分开）：协议语义（一次性 / 过期 / 绑定 / 指纹）
仍在 `approval.py`；本模块只管**字节怎么落、怎么取、怎么清**——全部函数接收
路径参数，目录从哪来由调用方决定（所以 `approval._store_dir` 这个既有 patch
点不动，既有测试的目录隔离夹具继续有效）。

三条性质（`tests/test_approval_store.py` 逐条钉住）：

- **原子写**：先在同目录写临时文件再 `os.replace`——崩溃或序列化失败都不留
  半截，覆盖写也不会先把旧令牌截成空文件（旧实现 `open(path, "w")` 正是如此）；
- **取走 = 原子重命名**（`<token>.json.running`）：同一令牌的并发 apply 只有
  一个赢家；**锁等待超时可以还原**（restore）——此时一个字节都没写进工作区，
  「稍后重试」才不是空话；
- **过期清理**：每次写新令牌顺手清一次过期项与**陈旧**残片——令牌里带业务
  载荷（明文），不该在系统临时目录里无限滞留。陈旧判据是 mtime 超过宽限期
  （宽限期内可能是另一进程正在执行的 apply，不能误杀）。
"""

from __future__ import annotations

import json
import os
import time

RUNNING_SUFFIX = ".running"

# .running / .tmp 残片的宽限期（秒）：apply 正常耗时以秒计，1 小时足够覆盖
# 慢机器的锁等待上限，又不会让崩溃残片无限滞留。
RUNNING_GRACE_SECONDS = 3600


def write_record(path, record):
    """原子写令牌：同目录临时文件 + `os.replace`；顺手清理同目录的过期项。

    顺序是「先序列化 → 再落临时文件 → 最后 replace」：任何一步失败（例如载荷
    不可 JSON 化）都不会破坏路径上既有的令牌文件。
    """
    purge_expired(os.path.dirname(path))
    blob = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(blob)
    os.replace(tmp, path)


def read_record(path):
    """读令牌记录；文件不可读或 JSON 坏时把 (OSError, ValueError) 抛给调用方。"""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def claim(path):
    """取走令牌（原子重命名到 `<path>.running`），返回取走后的路径。

    并发下只有一个调用能成功——`os.replace` 的原子性保证「一份令牌一个赢家」；
    失败（另一个进程已取走）抛 OSError，由调用方译成 `lost`。
    """
    claimed = path + RUNNING_SUFFIX
    os.replace(path, claimed)
    return claimed


def restore(claimed, path):
    """把取走的令牌放回去（锁等待超时用）。返回是否成功，永不抛。"""
    try:
        os.replace(claimed, path)
        return True
    except OSError:
        return False


def discard(claimed):
    """尽力删除取走的令牌文件（正常路径的「即焚」），失败不抛。"""
    try:
        os.remove(claimed)
    except OSError:
        pass


def purge_expired(directory, now=None, grace=RUNNING_GRACE_SECONDS):
    """清理过期令牌与陈旧残片，返回清理数量。

    判据：
    - `<token>.json`：能解析且 `expires_at < now` → 过期；不能解析 → 坏文件
      （原子写作不会产生半截，坏文件必是外部/历史残留）→ 一并清；
    - `.running` / `.tmp`：mtime 超过 `grace` 才清（宽限期内可能是另一进程
      正在执行的 apply，误杀会让「稍后重试」变成「找不到令牌」）。

    尽力而为：任何 OSError 都跳过该项——清理绝不能连累 preview / apply。
    """
    now = time.time() if now is None else now
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        full = os.path.join(directory, name)
        try:
            if name.endswith(RUNNING_SUFFIX) or name.endswith(".tmp"):
                if now - os.path.getmtime(full) > grace:
                    os.remove(full)
                    removed += 1
                continue
            if not name.endswith(".json"):
                continue
            try:
                expires = float(read_record(full).get("expires_at") or 0)
            except (OSError, ValueError, TypeError, AttributeError):
                expires = 0.0          # 坏文件按"已过期"处理
            if expires < now:
                os.remove(full)
                removed += 1
        except OSError:
            continue
    return removed
