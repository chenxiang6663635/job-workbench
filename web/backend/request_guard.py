# -*- coding: utf-8 -*-
"""请求参数名防线：`ws` 的近名错拼与大小写变体（issue #22）。

为什么独立成件：`deps.py` 在 2026-10-16 双根收口批撞了 300 行规模闸门，而这一块
与「根解析 / 安全拼接」不是一件事——它只依赖 `ApiError` 与 `Request`，搬出来
之后两边的纪律都能一眼读完（同款先例：`iocaps.py` / `ro_files.py`）。

**必须留在依赖层、不能挪进中间件**，是刻意的：中间件是后注册的在最外层，在里面
直接 return 会绕过 CORSMiddleware，浏览器读不到那个 400 的正文，只会看到网络错误。
走 HTTPException 才是正常错误路径。
"""

from __future__ import annotations

from fastapi import Request

from apierror import ApiError

# `ws` 的近名错拼（issue #22）。FastAPI **默认忽略未知查询参数**：客户端把 `ws`
# 写成 `workspace` 时参数被直接丢掉 → ws=None → 回退默认工作区（personal/，真实
# 数据）→ 200。只认这几个已知近名，不做全局参数白名单——那要手工维护每个端点的
# 全部参数，脆弱且容易误伤。
WS_NEAR_MISS = ("workspace", "ws_", "wks", "workspaces")


def reject_bad_param_name(request: Request) -> None:
    """近名错拼 / 大小写变体的参数名检查（issue #22 回归防线）。

    大小写不敏感地比对近名：查询参数名大小写敏感（HTTP 语义），`?Workspace=` 不在
    小写清单里就会被当未知参数丢掉——复现与 #22 一字不差的静默回退。大小写变体
    （PascalCase 脚本、Swagger 生成代码）与复数形式是同等常见的错拼来源；
    lower → 原始名，报错时能指出用户实际写的是什么。
    """
    lower_keys = {}
    for key in request.query_params.keys():
        lower_keys.setdefault(key.lower(), key)

    for bad in WS_NEAR_MISS:
        if bad in lower_keys:
            raise ApiError(
                400, "ws.unknownParam",
                "未知参数 `%s`；工作区参数名是 `ws`（例如 ?ws=personal）" % lower_keys[bad],
                name=lower_keys[bad],
            )

    # 合法名 `ws` 的大小写变体（`WS` / `Ws`）单独处理：不能把它放进近名清单
    # （归一化后就是 `ws`，会与合法请求混淆），但它同样会被 FastAPI 静默忽略。
    if "ws" in lower_keys and lower_keys["ws"] != "ws":
        raise ApiError(
            400, "ws.unknownParamCase",
            "未知参数 `%s`；工作区参数名是**小写的** `ws`" % lower_keys["ws"],
            name=lower_keys["ws"],
        )
