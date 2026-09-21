# -*- coding: utf-8 -*-
"""progress 路由包（2026-09-16 重构批）：/api/progress 下的七组资源。

原单文件 progress.py（839 行）按资源拆分；对外契约零变化——
routers/__init__ 侧与 main.py 的 `app.include_router(progress.router)`
一行未改（本包 __init__ 照旧暴露 `router`）。
"""
from fastapi import APIRouter

from . import (contacts, interviews, lineage, mails, offers,
               question_previews, questions, talks)

router = APIRouter(prefix="/api/progress")

# 注册顺序与拆分前的源码顺序一致（interviews → talks → mails → questions
# → contacts → offers → lineage；question_previews 紧随 questions，
# 2026-09-21 从那里拆出）；路径均为精确定义、彼此无前缀歧义。
for _m in (interviews, talks, mails, questions, question_previews,
           contacts, offers, lineage):
    router.include_router(_m.router)
