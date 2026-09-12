# -*- coding: utf-8 -*-
"""求职工作台 Web 后端入口。

本地原型，仅监听 localhost。数据层是 personal/ 下的 Markdown 与 CSV，
后端不复制数据，直接读写文件——与 CLI 共享同一份数据源。
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# 让 web/backend 能 import pathres 与 tools/ 下的现有脚本（tracker、jd_score、report 等）
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pathres  # noqa: E402
from deps import WORKSPACE_HEADER  # noqa: E402

# 路径经 pathres 解析：打包（onedir）指向 exe 同级，解包指向仓库根
ROOT = pathres.resolve_root()
TOOLS = pathres.resolve_tools_dir(ROOT)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from routers import applications, dashboard, imap, jobs, library, progress, provider, resume, system, workspace  # noqa: E402

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
    # allow_headers 只管请求头；前端要**读取**响应头必须在这里显式暴露，
    # 否则 dev（5173 → 8765 跨源）下 api.ts 读到的是 null，自检会失效。
    expose_headers=[WORKSPACE_HEADER],
)

# ---- 工作区回显（issue #22）----
# 在响应上回显本次实际服务的工作区，把「静默错误」变成「一读就能察觉」。
# 近名错拼的**拒绝**不在这里，而在 deps.workspace_dir —— 中间件是后注册的在最外层，
# 在这里直接 return 会绕过 CORSMiddleware：浏览器读不到那个 400 的正文，只会看到
# 网络错误（tests/test_ws_param_guard.py::test_rejection_carries_cors_header 盯着这点）。
# 注意本中间件注册在 `if index.html 存在` 的静态托管块**之外**——那个块里的缓存中间件
# 在没有前端 dist 时（CI、纯 API 场景）根本不会注册。
@app.middleware("http")
async def _workspace_guard(request: Request, call_next):
    response = await call_next(request)
    # 依赖解析在路由内部完成，故回显要等 call_next 之后读 request.state
    served = getattr(request.state, "workspace", None)
    if served:
        response.headers[WORKSPACE_HEADER] = served
    return response


app.include_router(dashboard.router)
app.include_router(applications.router)
app.include_router(jobs.router)
app.include_router(progress.router)
app.include_router(library.router)
app.include_router(workspace.router)
app.include_router(provider.router)
app.include_router(imap.router)
app.include_router(resume.router)
app.include_router(system.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- 前端静态产物同源托管（Electron 桌面壳）----
# 若 web/frontend/dist 存在，则挂载为静态站点：`/` 返回 index.html，
# API 仍在 /api。这样 Electron 页面与 API 同源，无 CORS 问题，
# 前端 api.ts 的相对路径 /api/... 在 dev（走 vite proxy）与生产（同源）都无需改动。
# 必须放在所有 API 路由注册之后，保证 /api 优先匹配。
DIST_DIR = pathres.resolve_dist_dir(ROOT)
if os.path.isfile(os.path.join(DIST_DIR, "index.html")):
    from fastapi.staticfiles import StaticFiles

    # index.html 无 Cache-Control 时浏览器按启发式缓存旧文件，
    # 用户会一直加载旧 JS——表现为"改了功能但界面没变化"。故 HTML 强制
    # 协商缓存（no-cache：每次校验 ETag）；带内容 hash 的 assets 可长缓存。
    @app.middleware("http")
    async def _cache_policy(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        elif "/assets/" in path:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")


def _pause_if_frozen():
    """打包成 exe 双击运行时，出错若立即退出窗口会一闪而过，用户只看到"没反应"。
    保持控制台打开等人按回车；源码模式终端本来就不会闪退，无需等待。"""
    if getattr(sys, "frozen", False):
        try:
            input("\n按回车键关闭窗口...")
        except (EOFError, KeyboardInterrupt):
            pass


def _port_in_use(port):
    """端口是否已有进程监听。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_our_service(port):
    """端口上的服务是否为本工作台（health 探测）。"""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=2) as r:
            return b"ok" in r.read()
    except Exception:
        return False


def _open_browser_later(url, delay=1.5):
    """服务就绪前预约打开浏览器（uvicorn.run 会阻塞主线程，用定时器异步开）。"""
    import threading
    import webbrowser
    threading.Timer(delay, lambda: webbrowser.open(url)).start()


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
    url = "http://127.0.0.1:%d" % args.port

    try:
        if _port_in_use(args.port):
            if _is_our_service(args.port):
                # 已有本工作台服务在跑（可能是 dev 后端或另一个实例）：直接复用，开界面即可
                print("检测到服务已在运行，直接打开界面：%s" % url)
                import webbrowser
                webbrowser.open(url)
                _pause_if_frozen()
                sys.exit(0)
            print("错误：端口 %d 已被其他程序占用，无法启动。" % args.port)
            print("请关闭占用该端口的程序后重试（或改用 --port 指定其他端口）。")
            _pause_if_frozen()
            sys.exit(1)

        # 双击 exe 场景：启动成功后自动打开浏览器界面
        _open_browser_later(url)
        uvicorn.run(app, host=args.host, port=args.port)
    except Exception as e:  # noqa: BLE001 —— 双击场景必须给人话而非闪退
        print("后端启动失败：%s" % e)
        _pause_if_frozen()
        raise
