# -*- coding: utf-8 -*-
"""邮件 → 候选事实（批 9）：只读解析端点。

**为什么单独成文件**：`routers/imap.py` 的水位线只许降（约 300 行的规模闸门），
这里与 `application_delete.py` 同款处置——新能力单开一个 router，同级前缀、
同组边界。

四条边界（与 `routers/imap.py` 逐条一致）：

1. **只读**：把已拉到手的正文 / ICS 解释成候选事实就结束——不持锁、不落盘；
2. **无后台路径**：没有定时器、轮询或保活；每次调用都是一次纯计算；
3. **写回不在这里**：邮件台账走 `POST /api/progress/mails`，阶段更新走
   `POST /api/applications/apply-status-suggestion`（都由用户逐条确认触发）；
4. **同义不新造错误码**：空输入复用 `status.textRequired`。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apierror import ApiError
from deps import workspace_dir
from jobws_core import mail_facts, tracker

router = APIRouter(prefix="/api/imap")


class SuggestFacts(BaseModel):
    """正文与 ICS 都可选：有的邮件只有正文，有的只有日历邀请。

    `id` 用 Optional 而不是「str = None」：前端把「没选记录」序列化成 null 是
    最自然的写法，显式传 null 不该 422（与阶段 2 的 SuggestRequest 同款坑）。
    """
    原文: str = ""
    ics: str = ""
    id: Optional[str] = None


@router.post("/suggest-facts")
def suggest_facts(item: SuggestFacts, ws: str = Depends(workspace_dir)):
    """正文 / ICS → 候选事实（时间 / 会议链接 / 阶段 / 对应记录）。**只读。**

    追踪表只读一次用于记录匹配（`focus_id` 非空时按用户点选的那条，比子串匹配
    权威）；返回事实列表，写入与否由用户在界面逐条确认。
    """
    text = (item.原文 or "").strip()
    ics = (item.ics or "").strip()
    if not text and not ics:
        # 复用既有的同义 code（前端语言包已覆盖，避免同义两个码漂移）
        raise ApiError(422, "status.textRequired", "请先选择一封邮件或粘贴要解析的原文")

    rows = tracker.read_rows(ws)
    facts = mail_facts.extract_facts(text, ics_text=ics, rows=rows,
                                     focus_id=(item.id or "").strip())
    return {"facts": facts, "total": len(facts)}
