# -*- coding: utf-8 -*-
"""工作区配置文件的凭据字段 ↔ `jobws_core.credentials` 策略层的共享接线（issue #203）。

imap 与 provider 曾各自复制一份「解析 → 迁移落盘 → strict 409」：重复的不是行数，
而是**行为口径**——复制体最容易漂的地方恰是"照抄时漏掉一个分支"（漏掉迁移落盘、
或把"引用取不到"当成"没配置"）。

两条铁律（与 `jobws_core.credentials` 同源，由路由面的测试逐条钉住）：
1. **「引用在手但取不到」≠「没配置」**：strict 调用点（/test、/fetch、BYOK 消费面）
   必须显式 409 指路「重新保存」——界面看着正常、调用却拿不到凭据，是最难排查的
   一种"正常"；静默按未配置处理等于把它伪装掉。
2. **迁移必须落盘**：`migrated=True` 时锁内原子写回（否则每次读都重新迁移一遍、
   还反复写系统存储）。

`persist=False` 是给**已持锁**的调用点（imap / provider 两个 POST 保存）准备的：
`filelock` 不可重入，锁内再 `locked()` 只会等到超时（429）；迁移结果由调用方
并入自己那一次原子写。
"""

from __future__ import annotations

import json

from jobws_core import credentials

from apierror import ApiError
from atomicio import atomic_write_text
from lockctx import lock_path, locked


def store():
    """本次使用的凭据存储形态（每次现选、**不缓存**——见 `credentials.select_store`）。

    必须是**调用时**查属性：测试逐个用例 monkeypatch `credentials.select_store`
    注入假 store；导入期绑定函数对象会把"每请求现选"变成一处隐蔽的全局状态。
    """
    return credentials.select_store()


def resolve(cfg, *, path, ws, ref_key, legacy_key, prefix, lock_name,
            persist=True, reload=None, log=None):
    """解析凭据（必要时把旧明文迁移进系统存储并落盘），返回 `credentials.ResolveOutcome`。

    **不抛**：strict 语义由 `resolve_strict` 叠加；GET 这类展示面直接用它。

    `reload`：锁内**重读**配置的回调（如 `lambda: _read_config(path)`）。展示面
    （GET / /test / /fetch）顺带迁移时，手里这份 cfg 可能是几毫秒前读的——直接写回
    会把并发 POST 刚保存的字段覆盖掉（provider 的老实现专门防过这一手，抽公共件
    时不能丢）。给了回调就"重读 → 只在新鲜副本上应用引用变更 → 写回"，并把合并
    结果刷新进调用方的 cfg（后续字段读到的是最新值）。不传则维持旧语义（只写回
    手里的 cfg），POST 这类"自己刚读完又自己写"的调用点不需要它。
    """
    outcome = credentials.resolve_secret(
        cfg, ref_key=ref_key, legacy_key=legacy_key, prefix=prefix,
        store=store(), log=log)
    if outcome.migrated and persist:
        # 铁律 2：迁移必须持久化——否则每次读都重新迁移一遍（还反复写系统存储）。
        with locked(lock_path(ws, lock_name)):
            if reload is not None:
                fresh = reload()
                if isinstance(fresh, dict):
                    fresh[ref_key] = cfg[ref_key]
                    fresh.pop(legacy_key, None)
                    cfg.clear()
                    cfg.update(fresh)
            atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2))
    return outcome


def resolve_strict(cfg, *, path, ws, ref_key, legacy_key, prefix, lock_name,
                   error_code, error_message, reload=None, log=None):
    """`resolve` + 铁律 1：cfg 里引用非空、`secret` 却为 None → 409 `error_code`。

    判定在 `resolve` **之后**（迁移刚写入的引用也要算数——那种情况下 secret 是
    旧明文，非 None，不会误报）。

    「引用在手却取不到」的出路是**重新保存**（换了电脑 / Windows 账户，或系统
    清理过凭据管理器），不是当作"没配置"（去检查配置栏）——两者对用户是不同的
    指导，合成一句话等于把可操作的那半句磨掉。
    """
    outcome = resolve(cfg, path=path, ws=ws, ref_key=ref_key,
                      legacy_key=legacy_key, prefix=prefix,
                      lock_name=lock_name, reload=reload, log=log)
    ref = cfg.get(ref_key)
    if isinstance(ref, str) and ref.strip() and outcome.secret is None:
        raise ApiError(409, error_code, error_message)
    return outcome
