# -*- coding: utf-8 -*-
"""API 错误的结构化出口：**加法**改造，detail 照旧。

为什么是加法而不是替换：

- `detail` 是既有契约（测试、调试脚本、CLI 之外的第三方调用都在读它），换掉它
  等于把一处改动摊到所有调用方；
- 界面语言该由**渲染方**决定，后端不该猜。后端只多给一个稳定的语义标识
  （`error_code`）与它的参数（`error_params`），前端拿自己的语言包渲染。

于是英文界面看到的是英文、中文界面看到的是中文，而 detail 仍然是那句可直接
贴进 issue 的中文原文——三者不冲突。

用法：

    raise ApiError(422, "app.reasonRequired", "进入终态 `已挂` 时必须填写「状态原因」",
                   stage="已挂")

**code 的命名口径**：`<域>.<语义>`，域与 routers 对齐（ws / path / app / status /
job / progress / resume / imap / provider / lib / sys / approval）。同一个语义在不同
路由里必须复用同一个 code——前端语言包按 code 给一份文案，各写各的就会漂移。
"""

from __future__ import annotations

import errno

from fastapi import HTTPException

from jobws_core import outbound

# OSError 的 errno → **用户能动手**的一句话。**不要回传异常原文**
# （CodeQL `py/stack-trace-exposure` #186-190）：`str(OSError)` 带绝对路径与英文
# errno 文本，既可能泄漏本地目录结构，也不比这句话更有用。原文进日志给维护者。
_OS_ERROR_HINTS = {
    errno.ENOSPC: "磁盘空间不足",
    errno.EACCES: "没有写入权限（可能被杀毒软件或权限设置拦住）",
    errno.EPERM: "没有权限",
    errno.EROFS: "目标在只读位置（写保护？）",
    errno.ENAMETOOLONG: "路径太长",
    errno.EBUSY: "目标正被其他程序占用",
}


def os_error_reason(errno_value):
    """errno（**int，不是异常对象**）→ 用户能动手的一句话；查不到给「详见应用日志」。

    为什么收 int 而不是异常：函数一旦拿到异常对象，返回值就带着污点——CodeQL
    认不出我们这张映射表是 sanitizer（与 #2 SSRF / #194 同类：自定义校验器不被
    识别）。在**调用点**把 `exc` 折成 `exc.errno`（一个 int），污点就断在那里。
    调用形如：os_error_reason(getattr(exc, "errno", None))
    """
    return _OS_ERROR_HINTS.get(errno_value, "详见应用日志")


class ApiError(HTTPException):
    """带语义 code 的 HTTPException。

    `params` 只放**渲染文案真正用得到的**字段（阶段名、目录名、id 等），
    不要把整个请求体塞进来——它会被原样回给前端。
    """

    def __init__(self, status_code: int, code: str, detail: str, **params):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.params = params


def outbound_blocked(exc, invalid_code, blocked_code):
    """`jobws_core.outbound.OutboundBlocked` → 用户可读的 422。

    为什么收在这里而不是各路由里写：**同一份拒绝会在两处抛出**——入口检查
    （`fetch_jd` 自己查一次）与「重定向阶段复检」（`tls_http` 逐跳复检）。
    两处必须给出同一份契约（状态码 / code / 参数集），各写一遍迟早漂移；
    `test_error_code_params` 只核对参数集，保证不了状态码与文案口径。
    """
    if exc.reason == outbound.REASON_URL:
        # 畸形 URL（`:abc` / 越界端口 / 方括号没闭合）：链接写得不对，不是指向内网。
        # 该 code **不带参数**（与其它抛出点一致，见 `test_error_code_params`）。
        return ApiError(422, invalid_code,
                        "链接格式不对（端口或方括号），请填写完整的 http(s) 链接")
    return ApiError(
        422, blocked_code,
        "无法抓取这个链接（%s）：它指向本机或内网地址，或解析不到公网地址。"
        "请换成公网可访问的岗位页面。" % (exc.host or "未知主机"),
        host=exc.host or "")
