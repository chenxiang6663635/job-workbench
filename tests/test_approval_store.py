# -*- coding: utf-8 -*-
"""令牌簿记文件层（`approval_store`）：原子写 / claim / restore / 过期清理。

2026-10-08 审计 1.1-4 的后两处：令牌文件此前是 `open(path, "w") + json.dump`
的非原子写（序列化失败会先把旧令牌截成空文件），且 TEMP 目录里的令牌（含
明文业务载荷）**无任何清理实现**。本文件先红后绿。
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from jobws_core import approval_store  # noqa: E402


def _record(expires_in=600):
    return {"token": "a" * 32, "expires_at": time.time() + expires_in,
            "payload": {"x": 1}}


def _put(directory, name, record):
    """直写测试用令牌文件（绕开 write_record 的顺手清理，保证夹具可控）。"""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
    return path


def test_write_record_leaves_old_file_intact_when_serialization_fails(tmp_path):
    """序列化失败不得破坏既有令牌——非原子写会先 open(w) 把旧文件截成空。

    夹具用**有效令牌形状**（带未来 expires_at）：缺这个字段的记录会被
    `write_record` 开头的顺手清理按"过期"收走，那不是本测试要观察的行为。
    """
    old = {"expires_at": time.time() + 600, "old": True}
    path = str(tmp_path / "t.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(old))

    with pytest.raises(TypeError):
        approval_store.write_record(path, {"bad": object()})

    with open(path, encoding="utf-8") as handle:
        assert json.load(handle) == old
    assert [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")] == []


def test_write_record_goes_through_temp_and_replace(tmp_path, monkeypatch):
    """写入 = 同目录临时文件 + os.replace（原子可见），结束后不留 .tmp。"""
    calls = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace",
                        lambda a, b: (calls.append((a, b)), real_replace(a, b))[1])
    path = str(tmp_path / "t.json")

    approval_store.write_record(path, _record())

    assert len(calls) == 1, calls
    assert calls[0][0].endswith(".tmp")
    assert os.path.dirname(calls[0][0]) == str(tmp_path), "临时文件必须同目录（跨盘 replace 非原子）"
    assert os.path.isfile(path)
    assert [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")] == []


def test_claim_is_exclusive_and_restorable(tmp_path):
    """取走 = 原子重命名：并发只有一个赢家；锁超时可还原让重试成立。"""
    path = str(tmp_path / "t.json")
    approval_store.write_record(path, _record())

    claimed = approval_store.claim(path)

    assert claimed == path + approval_store.RUNNING_SUFFIX
    assert not os.path.exists(path) and os.path.exists(claimed)
    with pytest.raises(OSError):
        approval_store.claim(path)          # 第二个赢家拿不到同一份令牌
    assert approval_store.restore(claimed, path) is True
    assert os.path.isfile(path) and not os.path.exists(claimed)


def test_purge_expired_removes_only_stale(tmp_path):
    """过期 / 坏文件 / 陈旧 .running 清掉；有效令牌与「新鲜」残片不动。"""
    d = str(tmp_path)
    expired = _put(d, "a" * 32 + ".json", _record(expires_in=-1))
    valid = _put(d, "b" * 32 + ".json", _record())
    broken = os.path.join(d, "c" * 32 + ".json")
    with open(broken, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    stale_running = valid + approval_store.RUNNING_SUFFIX
    with open(stale_running, "w", encoding="utf-8") as handle:
        handle.write("{}")
    old = time.time() - approval_store.RUNNING_GRACE_SECONDS - 60
    os.utime(stale_running, (old, old))

    removed = approval_store.purge_expired(d)

    assert removed == 3, removed            # expired + broken + 陈旧 running
    assert not os.path.exists(expired)
    assert not os.path.exists(broken)
    assert not os.path.exists(stale_running)
    assert os.path.isfile(valid), "有效令牌绝不能被清"


def test_purge_keeps_fresh_running(tmp_path):
    """宽限期内的 .running 保留——可能是另一进程正在执行的 apply。"""
    d = str(tmp_path)
    running = os.path.join(d, "a" * 32 + ".json" + approval_store.RUNNING_SUFFIX)
    with open(running, "w", encoding="utf-8") as handle:
        handle.write("{}")

    assert approval_store.purge_expired(d) == 0
    assert os.path.exists(running)


def test_write_record_purges_expired_first(tmp_path):
    """写新令牌顺手清一次过期项——这就是清理的触发点（审计：此前无任何实现）。"""
    d = str(tmp_path)
    expired = _put(d, "a" * 32 + ".json", _record(expires_in=-1))
    path = os.path.join(d, "d" * 32 + ".json")

    approval_store.write_record(path, _record())

    assert not os.path.exists(expired)
    assert os.path.isfile(path)
