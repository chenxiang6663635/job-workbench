# -*- coding: utf-8 -*-
"""请求依赖：工作区解析与路径安全。

路径穿越防护：API 收到的任何相对路径（岗位目录名等）先归一化，
再确认仍在工作区内。本地单用户虽无攻击面，但这是要分发的产品的原型，
习惯从一开始养成。
"""

from __future__ import annotations

import os
import sys

from fastapi import Query, Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pathres  # noqa: E402
from apierror import ApiError  # noqa: E402

# 应用根（只读资源）。打包后 exe 同级，解包为仓库根。
ROOT = pathres.resolve_root()
DEFAULT_WORKSPACE_NAME = "personal"

# 各模块在工作区下的固定相对位置（与 CLI 约定一致）
DIR_JOBS = "01_岗位池"
DIR_TRACKING = "05_投递追踪"
DIR_RESUME = "02_简历工坊"

# 默认工作区环境变量。CLI --workspace 会优先覆盖它，其次回退 personal/。
ENV_WORKSPACE = "JOBWS_WORKSPACE"

# 响应头：回显本次请求实际服务的工作区。后端写入、前端自检、排障时人眼可读。
# 单一真值源在此处，main.py 的中间件与 CORS 白名单都引用它，避免字符串写两遍分叉。
WORKSPACE_HEADER = "X-Jobws-Workspace"

# `ws` 的近名错拼（issue #22）。FastAPI **默认忽略未知查询参数**：客户端把 `ws` 写成
# `workspace` 时参数被直接丢掉 → ws=None → 回退默认工作区（personal/，真实数据）→ 200。
# 只认这几个已知近名，不做全局参数白名单——那要手工维护每个端点的全部参数，
# 脆弱且容易误伤。
WS_NEAR_MISS = ("workspace", "ws_", "wks", "workspaces")


def data_root():
    """可写的数据根目录（personal/ 的父目录）。

    打包后若 exe 装在不可写位置（如 Program Files），会回退到系统用户目录，
    故工作区可能不在 ROOT 内。见 pathres.resolve_workspace_root。
    """
    return pathres.resolve_workspace_root(ROOT)[0]


def allowed_roots():
    """允许作为工作区父目录的根：应用根 + 可写数据根（去重）。"""
    roots = [ROOT, data_root()]
    out = []
    for r in roots:
        r = os.path.normpath(r)
        if r not in out:
            out.append(r)
    return out


def _inside_allowed_roots(full):
    """工作区绝对路径是否落在某个允许根的**内部**。

    必须是子目录而非根本身（`?ws=personal/../` normpath 到根 → 越界，
    test_ws_param_guard 记录了该行为）；比较前先 normcase，与
    routers/workspace.py 同口径——Windows 文件系统大小写不敏感、而
    字符串比较敏感（盘符大小写不同时正常名字会被误判越界）。
    """
    target = os.path.normcase(full)
    roots_norm = {os.path.normcase(r) for r in allowed_roots()}
    if target in roots_norm:
        # 等于任何允许根本身 → 越界。不只防「同根」：数据根恰好在应用根内时
        # （JOBWS_DATA_DIR 指向仓库内目录），数据根本身也满足「在应用根内部」
        # 的前缀判定——不显式排除就会 200 服务「所有工作区的父目录」
        # （独立审查 MINOR-1；routers/workspace.py 用同款「排除根本身」）。
        return False
    for root in roots_norm:
        if target.startswith(root + os.sep):
            return True
    return False


def resolve_default_workspace(root=None):
    """解析默认工作区绝对路径。

    基于可写数据根目录（而非应用根），保证打包后数据落在可写位置。
    优先级：环境变量 JOBWS_WORKSPACE（相对路径）→ 数据根下的 personal/。
    返回绝对路径（可能指向不存在的目录，调用方负责判断）。
    """
    if root is None:
        root = data_root()
    name = os.environ.get(ENV_WORKSPACE, "").strip() or DEFAULT_WORKSPACE_NAME
    return os.path.normpath(os.path.join(root, name))


def _reject_bad_param_name(request: Request) -> None:
    """近名错拼 / 大小写变体的参数名检查（issue #22 回归防线）。

    放在这里（而不是中间件里）是**刻意的**：中间件是后注册的在最外层，
    在里面直接 return 会绕过 CORSMiddleware，浏览器读不到那个 400 的正文，
    只会看到网络错误。走 HTTPException 才是正常错误路径。

    大小写不敏感地比对近名：查询参数名大小写敏感（HTTP 语义），
    `?Workspace=` 不在小写清单里就会被当未知参数丢掉——复现与 #22 一字不差
    的静默回退。大小写变体（PascalCase 脚本、Swagger 生成代码）与复数形式
    是同等常见的错拼来源；lower → 原始名，报错时能指出用户实际写的是什么。
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


def _resolve_relative_workspace(ws: str) -> str:
    """相对工作区名 → 绝对路径：**数据根优先**、应用根兜底（去重后逐个探测）。

    为什么不是只按 ROOT 拼：打包形态（NSIS 装到 Program Files 等不可写位置）
    数据根是系统用户目录——那才是工作区真正所在，按安装目录拼只会指向一个
    空壳（mcp/jobws_mcp/paths.py 同款结论）；而前端选中工作区后**必带 ws**，
    这条路径一旦拼错，桌面版多工作区切换直接 404。开发/便携形态下两候选
    相同（data_root() == ROOT），行为与历史完全一致。

    越界判定逐候选进行（fail-closed）：越界候选即使物理存在也不采用；
    两候选全越界 → 400，界内候选不存在 → 404。
    """
    seen = set()
    candidates = []
    for cand_root in (data_root(), ROOT):
        cand = os.path.normpath(os.path.join(cand_root, ws))
        key = os.path.normcase(cand)
        if key not in seen:
            seen.add(key)
            candidates.append(cand)

    full = None
    for cand in candidates:
        if not _inside_allowed_roots(cand):
            continue
        if os.path.isdir(cand):
            full = cand
            break

    if full is None:
        if not any(_inside_allowed_roots(c) for c in candidates):
            raise ApiError(400, "ws.outOfRange", "workspace 越出允许范围")
        raise ApiError(
            404, "ws.notFound",
            "工作区不存在: %s（先运行 tools/jobws.py init）" % ws,
            name=ws,
        )

    return full


def workspace_dir(request: Request, ws: str = Query(default=None, description="工作区相对路径")) -> str:
    """解析工作区绝对路径。缺省用可配置的默认工作区（personal/）。

    接受相对路径（供多工作区切换），拒绝绝对路径——后端只服务
    应用根或数据根之下的目录，不允许任意位置读写。

    解析结果会写入 `request.state.workspace`，由 main.py 的中间件以
    X-Jobws-Workspace 回显（issue #22）：让「实际服务的是哪个工作区」从
    不可见变为调用方一读就能察觉——静默返回别的工作区数据比报错危险得多。

    细节分别在 `_reject_bad_param_name`（参数名）与
    `_resolve_relative_workspace`（相对名解析）——规模闸门要求
    编排与细节分离（初版单函数越 80 行被拦，按提示拆分）。
    """
    _reject_bad_param_name(request)

    # 显式的空值（`?ws=`）多半来自拼模板串的第三方脚本：静默回退默认工作区
    # 与「静默回退即危险」的立场冲突，明确拒绝。前端只在选中工作区时才拼 ws，
    # 不会受影响。
    if ws is not None and not ws.strip():
        raise ApiError(400, "ws.empty", "`ws` 不允许为空（省略该参数即用默认工作区）")

    if not ws:
        full = resolve_default_workspace()
    else:
        if os.path.isabs(ws):
            raise ApiError(400, "ws.mustBeRelative", "workspace 必须是相对路径")
        full = _resolve_relative_workspace(ws)

    # 回显归一化后的工作区名，而不是原始输入串：`?ws=./personal` 服务的就是
    # personal，回显 `./personal` 会让按期望值比对的客户端误报不一致。
    request.state.workspace = os.path.basename(os.path.normpath(full))
    return full


def safe_join(workspace: str, *parts: str) -> str:
    """拼接 workspace 下的相对路径，越界即拒绝。

    parts 中不允许绝对路径与 .. 逃逸；返回归一化后的绝对路径，
    且保证以 workspace 为前缀。
    """
    for p in parts:
        if os.path.isabs(p) or ".." in p.split(os.sep) + p.split("/"):
            raise ApiError(400, "path.illegalSegment", "非法路径片段: %r" % p, part=p)

    full = os.path.normpath(os.path.join(workspace, *parts))
    if not (full == workspace or full.startswith(workspace + os.sep)):
        raise ApiError(400, "path.escape", "路径越出工作区")

    return full
