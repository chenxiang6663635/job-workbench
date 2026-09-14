# -*- coding: utf-8 -*-
"""出网 TLS 策略的**唯一实现**：默认严格校验，失败即拒绝，降级必须显式。

为什么要有这个模块（issue #59 + #50 S2）：

- provider 的连通性测试曾**有意构造不校验证书的上下文**（Windows 上为绕开证书库
  而走的那条捷径），并在上面发送 `Authorization: Bearer <api_key>`，而目标是
  **用户自己填的公网地址**——key 会在未校验的连接上暴露给中间人；
- resume / jobs 两处出网调用没传上下文，证书库损坏的机器上直接抛
  `ASN1: NOT_ENOUGH_DATA` 原文（用户既看不懂、也不知怎么修）；
- IMAP 侧（`tools/imap_fetch.py`）已有一套「默认严格 → 失败即拒绝 → 仅
  `JOBWS_IMAP_TLS=insecure` 时降级」的实现。本模块把它泛化成唯一真值，让三处
  HTTP 出网与 IMAP 共用同一个判定，避免"多份近似实现、口径各差一点"。

口径（五条，`tests/test_tls_policy.py` 逐条钉住）：

1. 先试 `ssl.create_default_context()`：成功即为严格上下文（校验主机名 + 证书）；
2. 系统证书库加载失败（典型是 Windows 证书库损坏的 ASN1 错误，`SSLError`/`OSError`）
   且该功能**已显式设 `insecure`** → 降级。用户的明确选择优先于自动兜底：连自签
   证书的服务器时，内置 CA 一样验不过，覆盖掉显式意图只会让人更困惑；
3. 未显式降级 → **回退到随包分发的内置 CA 清单**（certifi 的 `cacert.pem`）。这仍是
   **严格**上下文：校验主机名与证书链，只是信任源从本机库换成随包根——所以它不是
   降级、不需要任何环境变量。本机库坏、或本机 OpenSSL 与它不兼容时，这是不依赖
   本机状态的第二条路（2026-09-14 实测：conda 3.8 环境的旧 OpenSSL 读系统库必失败，
   而 3.12 成功；修 OpenSSL 是治本，这条回退是止血）；
4. 内置 CA 也不可用（没装 certifi，或它自身加载失败）→ **默认拒绝**，消息含
   `certmgr.msc` 排查指引、显式降级变量名，以及 purpose（是哪条功能在出网）；
5. 只有该变量（容忍大小写与首尾空格——它是人手敲的）等于 `insecure` 才降级，
   且降级后的上下文确实把证书校验与主机名校验都关掉了（不是"以为降级了"）——
   测试逐项断言，别在这里复述字面写法：`tests/test_tls_wiring.py` 的扫描
   按形状计数放行，本文件里多写一处字面量会被它抓住（真实防线不靠注释）。

**刻意不做的一件事：不缓存上下文。** `create_default_context()` 每次都要枚举系统
证书库（已知慢路径），但缓存会把"用户刚修好证书库却仍然失败"变成幽灵问题——
进程不重启就永远用着旧判定。单次出网的调用量级也不构成瓶颈。
"""

from __future__ import annotations

import os
import ssl

# 显式降级变量的取值：除了这一个词，任何取值都不降级（见口径第 3 条）。
INSECURE = "insecure"

# 两个域各自的降级变量名，调用点从这里取，别在别处再写一遍字面量。
HTTP_ENV_VAR = "JOBWS_HTTP_TLS"
IMAP_ENV_VAR = "JOBWS_IMAP_TLS"


class TlsPolicyError(RuntimeError):
    """系统证书库不可用、且未显式降级时抛出。

    消息面向**用户**（会经 `ApiError` / `ImapFetchError` 透到界面上），所以必须
    写清「怎么办」，而不是只带异常原文。
    """


def outbound_ssl_context(purpose, env_var):
    """返回本次出网要用的 SSL 上下文，或直接拒绝。

    Args:
        purpose: 人话的功能名（如「Provider 连通性测试」「简历改写」）。只进错误
            消息——用户得知道是"哪一步"在出网。
        env_var: 该功能对应的显式降级变量名（HTTP 出网用 `HTTP_ENV_VAR`，
            IMAP 用 `IMAP_ENV_VAR`）。

    Raises:
        TlsPolicyError: 证书库不可用且未显式降级时。
    """
    try:
        return ssl.create_default_context()
    except (ssl.SSLError, OSError) as exc:
        # 捕 `OSError` 而不是只捕 `ssl.SSLError`：证书库故障在个别平台/版本上会
        # 抛成更外层的形态（`SSLError` 本身也是 `OSError` 子类，这里列出两者是
        # 为了让意图显式）。只认 `SSLError` 的话，这类故障既不降级、也拿不到出路
        # 文案——就退回了"用户看到原文"这个 #59 想消除的现象（独立审查 MINOR-1）。
        if os.environ.get(env_var, "").strip().lower() == INSECURE:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        fallback = _context_from_builtin_ca()
        if fallback is not None:
            # 第二条路：信任源换成随包 CA，仍是严格校验（口径第 3 条）。
            return fallback
        raise TlsPolicyError(
            "无法加载本机系统证书库、随包 CA 清单也不可用，%s无法校验证书（%s）。"
            "已拒绝连接：在未校验的连接上发送凭证可被中间人截获。"
            "出路：修复系统证书库（certmgr.msc 排查损坏的证书条目）；"
            "或设置环境变量 %s=insecure 显式跳过证书校验（不推荐，风险自负）。"
            % (purpose, exc, env_var))


def _builtin_ca_file():
    """随包 CA 清单的路径；未安装 certifi 时返回 None。

    单独成函数是为了**可测**：测试用替身分别模拟「内置 CA 可用」与「内置 CA 缺失」
    两条路，不必真去改动环境里的 certifi。
    """
    try:
        import certifi
    except ImportError:
        return None
    return certifi.where()


def _context_from_builtin_ca():
    """系统证书库不可用时的第二条路：随包 CA 清单（certifi）。

    仍是严格上下文——`create_default_context(cafile=…)` 会照常校验主机名与证书链，
    只是信任根不是本机库。因此这里返回的上下文**不需要**任何环境变量，也**不是**
    降级；certifi 缺失或它自身加载失败时返回 None，由调用方继续走「拒绝 / 显式降级」。
    """
    cafile = _builtin_ca_file()
    if not cafile:
        return None
    try:
        return ssl.create_default_context(cafile=cafile)
    except (ssl.SSLError, OSError):
        return None
