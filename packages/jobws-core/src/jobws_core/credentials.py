# -*- coding: utf-8 -*-
"""凭据的 at-rest 策略层：形态选择、惰性迁移、保存与「清除即删」（issue #203）。

**两种存储形态**（`select_store` 决定；桌面版默认自动走 credman）：`credman`
把密文放进 Windows 凭据管理器（后端实现在 `credentials_win.py`），配置文件里只剩
引用串（`new_ref` 生成，与工作区路径无关——换目录、改工作区名后引用仍命中）；
`plaintext` 是源码 / CLI 形态的显式回退，密文留在配置文件里；显式要求 credman 而
平台不可用时也落到这里（记 warning，不抛）。

**导入期永不失败**：顶层只有标准库；Windows 后端经 PEP 562 惰性导出（见文件末尾
`__getattr__`），`credentials` ↔ `credentials_win` 之间没有顶层循环导入——CI 的
ubuntu job 照常 import 本模块。

**两条不能动的铁律**（`tests/test_credentials.py` 逐条钉住）：
1. 「引用在手但取不到」≠「没配置」：有非空引用时只认系统存储，取不到必须返回
   `secret=None` 让调用方显式报错——**绝不**回落同一条目里的旧明文；同理
   「写失败必须保留明文」：迁移 / 保存写系统存储失败时 cfg 里的明文原样保留，
   一次失败的迁移不能吞掉用户仅存的那份凭据（那是数据丢失，不是可用性降级）。
2. 日志永不含密文：只记形态、引用（ref）与成败；测试用注入 logger 与 caplog
   两路收集、逐条断言。

**本模块不读写文件**：只就地改传进来的 cfg（dict），落盘是调用方的事（两段式
写入：先拿 `ResolveOutcome` 决定界面 / 错误，再由调用方原子落盘）。
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import NamedTuple

logger = logging.getLogger(__name__)

# 环境变量与形态标识：CLI / 后端 / 文档都引用这组常量，别处不要再写字面量。
CREDENTIAL_STORE_ENV = "JOBWS_CREDENTIAL_STORE"
KIND_CREDMAN = "credman"
KIND_PLAINTEXT = "plaintext"
# 凭据管理器里目标名的第一段；uuid4 保证两次生成必不相同（同名凭据不互相覆盖）。
_REF_NAMESPACE = "job-workbench"


class SecretStore:
    """存储接口：get 取不到 → None；set / delete → True|False；都不抛。

    `kind` 是形态标识（"credman" / "plaintext"）。基类只定义接口，别直接实例化。
    """
    kind = ""

    def available(self):
        raise NotImplementedError

    def get(self, ref):
        raise NotImplementedError

    def set(self, ref, secret):
        raise NotImplementedError

    def delete(self, ref):
        raise NotImplementedError


class PlaintextStore(SecretStore):
    """明文回退：密文住在调用方的 cfg 里，本类不保存任何东西。

    `available()` 为 True 表达"这条回退路径永远可用、永不抛"；get / set / delete
    全为 None / False 表达"它不落任何存储"——调用方应把 cfg[legacy_key] 当作
    数据的家，而不是在这里再存一份。
    """
    kind = KIND_PLAINTEXT

    def available(self):
        return True

    def get(self, ref):
        return None

    def set(self, ref, secret):
        return False

    def delete(self, ref):
        return False


class ResolveOutcome(NamedTuple):
    """一次解析的完整结果（具名，防调用点错位）。

    `secret=None` 有且只有两种含义：引用在手但系统存储取不到、或两边都没配——
    前者必须由调用方**显式报错**，不能与"用户没配置过"混为一谈。`migrated=True`
    表示 cfg 已被**就地改写**（发生了「旧明文 → 系统存储」的迁移，或清理了引用旁
    残留的明文字段），**调用方负责把 cfg 落盘**（本模块不碰文件）。
    """
    secret: str | None
    kind: str
    migrated: bool


def _logger_of(log):
    """注入的 logger 优先；未注入用模块 logger（测试用假 logger 收集日志）。"""
    return logger if log is None else log


def _is_text(value):
    """cfg 字段是否为非空字符串；脏配置里的其它类型一律按"没有"处理。"""
    return isinstance(value, str) and bool(value)


def new_ref(prefix):
    """生成凭据引用：`job-workbench/<uuid4hex>/<prefix>`。

    刻意**不**含工作区路径或文件名：引用是凭据管理器里的目标名，换目录、改
    工作区名之后旧引用仍然命中；uuid4 保证随机且两次生成必不相同。
    """
    return "%s/%s/%s" % (_REF_NAMESPACE, uuid.uuid4().hex, prefix)


def select_store(override=None, *, platform=None, env=None):
    """决定本次用哪种存储：override 优先，其次 env[CREDENTIAL_STORE_ENV]，默认 auto。

    auto 在 Windows 上拿不到凭据管理器时回落明文；显式 "credman" 而平台不可用
    同样回落（记 warning，不抛）——"存不进去"不能升级成"功能不可用"。`platform`
    / `env` 是测试注入口（默认取 sys.platform / os.environ）；注意 `platform`
    参数会遮蔽同名标准库模块，所以模块内部一律用 sys.platform。
    """
    plat = sys.platform if platform is None else platform
    environ = os.environ if env is None else env
    raw = override if override is not None else environ.get(CREDENTIAL_STORE_ENV)
    mode = ("" if raw is None else str(raw)).strip().lower() or "auto"
    if mode not in ("auto", KIND_CREDMAN, KIND_PLAINTEXT):
        logger.warning("未知的 %s=%r，按 auto 处理", CREDENTIAL_STORE_ENV, raw)
        mode = "auto"

    if mode == KIND_PLAINTEXT:
        return PlaintextStore()
    # 注入的 platform 与真实可用性都要满足：CI 在 Linux 上注入 "win32" 时，
    # advapi32 依然加载不到，必须回落而不是假装可用。
    if plat == "win32":
        from .credentials_win import CredManStore  # 惰性：见模块头「导入期永不失败」
        store = CredManStore()
        if store.available():
            return store
    if mode == KIND_CREDMAN or plat == "win32":
        logger.warning("凭据管理器不可用（platform=%s、%s=%s），回落明文存储",
                       plat, CREDENTIAL_STORE_ENV, mode)
    return PlaintextStore()


def resolve_secret(cfg, *, ref_key, legacy_key, prefix, store, log=None):
    """按 cfg 当前形态把凭据取出来（必要时就地迁移）。

    顺序不能变：① 有非空 ref_key → 只认系统存储，取不到返回 (None, kind, False)
    且**绝不**回落 legacy_key——"引用在手却取不到"是"凭据没了"，须由调用方显式
    报错；② 无 ref 但有旧明文 → store.set 成功才改写 cfg（写 ref_key、删
    legacy_key、migrated=True），失败则 cfg 原样、按明文形态返回（铁律 1）；
    ③ 都没有 → (None, store.kind, False)，调用方按"未配置"处理。
    """
    handle = _logger_of(log)
    ref = cfg.get(ref_key)
    if _is_text(ref):
        secret = store.get(ref.strip())
        if secret is None:
            handle.warning("凭据引用在 %s 中取不到（ref=%s）——凭据可能已被删除，"
                           "请重新保存；旧明文字段不再作为回退", store.kind, ref)
            return ResolveOutcome(None, store.kind, False)
        if _is_text(cfg.get(legacy_key)):
            # 混合配置（引用 + 残留明文，多为手改或迁移中断）：引用有效，明文已无用。
            # 就地清掉并让调用方落盘——否则下一次保存会把这段老明文原样写回
            # （四端复核 n-2）。`migrated=True` 在这里表示"cfg 已被就地改写，请落盘"。
            cfg.pop(legacy_key, None)
            handle.info("已清理残留的明文字段（引用 %s 有效，ref=%s）", legacy_key, ref)
            return ResolveOutcome(secret, store.kind, True)
        return ResolveOutcome(secret, store.kind, False)

    legacy = cfg.get(legacy_key)
    if _is_text(legacy):
        ref = new_ref(prefix)
        if store.set(ref, legacy):
            cfg[ref_key] = ref
            cfg.pop(legacy_key, None)
            handle.info("旧明文凭据已迁移到 %s（ref=%s）", store.kind, ref)
            return ResolveOutcome(legacy, store.kind, True)
        if store.kind == KIND_PLAINTEXT:
            # 明文形态本来就没有系统存储可迁：不是失败，是明说的常态。
            handle.debug("明文存储形态：凭据保持在配置文件（%s）", legacy_key)
        else:
            handle.warning("迁移旧明文凭据到 %s 失败，明文原样保留（%s）",
                           store.kind, legacy_key)
        return ResolveOutcome(legacy, KIND_PLAINTEXT, False)

    return ResolveOutcome(None, store.kind, False)


def store_secret(cfg, secret, *, ref_key, legacy_key, prefix, store, log=None):
    """保存新凭据：优先写系统存储，失败才把明文留在 cfg；返回最终存放形态。

    区分两件事：显式明文形态是常态（debug），"写系统存储失败"才要提醒（warning）。
    cfg 只被就地改写（成功后写 ref_key、删 legacy_key），落盘由调用方做。
    """
    handle = _logger_of(log)
    # 轮换复用已有引用：写同一个目标名即覆盖，不会在凭据管理器里留下指向旧密文的
    # 孤儿条目（用户的「更新授权码 / 换 key」永远只对应一条凭据）。
    existing = cfg.get(ref_key)
    ref = existing.strip() if _is_text(existing) else new_ref(prefix)
    if store.set(ref, secret):
        cfg[ref_key] = ref
        cfg.pop(legacy_key, None)
        handle.info("凭据已保存到 %s（ref=%s）", store.kind, ref)
        return store.kind
    # 写失败 → cfg 丢掉引用、回落明文。注意：系统存储里可能残留一条指向旧密文的
    # 条目（本模块不掌握"cfg 何时真正落盘"——删早了，万一调用方的原子写失败，
    # 用户就会连仅存的那把钥匙也没了）。这是「绝不丢钥匙」优先于「不留孤儿」的
    # 取舍；排障时按 ref 到凭据管理器里找。
    cfg[legacy_key] = secret
    cfg.pop(ref_key, None)
    if store.kind == KIND_PLAINTEXT:
        handle.debug("明文存储形态：凭据保存在配置文件（%s）", legacy_key)
    else:
        handle.warning("写入 %s 失败，凭据按明文保存在配置文件（%s）",
                       store.kind, legacy_key)
    return KIND_PLAINTEXT


def delete_secret(cfg, *, ref_key, legacy_key, store, log=None):
    """「清除即删」：cfg 里清干净，系统存储里的条目也跟着删。

    无论删除成败，cfg 的两个键都必须清掉——留下一个指向已删凭据的死引用，
    下次读会变成"引用在手却取不到"的报错，而用户的意图明明是"不用了"。
    删除失败只记日志（可能本来就不存在；明文形态也删不了系统存储里的条目）。
    """
    handle = _logger_of(log)
    ref = cfg.get(ref_key)
    if _is_text(ref):
        try:
            deleted = store.delete(ref)
        except Exception as exc:
            # 存储实现承诺不抛；但"cfg 必须清干净"这条不变式不能被它破坏。
            deleted = False
            handle.warning("删除系统存储中的凭据失败（ref=%s）：%s", ref, exc)
        if not deleted and store.kind != KIND_PLAINTEXT:
            handle.warning("系统存储中删除凭据未成功（ref=%s）", ref)
    cfg.pop(ref_key, None)
    cfg.pop(legacy_key, None)


def __getattr__(name):
    """PEP 562 惰性导出 Windows 后端。

    为什么需要它：`CredManStore` 的引用面（测试、未来的 callers）希望继续写作
    `credentials.CredManStore`，但顶层导入 `credentials_win` 会与之形成循环
    （后端要继承本模块的 `SecretStore`）。惰性导出两全：模块加载期不碰 ctypes，
    属性访问时再 import——那时本模块已初始化完毕。
    """
    if name == "CredManStore":
        from .credentials_win import CredManStore
        return CredManStore
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
