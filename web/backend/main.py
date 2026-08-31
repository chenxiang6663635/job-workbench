# -*- coding: utf-8 -*-
"""秋招工作台 Web 后端入口。

本地原型，仅监听 localhost。数据层是 personal/ 下的 Markdown 与 CSV，
后端不复制数据，直接读写文件——与 CLI 共享同一份数据源。
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 让 web/backend 能 import tools/ 下的现有脚本（tracker、jd_score、report 等）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from routers import applications, dashboard, jobs, library  # noqa: E402

app = FastAPI(title="秋招工作台", version="0.1.0")

# 前端 Vite 开发服务器。本地原型，来源限定 localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(applications.router)
app.include_router(jobs.router)
app.include_router(library.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
