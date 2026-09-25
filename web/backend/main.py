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

from routers import registry as route_registry  # 路由登记表：见 routers/registry.py（顺序有约束）

# ---- 启动前检查（解释器基线与监听边界）----
# 2026-09-25 收口批：两段检查整体移到 web/backend/preflight.py（main.py 因新增
# 监听边界检查越过 300 行规模预算；检查的共性都是"启动之前决定该不该起"）。
# 这里 re-export 函数名，测试（main.interpreter_verdict / main.is_loopback_host）
# 与调用方照旧可用；preflight 只含纯函数，import 无副作用。
from preflight import enforce_interpreter, interpreter_verdict, is_loopback_host  # noqa: E402,F401

logger = logging.getLogger("jobworkbench")

enforce_interpreter()


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

    **设置后立即预检**（2026-09-25 收口批，审计 P1-A）：配置越界在这里就报错
    退出（退出码 2，与解释器拒收同码），而不是启动成功、等到每个请求才 400——
    双击 exe 场景的配置错误应该第一秒被响亮指出（_pause_if_frozen 兜住
    窗口可见性）。
    """
    import deps
    if cli_workspace:
        os.environ[deps.ENV_WORKSPACE] = cli_workspace.strip()
    try:
        deps.resolve_default_workspace()
    except deps.ApiError as exc:
        print("[job-workbench] 默认工作区配置越界：%s" % exc.detail, file=sys.stderr)
        _pause_if_frozen()
        raise SystemExit(2)

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
# 注意本中间件注册在 `if index.html 存在` 的静态托管块**之外**——那个块里的缓存中间件在没有前端 dist 时（CI、纯 API 场景）根本不会注册。
@app.middleware("http")
async def _workspace_guard(request: Request, call_next):
    response = await call_next(request)
    # 依赖解析在路由内部完成，故回显要等 call_next 之后读 request.state
    served = getattr(request.state, "workspace", None)
    if served:
        response.headers[WORKSPACE_HEADER] = served
    return response


route_registry.register(app)


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
    保持控制台打开等人按回车；源码模式终端本来就不会闪退，无需等待。

    **只对交互式终端暂停**（2026-09-25 收口批，四端复核发现）：桌面壳以
    stdio: pipe 拉起后端且不关闭 stdin 时，input() 会永久阻塞——进程不退、
    壳的 exit 回调不来，用户 30 秒后看到「启动超时」弹窗、真实原因只留在
    日志里；CI 冒烟此前用 DEVNULL 绕开的正是同一行为。
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return          # 非交互（管道 / DEVNULL）：停了也没人能按回车
    except (AttributeError, ValueError):    # stdin 被替换成不可判定的对象
        return
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
                        help="默认工作区名（相对数据根/应用根，如 personal；越界值会被拒绝）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--host", default="127.0.0.1",
                        help="监听地址（非本机回环需同时传 --unsafe-network-api）")
    parser.add_argument("--unsafe-network-api", action="store_true",
                        help="显式承认风险：把**没有鉴权**的本地 API 暴露到非回环地址")
    args = parser.parse_args()

    if not is_loopback_host(args.host):
        if not args.unsafe_network_api:
            print("错误：--host %s 会把**没有任何鉴权**的数据 API 暴露到本机之外。"
                  % args.host, file=sys.stderr)
            print("本机使用不需要改 --host；确要让同网络访问，请显式加 "
                  "--unsafe-network-api（同网络可访问者都能读写工作区数据）。",
                  file=sys.stderr)
            _pause_if_frozen()
            sys.exit(2)
        print("警告：--unsafe-network-api 已生效——API 无鉴权，监听 %s 时"
              "同网络可访问者都能读写你的工作区数据。" % args.host)

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
