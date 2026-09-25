# -*- coding: utf-8 -*-
"""工作区解析：与后端 `deps.py` **同口径**，但不 import fastapi。

为什么自己写一遍而不是直接 import `deps`：`deps.py` 第一行就
`from fastapi import ...`，而 MCP 包跑在独立的解释器环境里（3.12+，与领域包
同基线；此处曾写 3.10+ 是领域层搬迁完成前的旧基线——2026-09-25 收口批订正）（职责分层：
MCP 是宿主里的可选组件、不需要 fastapi，主干也不需要 MCP SDK；依赖面
不同，不是约束冲突——见 `mcp/pyproject.toml` 的说明段）。

所以这里只 import `pathres`：它只依赖 os/sys，零第三方依赖，且本来就是
「只读资源 / 可写数据」这条链路的单一事实源。剩下的几个常量与函数按
`deps.py` 的口径复刻（改动时必须同步改两边，故在此写明对应关系）。

**「装上就能用」（2026-09-19 批 6 第二批 PR-B）**：领域层已全部搬进
`jobws_core`（含 `pathres`），本模块原先那段「sys.path 注入 + `JOBWS_REPO_ROOT`
推导 + 找不到仓库就 ImportError」的硬闸已整段删除。现在 `jobws-mcp` 装在哪都行。

一处**口径变化**：`allowed_roots()` 从「应用根 + 数据根」收敛为**只有数据根**。
源码形态下两者本来就常常相同（仓库根与数据根同处），而独立安装后「应用根」不再
存在——继续保留它就得重新发明一个（site-packages 旁边？那正是 `pathres` 在警告的
「把用户数据写进 Python 安装目录」）。收敛到数据根也更符合本包的安全意图：
给宿主的受控通道，不该放开任意目录。
"""

import os
import sys

# 硬闸已删（2026-09-19 PR-B）：下面一行是**唯一**的领域层依赖，且它只依赖 os/sys。
# 缺了它就是装错了（`mcp/pyproject.toml` 已声明 jobws-core），导入期直接报错最清楚。
# 2026-09-25 收口批：归属判定收口到同包的 `containment`（路径包含原语，Web 同源）。
from jobws_core import containment, pathres  # noqa: E402

# 给 pathres 一个「应用根」＝**数据根**，且**必须在此刻**——领域层（`tracker/_core`、
# `jd_score`）在**导入期**就求值 `ROOT`，晚一步下面的 import 直接 RuntimeError。
#
# 为什么给的是数据根而不是「应用目录」：本包没有那个概念（`template/` 与 `dist/`
# 都不随包发），数据根是它真正需要的那个（工作区在它下面）。领域层里靠 ROOT 找的
# 东西（如 `jd_score` 的 `template/profiles`）在独立安装下不存在，各自有回退
# ——`resolve_profile` 会看工作区自己的 `config/`。
pathres.set_app_root(
    os.environ.get("JOBWS_DATA_DIR", "").strip() or pathres.user_data_dir())

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
    """可写数据根（personal/ 的父目录）——**只**走数据根的优先级链。

    刻意**不给** pathres 传应用根：本包现在装在哪都行，而
    `resolve_workspace_root` 的 portable 分支会把「可写目录」当数据根——
    传 site-packages 进去，就等于把用户数据写到 Python 安装目录旁边
    （pathres 自己的注释正在警告这件事）。所以这里只认两条：
    `JOBWS_DATA_DIR` → 系统用户目录（与 pathres 的第三级同源）。
    """
    env_dir = os.environ.get(ENV_DATA_DIR, "").strip()
    if env_dir:
        return os.path.abspath(env_dir)
    return pathres.user_data_dir()


def allowed_roots():
    """允许作为工作区父目录的根：**只有数据根**（口径变化见模块 docstring）。

    原先还含「应用根」是为了源码形态（那时数据根就是仓库根）；独立安装后
    「应用根」不存在，而沿用 `pathres.resolve_root()` 会要求宿主注入它——
    本包的价值恰恰是不必（见本批的目标）。
    """
    return [os.path.normpath(data_root())]


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

    仍比后端更严的一处（MCP 的参数来源更不可控）：不允许「恰好等于根」——
    把仓库根当工作区，等于允许枚举仓库结构。归属判定本身 2026-09-25 起与
    Web 同源（`jobws_core.containment`，realpath + commonpath；此前本条记的
    「比对前先 realpath」是 MCP 独有的加严，漂移已收口）。
    """
    roots = allowed_roots()
    name = (name or os.environ.get(ENV_WORKSPACE, "") or "").strip()

    if not name:
        path = os.path.normpath(resolve_default_workspace())
    elif os.path.isabs(name):
        path = os.path.normpath(name)
    else:
        # 越界写法与 Web 默认工作区同口径（2026-09-25 收口批）：`..` 段与盘符段
        # （`C:foo`）此前 Windows / Linux 行为不同（realpath 兜住 vs 当普通名字
        # 通过），现在两平台一致拒绝；绝对路径走上面单独分支（既有语义＝仅
        # 数据根内通过）。
        reason = containment.escape_reason(name)
        if reason:
            raise WorkspaceError(
                "工作区名含越界写法（%s）：%s（只接受数据根内的相对目录名）"
                % (reason, name))
        # 相对工作区名按**数据根**解析——本模块**有意比后端更严**：只认这一个
        # 根，不逐个根去试存在的目录（那会让同名工作区在不同形态下指向不同
        # 副本）。打包形态下数据根是系统用户目录——那里才是用户数据真正所在，
        # 按安装目录拼只会指向一个空壳。（后端 ?ws= 自 2026-09-16 起为「数据根
        # 优先 + 应用根兜底」的两候选解析，可达集合比这里大。）
        path = os.path.normpath(os.path.join(data_root(), name))

    if not containment.within_any(path, roots):
        raise WorkspaceError(
            "工作区越出允许范围：%s（允许的根：%s）"
            % (path, "、".join(containment.real(r) for r in roots)))
    real = containment.real(path)
    if must_exist and not os.path.isdir(real):
        raise WorkspaceError(
            "工作区不存在：%s（请先在你打开的工作台里初始化，"
            "或设置 JOBWS_DATA_DIR 指向数据根）" % path)
    return real


def resolve_within_workspace(workspace, value, label="目录"):
    """校验「必须是工作区内相对路径」的工具入参，返回 (规范化绝对路径, 相对路径, 错误)。

    为什么单独一层：MCP 工具的路径参数可能由**模型代传**（如 tools_writable 的
    `module_dir`），四类越界写法都得在工具层先拒——
      ① 绝对路径（os.path.join 会当成新根）；
      ② `..` 段（翻出工作区）；
      ③ 盘符相对路径（`C:foo`：`isabs()==False`、不含分隔符，join 时却重置根——
         2026-09-23 实测，`join(ws, "C:foo")` 直接得到 `C:foo`，工具会去扫盘根）；
      ④ 空值。
    最后 realpath 二次校验：工作区内的符号链接 / junction 读穿到外面同样算越界
    （与 `resolve_workspace` 的口径一致）。第二个返回值是规范化后的相对路径
    （统一正斜杠、去掉空段与 `.`），供领域层按相对语义继续使用。
    """
    raw = (value or "").strip()
    if not raw:
        return None, None, "%s 不能为空" % label
    normalized = raw.replace("\\", "/")
    if os.path.isabs(raw) or os.path.isabs(normalized):
        return None, None, "%s 必须是工作区内的相对路径（不能是绝对路径）：%s" % (label, raw)
    segments = [seg for seg in normalized.split("/") if seg not in ("", ".")]
    if not segments:
        return None, None, "%s 不能为空" % label
    if any(seg == ".." for seg in segments):
        return None, None, "%s 不能包含 .. 段：%s" % (label, raw)
    if any(":" in seg for seg in segments):
        return None, None, ("%s 不能包含盘符（`C:foo` 这类盘符相对路径会让 join 重置到"
                             "盘根）：%s") % (label, raw)
    ws_real = containment.real(workspace)
    real = containment.real(os.path.join(ws_real, *segments))
    if not containment.is_within_or_equal(real, ws_real):
        return None, None, "%s 越出工作区：%s" % (label, raw)
    return real, "/".join(segments), None


def workspace_profile(workspace):
    """工作区是否已初始化：判定标准是含 `config/profile.md`（与后端
    `routers/workspace.py:44` 同一口径）。缺它时工具返回空集而不是报错——
    没数据不等于出错。"""
    return os.path.isfile(os.path.join(workspace, "config", "profile.md"))
