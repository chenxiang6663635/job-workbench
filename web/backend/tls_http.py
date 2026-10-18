# -*- coding: utf-8 -*-
"""HTTP 出网的统一入口：TLS 策略（`jobws_core.tls_policy`）+ 证书类错误的稳定 code。

为什么要有这层（issue #59）：三个出网调用点（provider 连通性测试 / JD 抓取 /
简历改写）原本各写各的，于是出现两种沉默失效——一处**有意关闭**了证书校验
（还在上面发 Bearer key），两处**根本没传上下文**，证书库损坏的机器上只能抛
ASN1 原文。策略收进 `tls_policy` 之后，错误翻译也收在这里，避免三份近似实现。

分工：

- `tls_policy` 管"能不能建立**可校验**的连接"（证书库不可用 → 拒绝，或用户显式降级）；
- 本模块管"证书类错误怎么变成界面能渲染的东西"（稳定 `error_code` + 参数）；
- **非证书类**的连接错误原样抛出——各调用点已有的连接文案
  （`provider.connectUnreachable` / `job.fetchUnreachable` 等）继续生效，
  这次改造不该顺手换掉用户已经见过的说法。

两个 code 的分工（前端按 `err.<code>` 查语言包）：

- `sys.certStoreUnavailable`：**本机**证书库加载失败 → 出路是修证书库（certmgr.msc）
  或显式降级，文案里给出口；
- `sys.certUntrusted`：**对端**证书不被信任（自签名或劫持）→ 不给降级出口——
  两条路的答案都不是关校验（与 #50 的 IMAP 判定同一口径）。
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.parse
import urllib.request

from jobws_core import outbound
from jobws_core import tls_policy

from apierror import ApiError


def public_only_redirect_handler():
    """只放行**公网**目标的重定向处理器（每一跳都复检，见 `outbound`）。

    为什么必须逐跳：`urlopen` 默认自动跟随 302，只在入口查一次等于给了
    "公网域名 → 302 到 169.254.169.254" 的旁路（CodeQL `py/full-ssrf` #2）。
    """
    class _PublicOnlyRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            outbound.assert_public_url(newurl)
            return urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, headers, newurl)

    return _PublicOnlyRedirect()


def _host_of(req):
    """从请求里取主机名，只用于文案参数（取不到就给空串，不要因此失败）。

    用 `urlsplit` 而不是直接读 `req.host`：后者不含端口以外的信息且对畸形
    URL 抛异常；文案参数不该有"再抛一个错"的副作用。
    """
    try:
        return urllib.parse.urlsplit(req.full_url).hostname or ""
    except ValueError:
        return ""


def _untrusted(req):
    host = _host_of(req)
    return ApiError(
        502, "sys.certUntrusted",
        "证书校验失败：系统证书库不信任 %s 的证书（可能自签名，也可能被中间人"
        "劫持）。不要为它关闭校验，请改用可信端点或检查网络环境。" % (host or "该地址"),
        host=host)


def open_url(req, timeout, purpose, public_only=False):
    """按统一策略打开出网请求，返回 urlopen 的响应对象（可直接 `with`）。

    Args:
        req: `urllib.request.Request`
        timeout: 秒
        purpose: 人话的功能名，进"证书库不可用"的用户文案（用户要知道是哪一步失败）
        public_only: **目标完全由用户提供**时置 True（当前只有 JD 抓取）——
            入口先过 `outbound.assert_public_url`，之后每一跳重定向再复检。
            LLM / 邮件增强这几个调用点**不要**开：它们可能合法指向本机
            （本地 Ollama、内网网关），那是用户自己配置的端点。
            附带说明：那几处把用户配置的 `base_url` 直接信任（且带凭据发出），
            属于"共享/导入工作区时凭据可能外发"的信任边界问题，不是 SSRF——
            正确的加固是提示用户核对来源，不是在本层禁本机地址。

    Raises:
        ApiError: `sys.certStoreUnavailable`（本机证书库加载失败且未显式降级）
            或 `sys.certUntrusted`（对端证书不被信任）。
        jobws_core.outbound.OutboundBlocked: `public_only=True` 且目标落在
            本机/内网/保留段（由调用点翻译成用户文案）。
        urllib.error.URLError: 其它连接问题**原样抛出**，由调用点按既有文案处理。
    """
    try:
        ctx = tls_policy.outbound_ssl_context(purpose, tls_policy.HTTP_ENV_VAR)
    except tls_policy.TlsPolicyError as exc:
        # 消息本体就是要给用户看的出路指引（certmgr.msc / 显式降级变量），
        # detail 原样带上；前端另有一份按 code 渲染的文案，两者口径一致。
        raise ApiError(502, "sys.certStoreUnavailable", str(exc))

    if public_only:
        outbound.assert_public_url(req.full_url)
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            public_only_redirect_handler())

        def _open():
            return opener.open(req, timeout=timeout)
    else:
        def _open():
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)

    try:
        return _open()
    except ssl.SSLCertVerificationError:
        # 少数路径不包 URLError（直接抛）——若只认 URLError，这类失败会掉进
        # 调用点的泛化兜底，用户拿不到"证书不被信任、不要关校验"这句判断。
        raise _untrusted(req)
    except urllib.error.URLError as exc:
        # urllib 默认把 TLS 错误包成 URLError(reason=SSLCertVerificationError)
        if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
            raise _untrusted(req)
        raise
