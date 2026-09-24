# -*- coding: utf-8 -*-
"""求职工作台 Web 后端入口。

本地原型，仅监听 localhost。数据层是 personal/ 下的 Markdown 与 CSV，
后端不复制数据，直接读写文件——与 CLI 共享同一份数据源。
"""

from __future__ import annotations

import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 让 web/backend 能 import pathres 与 tools/ 下的现有脚本（tracker、jd_score、report 等）
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from jobws_core import pathres  # noqa: E402

# 注入应用根：**必须在导入 deps 之前**——deps 在模块顶层就调 resolve_root()。
# 解包形态下这里就是仓库根：`_BACKEND_DIR` 已经是 web/backend，**再上溯两级**
# （web/backend → web → 仓库根）。打包形态不参与（resolve_root 的 frozen 分支用
# exe 同级）。注入是显式的：pathres 不再从 __file__ 推断，因为那套推断搬进可安装
# 包后会静默指向 site-packages。
pathres.set_app_root(os.path.dirname(os.path.dirname(_BACKEND_DIR)))

from apierror import ApiError  # noqa: E402
from deps import WORKSPACE_HEADER  # noqa: E402
from errdetail import public_detail  # noqa: E402

# 路径经 pathres 解析：打包（onedir）指向 exe 同级，解包指向仓库根
ROOT = pathres.resolve_root()
TOOLS = pathres.resolve_tools_dir(ROOT)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from routers import application_delete, applications, approvals, dashboard, imap, imap_facts, jobs, library, prep, progress, provider, resume, snapshot, sync, system, workspace  # noqa: E402

# ---- 解释器基线（与 tests/conftest.py 的护栏、CONTRIBUTING 的口径同源）----
#
# **技术要求是 ≥3.9**：IMAP 路径把超时交给 `imaplib.IMAP4_SSL(timeout=…)`，这个参数
# 3.9 才有。3.8 上它不是"连不上邮箱"，而是抛 `TypeError: unexpected keyword argument`
# —— 2026-09-15 实测：界面上只看到一句裸的 "Internal Server Error"，既没有错误码也没有
# 指向（那台机器上后端被 conda 的 3.8 启动了）。所以太旧的解释器必须**在启动时**拒绝，
# 而不是等到用户点「拉取邮件」。
#
# **支持基线是 3.12**：CI 与打包只验证它；3.9–3.11 能用但未经验证，启动时给一条警告
# 而不是拒绝——不把"未验证"说成"不能用"。
IMAP_MIN_PY = (3, 9)
SUPPORTED_MIN_PY = (3, 12)
logger = logging.getLogger("jobworkbench")


def interpreter_verdict(version_info):
    """按解释器版本给出 ("ok" | "warn" | "refuse", 说明)。纯函数，便于测试。"""
    current = tuple(version_info[:2])
    if current < IMAP_MIN_PY:
        return "refuse", (
            "本应用需要 Python %d.%d+ 才能启动：IMAP 路径使用 imaplib 的 timeout 参数，"
            "%d.%d 上会直接抛 TypeError。请改用 Python %d.%d 启动后端"
            "（或使用桌面安装包——它自带运行时）。"
            % (IMAP_MIN_PY[0], IMAP_MIN_PY[1], current[0], current[1],
               SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1]))
    if current < SUPPORTED_MIN_PY:
        return "warn", (
            "当前解释器 %d.%d 低于支持基线 %d.%d（CI 与打包只验证后者）：可以运行，"
            "但未经验证——出问题请先用 %d.%d 复现。"
            % (current[0], current[1], SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1],
               SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1]))
    return "ok", ""


def _enforce_interpreter():
    verdict, message = interpreter_verdict(sys.version_info)
    if verdict == "refuse":
        print("[job-workbench] 解释器不满足技术要求：" + message, file=sys.stderr)
        raise SystemExit(2)
    if verdict == "warn":
        print("[job-workbench] 警告：" + message, file=sys.stderr)


_enforce_interpreter()

app = FastAPI(title="求职工作台", version="0.1.0")


@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    """把 ApiError 渲染成 {"detail", "error_code", "error_params"?}。

    detail 原样保留：前端语言包里查不到对应 code（例如旧前端配新后端）时
    直接显示它，不会退化成「只看到一串 err.xxx」。参数只在非空时才带上，
    避免响应体里多一个恒为 {} 的字段。
    """
    content = {"detail": exc.detail, "error_code": exc.code}
    if exc.params:
        content["error_params"] = exc.params
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    """未预期异常也必须说人话：绝不把裸 "Internal Server Error" 丢给界面。

    为什么需要它（2026-09-15 实测）：后端跑在低于技术要求的解释器上时，`imaplib`
    抛的 TypeError 没有任何一层接住，界面只看到一句英文裸 500——没有错误码、没有
    指向，用户能做的只有猜。未捕获异常要么是我们的 bug、要么是环境错，两者都该
    同时得到：**日志里的完整 traceback**（定位用）与**界面上的结构化人话**
    （`server.error` + 一句可复制的说明）。这条与 `_api_error_handler` 一起构成
    "错误一律走契约"的兜底：ApiError 是预期路径，这里是兜底路径。
    """
    detail = "%s: %s" % (type(exc).__name__, exc)
    logger.exception("未捕获异常（%s %s）：%s", request.method, request.url.path, detail)
    # 响应体用去路径版本：同样的信息、不含本机绝对路径
    safe = public_detail(exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误（%s）——完整信息见后端日志" % safe,
            "error_code": "server.error",
            "error_params": {"error": safe},
        },
    )


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
app.include_router(application_delete.router)  # 投递删除预览（批 D；applications.py 水位只许降故拆出）
app.include_router(approvals.router)
app.include_router(jobs.router)
app.include_router(progress.router)
app.include_router(library.router)
app.include_router(workspace.router)
app.include_router(provider.router)
app.include_router(imap.router)
app.include_router(imap_facts.router)  # 邮件解析（批 9；imap.py 水位只许降故单开）
app.include_router(resume.router)
app.include_router(system.router)
app.include_router(snapshot.router)  # 快照还原与演练（笔 2；system.py 水位只许降故单开）
app.include_router(sync.router)  # 批 8：工作区版本指纹（GUI 端同步用）
app.include_router(prep.router)  # 笔记：03_面试准备 / 04_知识库 只读浏览


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- 前端静态产物同源托管（Electron 桌面壳）----
# 若 web/frontend/dist 存在，则挂载为静态站点：`/` 返回 index.html，
# API 仍在 /api（Electron 页面与 API 同源，无 CORS）：前端 api.ts 的相对路径
# /api/... 在 dev（vite proxy）与生产都无需改动。
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


def _should_open_browser():
    """独立运行/双击 exe 时默认自动开界面（web 形态）。
    JOBWS_NO_BROWSER=1 关掉它——桌面端（Electron 已托着窗口）与 UI 冒烟都不需要再弹
    一个系统浏览器。此前桌面端漏传该变量，安装版启动会多开一个浏览器窗口。
    只认 "1"（容错首尾空白）："0" / "false" 这类直觉上表示「要开」的取值
    不应被静默改判为关闭（独立审查 M-1）。"""
    return os.environ.get("JOBWS_NO_BROWSER", "").strip() != "1"


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
                if _should_open_browser():
                    import webbrowser
                    webbrowser.open(url)
                _pause_if_frozen()
                sys.exit(0)
            print("错误：端口 %d 已被其他程序占用，无法启动。" % args.port)
            print("请关闭占用该端口的程序后重试（或改用 --port 指定其他端口）。")
            _pause_if_frozen()
            sys.exit(1)

        # 双击 exe 场景：启动成功后自动打开浏览器界面。
        # JOBWS_NO_BROWSER=1 关掉它——UI 冒烟（Playwright）会自己拉起后端，
        # 每跑一次就弹一个浏览器窗口既干扰开发、也会在 CI 上留下无谓的进程；
        # 桌面端（Electron）同理。
        if _should_open_browser():
            _open_browser_later(url)
        uvicorn.run(app, host=args.host, port=args.port)
    except Exception as e:  # noqa: BLE001 —— 双击场景必须给人话而非闪退
        print("后端启动失败：%s" % e)
        _pause_if_frozen()
        raise
