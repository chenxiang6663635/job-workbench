# -*- coding: utf-8 -*-
"""工作区解析：与后端 `deps.py` **同口径**，但不 import fastapi。

为什么自己写一遍而不是直接 import `deps`：`deps.py` 第一行就
`from fastapi import ...`，而 MCP 包跑在独立的 3.10+ 环境里（职责分层：
MCP 是宿主里的可选组件、不需要 fastapi，主干也不需要 MCP SDK；依赖面
不同，不是约束冲突——见 `mcp/pyproject.toml` 的说明段）。

所以这里只 import `pathres`：它只依赖 os/sys，零第三方依赖，且本来就是
「只读资源 / 可写数据」这条链路的单一事实源。剩下的几个常量与函数按
`deps.py` 的口径复刻（改动时必须同步改两边，故在此写明对应关系）。

**「需要仓库在侧」的现状（2026-09-17 批 6 更新——诚实分级）**：
领域层已开始包化：`packages/jobws-core`（import 名 `jobws_core`）提供写入原语
（`workspace_io`）与文件锁（`filelock`），装上就有、wheel 也拿得到。但**领域层
主体**（`tracker` / `report` / `jd_score` 等）仍在 `tools/` 下，要等第二批才搬。

所以本模块**仍然需要仓库在侧**，但原因变了：从「MCP 装成 wheel 就整个废了」
缩小到「`tools/` 里的那部分还没搬完」。等第二批搬完，下面这段 sys.path 注入
连同 `JOBWS_REPO_ROOT` 的推导即可整段删除——届时才是真正的「装上就能用」。
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

# tools/ 与 web/backend/ 都不是包，靠 sys.path 导入（与 tests/ 下的既有测试同法）。
# 2026-09-17：领域层主体仍在 tools/，故这段暂时保留；第二批把它搬进
# jobws_core 之后，整段删除（届时 MCP 不再需要仓库在侧）。
for _p in (BACKEND_DIR, TOOLS_DIR):
    if not os.path.isdir(_p):
        raise ImportError(
            "找不到工作台仓库（%s 不存在）。领域层主体（tracker / report / "
            "jd_score 等）仍在 tools/ 下、第二批才搬进可安装包，所以本阶段 "
            "jobws-mcp 仍需要能看到仓库：把 MCP 装在与仓库同处的位置"
            "（pip install -e ./mcp），或用环境变量 %s 指向仓库根。"
            % (_p, REPO_ROOT_ENV))
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pathres  # noqa: E402

# 注入应用根：pathres 不再从 __file__ 推断（它要搬进可安装包，推断值会静默变成
# site-packages 的上层）。这里是「仓库在侧」的临时形态——**PR-B 删硬闸时**，
# REPO_ROOT 连同 _locate_repo_root 整段消失，注入改由包内 pathres 与数据根协作。
pathres.set_app_root(REPO_ROOT)


def _warn_if_domain_package_missing():
    """领域包 `jobws-core` 没装时提示一句——**只提示，不阻断**。

    不 raise 的原因：旧路径 shim（`tools/filelock.py` / `tools/workspace_io.py`）
    在包没装时会退化为源码形态（把包的 src 加进 sys.path 再 import），功能
    一点不减——但那不是目标形态，装了才算数。

    走 stderr 而不是 print：MCP 的 **stdout 是 stdio 协议通道**，print 会污染它。
    """
    try:
        import jobws_core  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "[jobws-mcp] 提示：领域包 jobws-core 未安装，已退化为源码形态"
            "（旧路径 shim 会自行找到它）。目标是装上就能用："
            "pip install -e packages/jobws-core\n")


_warn_if_domain_package_missing()

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
        # 相对工作区名按**数据根**解析——本模块**有意比后端更严**：只认这一个
        # 根，不逐个根去试存在的目录（那会让同名工作区在不同形态下指向不同
        # 副本）。打包形态下数据根是系统用户目录——那里才是用户数据真正所在，
        # 按安装目录拼只会指向一个空壳。（后端 ?ws= 自 2026-09-16 起为「数据根
        # 优先 + 应用根兜底」的两候选解析，可达集合比这里大。）
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
