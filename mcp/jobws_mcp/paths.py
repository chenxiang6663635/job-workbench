# -*- coding: utf-8 -*-
"""工作区解析：与后端 `deps.py` **同口径**，但不 import fastapi。

为什么自己写一遍而不是直接 import `deps`：`deps.py` 第一行就
`from fastapi import ...`，而 MCP 包跑在独立的 3.10+ 环境里（主干后端为兼容
Python 3.8 把 pydantic 钉在 2.10 以下，与 MCP SDK 要求的 pydantic>=2.12
互斥——见 `.codebuddy/plans/后续优先级_2026-09-13.md` 第一节）。

所以这里只 import `pathres`：它只依赖 os/sys，零第三方依赖，且本来就是
「只读资源 / 可写数据」这条链路的单一事实源。剩下的几个常量与函数按
`deps.py` 的口径复刻（改动时必须同步改两边，故在此写明对应关系）。

**当前形态需要仓库在侧**：领域函数（tracker / report / jd_score）还在 `tools/`
下、没抽成可安装的包（那是 B8 的活），所以本包暂时与仓库共存，装成 wheel
会拿不到领域层。这里不复制一份 pathres 逻辑来「假装独立」——两套实现迟早
漂移；取而代之的是找不到仓库就明说，而不是抛一个没有上下文的 ImportError。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT_ENV = "JOBWS_REPO_ROOT"


def _locate_repo_root():
    """仓库根：环境变量优先，其次按包位置（mcp/jobws_mcp/ 上推两级）。"""
    env = os.environ.get(REPO_ROOT_ENV, "").strip()
    if env:
        return os.path.abspath(env)
    return os.path.dirname(os.path.dirname(_HERE))


REPO_ROOT = _locate_repo_root()
BACKEND_DIR = os.path.join(REPO_ROOT, "web", "backend")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

# tools/ 与 web/backend/ 都不是包，靠 sys.path 导入（与 tests/ 下的既有测试同法）
for _p in (BACKEND_DIR, TOOLS_DIR):
    if not os.path.isdir(_p):
        raise ImportError(
            "找不到工作台仓库（%s 不存在）。jobws-mcp 当前需要仓库在侧："
            "请以 editable 方式安装（pip install -e ./mcp），或用环境变量 %s "
            "指向仓库根。" % (_p, REPO_ROOT_ENV))
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pathres  # noqa: E402

# --- 与 deps.py 对齐的常量（改动时同步两边） ---
DEFAULT_WORKSPACE_NAME = "personal"          # deps.py:22
DIR_JOBS = "01_岗位池"                        # deps.py:25
DIR_TRACKING = "05_投递追踪"                  # deps.py:26
ENV_DATA_DIR = "JOBWS_DATA_DIR"              # pathres.ENV_DATA_DIR
ENV_WORKSPACE = "JOBWS_WORKSPACE"            # deps.py:30


class WorkspaceError(Exception):
    """工作区解析失败（越界或不存在）。

    自定义而不是复用后端的 ApiError：后者带着 HTTP 语义，而 MCP 侧要把
    失败讲成人话再交给宿主，不需要状态码。
    """


def data_root():
    """可写数据根（personal/ 的父目录），见 pathres.resolve_workspace_root。"""
    return pathres.resolve_workspace_root(pathres.resolve_root())[0]


def allowed_roots():
    """允许作为工作区父目录的根：应用根 + 可写数据根（去重）。对应 deps.py:52。"""
    roots = [pathres.resolve_root(), data_root()]
    out = []
    for r in roots:
        r = os.path.normpath(r)
        if r not in out:
            out.append(r)
    return out


def resolve_default_workspace(root=None):
    """默认工作区绝对路径。对应 deps.py:63。"""
    if root is None:
        root = data_root()
    name = os.environ.get(ENV_WORKSPACE, "").strip() or DEFAULT_WORKSPACE_NAME
    return os.path.normpath(os.path.join(root, name))


def resolve_workspace(name=None, must_exist=False):
    """解析工作区绝对路径。

    优先级：显式参数 > 环境变量 `JOBWS_WORKSPACE` > 默认工作区（受
    `JOBWS_DATA_DIR` 影响）。

    **越界必须拒绝**：后端对 `?ws=` 的约束是「只允许相对路径且落在允许根之内」
    （deps.py:126-132）。MCP 由宿主代用户调用，参数来自模型而非人手，
    少了这道检查等于给了任意目录读取能力——所以这里硬拒绝而不是警告。

    两处比后端更严（MCP 的参数来源更不可控）：
    - 比对前先 realpath：允许根内的符号链接 / junction 会读穿到链接目标；
    - 不允许「恰好等于根」：把仓库根当工作区，等于允许枚举仓库结构。
    """
    roots = [os.path.realpath(r) for r in allowed_roots()]
    name = (name or os.environ.get(ENV_WORKSPACE, "") or "").strip()

    if not name:
        path = os.path.normpath(resolve_default_workspace())
    elif os.path.isabs(name):
        path = os.path.normpath(name)
    else:
        # 相对工作区名按**数据根**解析。
        # 源码/便携形态下数据根就是应用根（pathres 的 portable 判定），与后端
        # deps.py:129「相对路径按 ROOT 拼」完全一致；打包形态下数据根是系统用户
        # 目录——那里才是用户数据真正所在，按安装目录拼只会指向一个空壳。
        # （不逐个根去试存在的目录：那会让同名工作区在不同形态下指向不同副本。）
        path = os.path.normpath(os.path.join(data_root(), name))

    real = os.path.realpath(path)
    if not any(real.startswith(r + os.sep) for r in roots):
        raise WorkspaceError(
            "工作区越出允许范围：%s（允许的根：%s）" % (path, "、".join(roots)))
    if must_exist and not os.path.isdir(real):
        raise WorkspaceError(
            "工作区不存在：%s（可先用 `python tools/jobws.py init --demo` "
            "生成一个）" % path)
    return real


def workspace_profile(workspace):
    """工作区是否已初始化：判定标准是含 `config/profile.md`（与后端
    `routers/workspace.py:44` 同一口径）。缺它时工具返回空集而不是报错——
    没数据不等于出错。"""
    return os.path.isfile(os.path.join(workspace, "config", "profile.md"))
