# -*- coding: utf-8 -*-
"""确认令牌的统一落盘入口（两段式的第二步）。

写类操作都走「预览（不落盘）→ 一次性令牌 → apply 落盘」（tools/approval.py）。
CLI/MCP 用它的 `apply`，网页端用本端点——「要写什么、写去哪里」都在令牌里、
不在请求里，所以这里**不接收**工作区或载荷参数。

`/api/workspaces/apply` 是更早的专用入口（初始化工作区用），行为与这里一致；
新接入的操作一律走本端点。

错误语义：
- 409 approval.conflict     —— 预览之后数据变了，已确认的写入不再安全（重新预览）；
- 422 approval.tokenInvalid —— 令牌不存在 / 已过期 / 已用过 / 载荷被改。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import approval
from apierror import ApiError

router = APIRouter(prefix="/api/approvals")


class ApprovalApplyBody(BaseModel):
    token: str


@router.post("/apply")
def apply_approval(body: ApprovalApplyBody):
    """凭令牌执行已确认的写入；令牌一次性，取走即焚（与 CLI 的 apply 同源）。

    刻意**不**接收工作区参数：令牌绑定的就是目标工作区，「要写哪里」在令牌里
    （与 /workspaces/apply 同一取舍——PR #100 的安全边界）。用户在 A 工作区预览
    后切到 B 再点确认，写入的仍是 A——这是确认书的语义，不是缺陷（跨宿主审查
    MINOR 确认过这一点）。
    """
    try:
        result = approval.apply(body.token)
    except approval.ApprovalConflict as exc:
        raise ApiError(409, "approval.conflict", str(exc))
    except approval.ApprovalError as exc:
        raise ApiError(422, "approval.tokenInvalid", str(exc))
    return {"ok": True, **result}
