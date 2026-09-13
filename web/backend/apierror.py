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
job / progress / resume / imap / provider / lib / sys）。同一个语义在不同路由里
必须复用同一个 code——前端语言包按 code 给一份文案，各写各的就会漂移。
"""

from __future__ import annotations

from fastapi import HTTPException


class ApiError(HTTPException):
    """带语义 code 的 HTTPException。

    `params` 只放**渲染文案真正用得到的**字段（阶段名、目录名、id 等），
    不要把整个请求体塞进来——它会被原样回给前端。
    """

    def __init__(self, status_code: int, code: str, detail: str, **params):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.params = params
