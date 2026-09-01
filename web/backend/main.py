# -*- coding: utf-8 -*-
"""求职工作台 Web 后端入口。

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

from routers import applications, dashboard, jobs, library, provider, workspace  # noqa: E402

app = FastAPI(title="求职工作台", version="0.1.0")


def _apply_workspace_env(cli_workspace=None):
    """让 deps.resolve_default_workspace 的默认值可被 CLI --workspace 覆盖。

    优先级：CLI --workspace > 环境变量 JOBWS_WORKSPACE > personal/。
    设置环境变量后，deps.workspace_dir 在无 ?ws= 时使用该默认值。
    """
    import deps
    if cli_workspace:
        os.environ[deps.ENV_WORKSPACE] = cli_workspace.strip()

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
app.include_router(workspace.router)
app.include_router(provider.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- 前端静态产物同源托管（Electron 桌面壳）----
# 若 web/frontend/dist 存在，则挂载为静态站点：`/` 返回 index.html，
# API 仍在 /api。这样 Electron 页面与 API 同源，无 CORS 问题，
# 前端 api.ts 的相对路径 /api/... 在 dev（走 vite proxy）与生产（同源）都无需改动。
# 必须放在所有 API 路由注册之后，保证 /api 优先匹配。
DIST_DIR = os.path.join(ROOT, "web", "frontend", "dist")
if os.path.isfile(os.path.join(DIST_DIR, "index.html")):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="求职工作台 Web 后端")
    parser.add_argument("--workspace", default=None,
                        help="默认工作区（相对仓库根，如 personal 或 other_workspace）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    args = parser.parse_args()

    _apply_workspace_env(args.workspace)
    uvicorn.run(app, host=args.host, port=args.port)
