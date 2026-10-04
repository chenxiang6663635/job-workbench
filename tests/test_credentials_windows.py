# -*- coding: utf-8 -*-
"""Windows 凭据管理器的**真机**往返（issue #203 子任务 A）。

CI 的 ubuntu job 整文件跳过；在 Windows 上它真的往凭据管理器写一条
`job-workbench/<uuid4>/selftest` 通用凭据，读回验字后立即删除——try/finally
保证清理，引用由 `new_ref` 生成（唯一、用后即删、不碰用户既有条目）。

跨平台契约（假 store / 形态判定 / 日志脱敏）在 `tests/test_credentials.py`。
"""

import sys

import pytest

from jobws_core import credentials

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="凭据管理器只有 Windows 上存在（CI 的 ubuntu job 会跳过整文件）")


def _store_or_skip():
    """真机上有凭据管理器才继续；加载失败（企业策略等）如实跳过。"""
    store = credentials.CredManStore()
    if not store.available():
        pytest.skip("advapi32 / 凭据管理器不可用（企业策略或加载失败）")
    return store


def test_credman_roundtrip_set_get_delete():
    store = _store_or_skip()
    ref = credentials.new_ref("selftest")
    secret = "jwb-selftest-授权码-roundtrip"

    cleaned = False
    try:
        assert store.set(ref, secret) is True, "写入凭据管理器应成功"
        assert store.get(ref) == secret, "读回必须与写入逐字一致（含非 ASCII）"
    finally:
        cleaned = store.delete(ref)

    assert cleaned is True, "测试凭据必须清理掉"
    assert store.get(ref) is None, "删除后应读不到"


def test_credman_missing_ref_is_none_and_delete_is_idempotent():
    """不存在的引用：get → None；delete 幂等成功（"本来就已删除"也算达成）。"""
    store = _store_or_skip()
    ref = credentials.new_ref("selftest-missing")

    assert store.get(ref) is None
    assert store.delete(ref) is True
