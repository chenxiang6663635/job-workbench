# -*- coding: utf-8 -*-
"""凭据 at-rest 存储（`jobws_core.credentials`）的行为契约（issue #203 子任务 A）。

本文件**跨平台可跑**（CI 的 ubuntu job 也跑它）：一律用假 store / 注入口，不碰
真实凭据管理器；真机往返在 `tests/test_credentials_windows.py`（按平台门控）。

钉住的是两条不变式与一组形态判定（完整口径见模块 docstring）：

1. **「引用在手但取不到」≠「没配置」**：有 ref 时只认系统存储，取不到必须返回
   `secret=None`——**绝不**回落同一条目里的旧明文（那会把"凭据被删了"伪装成
   "用户没配过"）；
2. **写失败必须保留明文**：迁移 / 保存写系统存储失败时，cfg 里的旧明文原样保留
   ——一次失败的迁移不能吞掉用户仅存的那份凭据；
3. `select_store` 三态（auto / credman / plaintext）与平台回落：一律不抛；
4. **任何一条日志都不含密文**（注入 logger 与 caplog 两路收集）。
"""

import logging
import sys

import pytest

from jobws_core import credentials

SECRET = "TOP-SECRET-授权码-abc123"
REF = "job-workbench/0f8fad5b/imap"
REF_KEY = "passwordRef"
LEGACY_KEY = "password"
PREFIX = "imap"


class _FakeStore:
    """可编程的假存储：默认"写入成功、读出预置值"；逐项覆写行为并记录调用。"""

    def __init__(self, kind=credentials.KIND_CREDMAN, stored=None,
                 set_ok=True, delete_ok=True):
        self.kind = kind
        self.stored = stored          # get 命中时返回的值；None = 取不到
        self.set_ok = set_ok
        self.delete_ok = delete_ok
        self.calls = []               # [(op, ref, payload)]，payload 仅 set 用
        self.written = {}             # set 成功时落下的 {ref: secret}

    def available(self):
        return True

    def get(self, ref):
        self.calls.append(("get", ref, None))
        return self.stored

    def set(self, ref, secret):
        self.calls.append(("set", ref, secret))
        if not self.set_ok:
            return False
        self.written[ref] = secret
        return True

    def delete(self, ref):
        self.calls.append(("delete", ref, None))
        return self.delete_ok


class _LogCollector:
    """日志替身：把每条日志（含格式化后的消息）拼成文本，供"不含密文"断言。"""

    def __init__(self):
        self.lines = []

    def _record(self, level, msg, args):
        try:
            text = msg % args if args else str(msg)
        except Exception:   # 参数对不上时保底：原文 + 参数（测试替身不该借机丢信息）
            text = "%s %r" % (msg, args)
        self.lines.append("[%s] %s" % (level, text))

    def debug(self, msg, *args, **kwargs):
        self._record("DEBUG", msg, args)

    def info(self, msg, *args, **kwargs):
        self._record("INFO", msg, args)

    def warning(self, msg, *args, **kwargs):
        self._record("WARNING", msg, args)

    def error(self, msg, *args, **kwargs):
        self._record("ERROR", msg, args)

    @property
    def text(self):
        return "\n".join(self.lines)


def _config(*, ref=None, legacy=None):
    """按需拼出 cfg；键名用子任务 B 在 IMAP / Provider 两处将使用的形状。"""
    cfg = {}
    if ref is not None:
        cfg[REF_KEY] = ref
    if legacy is not None:
        cfg[LEGACY_KEY] = legacy
    return cfg


# --- resolve_secret：三条规则与两条不变式 ------------------------------------


def test_resolve_hit_returns_secret_and_leaves_cfg_untouched():
    store = _FakeStore(stored=SECRET)
    cfg = _config(ref=REF)

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome == credentials.ResolveOutcome(
        SECRET, credentials.KIND_CREDMAN, False)
    assert cfg == {REF_KEY: REF}
    assert store.calls == [("get", REF, None)]


def test_resolve_missing_ref_never_falls_back_to_legacy_plaintext():
    """铁律 1 的锁死用例：ref 与旧明文同时存在时，取不到只返回 None。

    这是最危险的一种脏配置（桌面版迁移后旧明文残留、随后用户删掉了凭据管理器
    里的条目）：回落旧明文就等于把"凭据没了"伪装成"一切正常"。
    """
    store = _FakeStore(stored=None)
    cfg = _config(ref=REF, legacy=SECRET)

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome.secret is None
    assert outcome.kind == credentials.KIND_CREDMAN
    assert outcome.migrated is False
    assert SECRET not in repr(outcome), "旧明文不得以任何形式出现在结果里"
    assert cfg == {REF_KEY: REF, LEGACY_KEY: SECRET}, "cfg 也不该被顺手改写"


def test_resolve_strips_accidental_whitespace_on_ref_lookup_only():
    """手工编辑配置留下的首尾空白不该让引用失配（只影响查询，不改写 cfg）。"""
    store = _FakeStore(stored=SECRET)
    cfg = _config(ref=" " + REF + " ")

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome.secret == SECRET
    assert store.calls == [("get", REF, None)]
    assert cfg == {REF_KEY: " " + REF + " "}, "查询容错不该顺手改写 cfg"


def test_resolve_legacy_migrates_when_store_write_succeeds():
    store = _FakeStore()
    cfg = _config(legacy=SECRET)

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome == credentials.ResolveOutcome(
        SECRET, credentials.KIND_CREDMAN, True)
    ref = cfg[REF_KEY]
    assert ref.startswith("job-workbench/") and ref.endswith("/" + PREFIX)
    assert LEGACY_KEY not in cfg, "明文已搬进系统存储，cfg 里不该再留一份"
    assert store.written == {ref: SECRET}
    assert store.calls[0][0] == "set", "迁移走的是 set，不是先 get"


def test_resolve_legacy_stays_plaintext_when_store_write_fails():
    """铁律 2 的锁死用例：迁移失败 → cfg 原样、明文还在、按明文形态返回。"""
    store = _FakeStore(set_ok=False)
    cfg = _config(legacy=SECRET)

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome == credentials.ResolveOutcome(
        SECRET, credentials.KIND_PLAINTEXT, False)
    assert cfg == {LEGACY_KEY: SECRET}, "write 失败必须保留明文且不改 cfg 形状"


def test_resolve_with_plaintext_store_keeps_legacy_untouched():
    """明文形态（源码 / CLI）：不迁移、不报错，cfg 原样。"""
    store = credentials.PlaintextStore()
    cfg = _config(legacy=SECRET)

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome == credentials.ResolveOutcome(
        SECRET, credentials.KIND_PLAINTEXT, False)
    assert cfg == {LEGACY_KEY: SECRET}


def test_resolve_with_nothing_configured_reports_missing_without_touching_store():
    store = _FakeStore()

    outcome = credentials.resolve_secret(
        _config(), ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX,
        store=store)

    assert outcome == credentials.ResolveOutcome(
        None, credentials.KIND_CREDMAN, False)
    assert store.calls == [], "没配置就不该去碰系统存储"


# --- store_secret：保存新凭据 -------------------------------------------------


def test_store_secret_credman_success_writes_ref_and_drops_legacy():
    store = _FakeStore()
    cfg = _config(legacy="用户曾经保存的旧授权码")

    kind = credentials.store_secret(
        cfg, SECRET, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX,
        store=store)

    assert kind == credentials.KIND_CREDMAN
    ref = cfg[REF_KEY]
    assert ref.startswith("job-workbench/")
    assert LEGACY_KEY not in cfg
    assert store.written == {ref: SECRET}


def test_store_secret_failure_keeps_plaintext_and_drops_stale_ref():
    store = _FakeStore(set_ok=False)
    cfg = _config(ref=REF)   # 旧 ref 已不可写：不得留在 cfg 里（死引用）

    kind = credentials.store_secret(
        cfg, SECRET, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX,
        store=store)

    assert kind == credentials.KIND_PLAINTEXT
    assert cfg == {LEGACY_KEY: SECRET}


def test_store_secret_with_plaintext_store_reports_plaintext():
    store = credentials.PlaintextStore()
    cfg = _config()

    kind = credentials.store_secret(
        cfg, SECRET, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX,
        store=store)

    assert kind == credentials.KIND_PLAINTEXT
    assert cfg == {LEGACY_KEY: SECRET}


# --- delete_secret：「清除即删」 ----------------------------------------------


def test_delete_secret_removes_both_cfg_keys_and_deletes_store_entry():
    store = _FakeStore()
    cfg = _config(ref=REF, legacy="残留旧明文")

    credentials.delete_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, store=store)

    assert cfg == {}
    assert ("delete", REF, None) in store.calls


def test_delete_secret_cleans_cfg_even_when_store_delete_fails():
    store = _FakeStore(delete_ok=False)
    cfg = _config(ref=REF, legacy="残留旧明文")

    credentials.delete_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, store=store)

    assert cfg == {}, "删除失败也不能留下指向已删凭据的死引用"


def test_delete_secret_without_ref_does_not_touch_store():
    store = _FakeStore()
    cfg = _config(legacy=SECRET)

    credentials.delete_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, store=store)

    assert cfg == {}
    assert store.calls == [], "没有 ref 就没有系统条目可删"


# --- select_store：三态与回落 --------------------------------------------------


def test_select_store_auto_on_linux_is_plaintext():
    store = credentials.select_store(platform="linux")

    assert isinstance(store, credentials.PlaintextStore)
    assert store.kind == credentials.KIND_PLAINTEXT


def test_select_store_explicit_plaintext_wins_even_on_windows_sim():
    store = credentials.select_store("plaintext", platform="win32")

    assert isinstance(store, credentials.PlaintextStore)


def test_select_store_explicit_credman_on_linux_falls_back_without_raising(caplog):
    with caplog.at_level(logging.WARNING, logger=credentials.__name__):
        store = credentials.select_store("credman", platform="linux")

    assert isinstance(store, credentials.PlaintextStore)
    assert credentials.CREDENTIAL_STORE_ENV in caplog.text


def test_select_store_reads_env_when_no_override(monkeypatch):
    monkeypatch.setenv(credentials.CREDENTIAL_STORE_ENV, "plaintext")

    store = credentials.select_store(platform="linux")

    assert isinstance(store, credentials.PlaintextStore)


def test_select_store_override_wins_over_env(monkeypatch):
    monkeypatch.setenv(credentials.CREDENTIAL_STORE_ENV, "credman")

    store = credentials.select_store("plaintext", platform="linux")

    assert isinstance(store, credentials.PlaintextStore)


def test_select_store_unknown_mode_falls_back_to_auto_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=credentials.__name__):
        store = credentials.select_store("credmen", platform="linux")   # 拼错

    assert isinstance(store, credentials.PlaintextStore)
    assert "credmen" in caplog.text, "拼错的值要能在日志里查到，不静默"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="该用例模拟'平台是 Windows 但 advapi32 拿不到'；Windows 真机路径在 test_credentials_windows.py")
def test_select_store_auto_on_windows_without_credman_falls_back(caplog):
    with caplog.at_level(logging.WARNING, logger=credentials.__name__):
        store = credentials.select_store(platform="win32")

    assert isinstance(store, credentials.PlaintextStore)
    assert "win32" in caplog.text


# --- 存储实现的形态契约 --------------------------------------------------------


def test_plaintext_store_contract_is_deliberately_inert():
    store = credentials.PlaintextStore()

    assert store.kind == credentials.KIND_PLAINTEXT
    assert store.available() is True, "回退路径永远可用（这是它 available 为真的含义）"
    assert store.get(REF) is None, "它不保存任何东西——家是调用方的 cfg"
    assert store.set(REF, SECRET) is False
    assert store.delete(REF) is False


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="非 Windows 的安全返回形态；Windows 真机行为见 test_credentials_windows.py")
def test_credman_store_is_safe_on_non_windows():
    """Linux / macOS 上构造与三个调用都安全（None / False，不抛）——CI 的形态。"""
    store = credentials.CredManStore()

    assert store.available() is False
    assert store.get(REF) is None
    assert store.set(REF, SECRET) is False
    assert store.delete(REF) is False


# --- new_ref ------------------------------------------------------------------


def test_new_ref_shape_unique_and_prefix_aware():
    first = credentials.new_ref("imap")
    second = credentials.new_ref("imap")

    assert first.startswith("job-workbench/")
    assert first.endswith("/imap")
    assert first != second, "两次生成必须不同（否则同名凭据互相覆盖）"
    middle = first[len("job-workbench/"):-len("/imap")]
    assert len(middle) == 32 and all(ch in "0123456789abcdef" for ch in middle)


# --- 日志：（任何一条都）不含密文 ----------------------------------------------


def test_no_log_line_ever_contains_the_secret():
    """铁律 2：密文只该出现在返回值与存储里，不该出现在日志。

    覆盖命中、引用取不到、迁移成功 / 失败、保存成功 / 失败、明文形态、删除
    失败——成功与失败两条路都走一遍，避免"只给失败路径脱敏"。
    """
    logs = _LogCollector()
    keys = dict(ref_key=REF_KEY, legacy_key=LEGACY_KEY, log=logs)
    with_prefix = dict(keys, prefix=PREFIX)   # delete_secret 没有 prefix 参数

    credentials.resolve_secret(_config(ref=REF), store=_FakeStore(stored=SECRET),
                               **with_prefix)
    credentials.resolve_secret(_config(ref=REF, legacy=SECRET),
                               store=_FakeStore(stored=None), **with_prefix)
    credentials.resolve_secret(_config(legacy=SECRET), store=_FakeStore(),
                               **with_prefix)
    credentials.resolve_secret(_config(legacy=SECRET),
                               store=_FakeStore(set_ok=False), **with_prefix)
    credentials.resolve_secret(_config(legacy=SECRET),
                               store=credentials.PlaintextStore(), **with_prefix)
    credentials.store_secret(_config(), SECRET, store=_FakeStore(), **with_prefix)
    credentials.store_secret(_config(), SECRET, store=_FakeStore(set_ok=False),
                             **with_prefix)
    credentials.delete_secret(_config(ref=REF, legacy=SECRET),
                              store=_FakeStore(delete_ok=False), **keys)

    assert logs.lines, "没有任何日志 = 用例没跑到断言上"
    assert SECRET not in logs.text
    assert "TOP-SECRET" not in logs.text, "哪怕片段也不许出现"


def test_module_logger_keeps_the_secret_out_too(caplog):
    """同一件事走**模块 logger**（未注入 log）再验一遍，防"只在注入路径脱敏"。"""
    with caplog.at_level(logging.DEBUG, logger=credentials.__name__):
        credentials.resolve_secret(
            _config(legacy=SECRET), ref_key=REF_KEY, legacy_key=LEGACY_KEY,
            prefix=PREFIX, store=_FakeStore(set_ok=False))

    assert caplog.records, "迁移失败必须留下日志"
    assert SECRET not in caplog.text


def test_resolve_cleans_a_stale_plaintext_beside_a_valid_ref():
    """引用有效、旁边还残留明文（手改配置 / 迁移中断）→ 清掉明文并要求落盘。

    不清的话，下一次保存会把这段老明文**原样写回**（四端复核 n-2）——引用明明
    已经生效，文件里却继续躺着一份旧钥匙。
    """
    store = _FakeStore(stored=SECRET)
    cfg = _config(ref=REF, legacy="残留的旧明文")

    outcome = credentials.resolve_secret(
        cfg, ref_key=REF_KEY, legacy_key=LEGACY_KEY, prefix=PREFIX, store=store)

    assert outcome == credentials.ResolveOutcome(SECRET, credentials.KIND_CREDMAN, True)
    assert LEGACY_KEY not in cfg, "残留明文必须被清掉"
    assert cfg[REF_KEY] == REF, "引用本身不动"
