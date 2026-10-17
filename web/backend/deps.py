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
from jobws_core import containment, dataroot, pathres  # noqa: E402
from apierror import ApiError  # noqa: E402
from request_guard import reject_bad_param_name  # noqa: E402  （参数名防线，见该模块）

# 应用根（只读资源）。打包后 exe 同级，解包为仓库根。
ROOT = pathres.resolve_root()
DEFAULT_WORKSPACE_NAME = "personal"

# 各模块在工作区下的固定相对位置（与 CLI 约定一致）
DIR_JOBS = "01_岗位池"
DIR_RESUME = "02_简历工坊"
# 笔记（只读浏览）：03 放表达、04 放知识（见各自 README）
DIR_PREP = "03_面试准备"
DIR_KB = "04_知识库"

# 默认工作区环境变量。CLI --workspace 会优先覆盖它，其次回退 personal/。
ENV_WORKSPACE = "JOBWS_WORKSPACE"

# 响应头：回显本次请求实际服务的工作区。后端写入、前端自检、排障时人眼可读。
# 单一真值源在此处，main.py 的中间件与 CORS 白名单都引用它，避免字符串写两遍分叉。
WORKSPACE_HEADER = "X-Jobws-Workspace"

# 参数名防线（近名错拼 / 大小写变体）已拆到 `request_guard.py`：本文件撞 300 行
# 规模闸门时按职责归位，issue #22 的回归防线随之搬走（行为不变）。


def data_root():
    """可写的数据根目录（personal/ 的父目录）。

    解析优先级（A3，spec 决策 1）：`JOBWS_DATA_DIR` > **持久化选择** > legacy
    （便携判定 / 系统用户目录）——统一走 `dataroot.resolve_data_root`，不再
    直接问 pathres（否则 Web 端读不到用户通过 CLI / 控制面做出的选择）。
    legacy 分支行为不变：打包后若 exe 装在不可写位置（如 Program Files），
    仍回退到系统用户目录，故工作区可能不在 ROOT 内。
    """
    return dataroot.resolve_data_root(dataroot.form_for_process(), ROOT).path


def _root_source():
    """当前数据根的解析来源（`env | persisted | legacy_portable | legacy_userdata`）。

    直接取 `dataroot.resolve_data_root` 的 `source` 字段——**不另写一份** env /
    持久化判断（那正是「两个真源」的老毛病）。
    """
    return dataroot.resolve_data_root(dataroot.form_for_process(), ROOT).source


def allowed_roots():
    """允许作为工作区父目录的根（2026-10-16 双根收口）。

    两条分支，按「是否**显式选择**过数据根」区分：

    - `JOBWS_DATA_DIR` 或持久化选择生效 → **只有数据根**。此前这里还带应用根，
      于是「哪个根」有两个真源：列表按 `[应用根, 数据根]` 扫描并「同名只留
      第一个」，解析却按「数据根优先」；当前数据根里没有该名字时更会**静默
      回退到应用根的同名旧副本**（读旧数据、写也落在旧副本上——外部复核 P2
      的取证见 `tests/test_dual_root_same_workspace.py`）。
    - 从未选择（legacy 推导）→ 保留 `[应用根, 数据根]`：此时声明的数据根可能
      还不存在，应用根里的旧布局是唯一可能的位置（源码形态的老仓库就是这种）。
      **这不是跨根兜底**：没有第二份同名数据可混淆。

    MCP 侧结构上只有数据根（`mcp/jobws_mcp/paths.py` 模块 docstring 有理由）；
    能力边界见上：显式选择时四端对「工作区在哪」只有一个答案。
    """
    root = os.path.normpath(data_root())
    if _root_source() in ("env", "persisted"):
        return [root]
    app = os.path.normpath(ROOT)
    return [app] if app == root else [app, root]


def _inside_allowed_roots(full):
    """工作区绝对路径是否落在某个允许根的**内部**（realpath 判定，见原语）。

    必须是子目录而非根本身（`?ws=personal/../` normpath 到根 → 越界，
    test_ws_param_guard 记录了该行为）；数据根恰好在应用根内时
    （JOBWS_DATA_DIR 指向仓库内目录），数据根本身也满足「在应用根内部」——
    原语的「排除根自身」同时覆盖这个独立审查 MINOR-1 的形态。大小写口径由
    原语内部的 normcase 承接（Windows 文件系统大小写不敏感、字符串比较敏感，
    盘符大小写不同时正常名字会被误判越界）。

    2026-09-25 发布前收口批：判定的**唯一实现**是 `jobws_core.containment`
    （realpath + commonpath）——此前这里是 `normcase + startswith`，不解析
    符号链接，与 MCP 侧（早已 realpath）漂移。用 `strictly_within_any`
    （排除「等于任何根」）而不是 `within_any`：数据根 ⊆ 应用根时必须继续
    拒绝数据根本身（迁移时丢过这一条，`test_data_root_itself_is_not_a_workspace`
    当场抓住）。
    """
    return containment.strictly_within_any(full, allowed_roots())


def resolve_default_workspace(root=None):
    """解析默认工作区绝对路径。

    基于可写数据根目录（而非应用根），保证打包后数据落在可写位置。
    优先级：环境变量 JOBWS_WORKSPACE（相对路径）→ 数据根下的 personal/。
    返回绝对路径（可能指向不存在的目录，调用方负责判断）。

    **越界必须拒绝**（2026-09-25 收口批，审计 P1-A）：环境变量
    `JOBWS_WORKSPACE`（桌面壳 / CLI `--workspace` 写进去的取值）此前拼完
    **不做归属校验**——`JOBWS_WORKSPACE=../x` 会让后端静默服务允许根之外的
    目录，与「静默回退即危险」的立场自相矛盾。现在与显式 `?ws=` 走同一道闸：
    越界写法（绝对路径 / `..` 段 / 盘符相对）与经链接读穿的界外路径都
    fail-closed；配置错误的代价是 400，但文案直接指出去哪里改。
    """
    if root is None:
        root = data_root()
    name = os.environ.get(ENV_WORKSPACE, "").strip() or DEFAULT_WORKSPACE_NAME
    reason = containment.escape_reason(name)
    full = os.path.normpath(os.path.join(root, name))
    if reason or not _inside_allowed_roots(full):
        raise ApiError(
            400, "ws.outOfRange",
            "默认工作区越出允许范围（%s）：%s —— 请把 JOBWS_WORKSPACE / "
            "--workspace 改成允许根内的相对目录名（如 personal），"
            "或清掉该配置使用默认值。" % (reason or "经链接指向界外", name),
        )
    return full


def _resolve_relative_workspace(ws: str) -> str:
    """相对工作区名 → 绝对路径：**只在当前数据根内**解析（2026-10-16 收口）。

    为什么不再兜底应用根：打包形态下数据根在系统用户目录，那才是工作区真正
    所在（按安装目录拼只会指向空壳，审计 M-1）；而「数据根没命中就回退应用根」
    会让两个根里同名的旧副本被静默服务——读旧数据、写落在旧副本上（外部复核
    P2，取证见 `tests/test_dual_root_same_workspace.py`）。找不到就是 404；
    应用根里的遗留候选由 `/api/system/paths` 的诊断对象（`legacy_candidates`）
    列出，设置页据此引导迁移，不靠"读的时候顺手兜底"。
    开发/便携形态下 `data_root() == ROOT`，行为与历史完全一致。

    候选顺序 = **数据根优先**，其余允许根随后：显式选择时允许根只有一个，
    legacy 时才可能轮到应用根（见 `allowed_roots` 的两条分支）。

    越界判定沿候选进行（fail-closed）：越界候选即使物理存在也不采用；
    全部候选越界 → 400，界内候选不存在 → 404；名称的越界写法同 CLI/MCP 先拒。
    """
    reason = containment.escape_reason(ws)
    if reason:
        raise ApiError(
            400, "ws.outOfRange",
            "工作区名含越界写法（%s）：%s —— 只接受允许根内的相对目录名。" % (reason, ws))
    primary = os.path.normpath(data_root())
    roots = [primary] + [r for r in allowed_roots() if r != primary]
    seen = set()
    candidates = []
    for cand_root in roots:
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


def _require_usable_data_root():
    """unavailable 的 fail-closed 闸（spec §四）：失效时读 / 写 / 破坏性全拒。

    每请求只读一个文件 + 一次 stat（O(1)）——不做候选扫描（那是诊断面的事）。
    503 语义：服务当前无法访问其数据位置（本机可修复的配置 / 环境态），
    与 502（上游网关）区分。
    """
    if dataroot.persisted_unavailable():
        raise ApiError(503, "sys.dataRootUnavailable",
                       "数据根不可用：持久化选择指向的位置不存在或不可写——"
                       "请修复该路径或清除持久化选择后重试（`jobws doctor` 查看详情）。")


def require_unambiguous_data_root():
    """破坏性入口的歧义闸（spec §四）：多候选且都含真实工作区时拒绝。

    只给**能确证是破坏性**的入口调用（快照还原、删除预览）——普通读写不设闸
    （否则老用户升级后正常写操作会突然失败，违反兼容承诺）。候选扫描有界
    （每个候选一层、条目数封顶），且这些入口本就低频。
    """
    state = dataroot.detect_state(
        dataroot.form_for_process(), ROOT, workspace_name=DEFAULT_WORKSPACE_NAME)
    if state == dataroot.STATE_AMBIGUOUS:
        raise ApiError(503, "sys.dataRootAmbiguous",
                       "本机存在多个像真实工作区的数据根——请先确认要操作的目标根，"
                       "再重试（`jobws doctor` 或 GET /api/system/paths 查看候选清单）。")


def workspace_dir(request: Request, ws: str = Query(default=None, description="工作区相对路径")) -> str:
    """解析工作区绝对路径（缺省 personal/）；**入口先过数据根守卫**（A2）。

    `unavailable` 时 fail-closed（读 / 写 / 破坏性全部拒绝，spec §四）；
    诊断端点请用 `workspace_dir_any_state`。其余语义与解析细节见
    `_resolve_workspace`（含 X-Jobws-Workspace 回显与两道校验）。
    """
    _require_usable_data_root()
    return _resolve_workspace(request, ws)


def workspace_dir_any_state(request: Request, ws: str = Query(default=None, description="工作区相对路径")) -> str:
    """同 `workspace_dir`，但**不查数据根失效**——只给诊断类端点用。

    数据根不可用时，用户恰恰最需要诊断对象本身（`/api/system/paths` 与诊断包）。
    """
    return _resolve_workspace(request, ws)


def _resolve_workspace(request: Request, ws: str) -> str:
    """工作区解析本体（两个入口共用；行为与拆分前逐字一致）。

    接受相对路径（供多工作区切换），拒绝绝对路径——后端只服务应用根或数据根
    之下的目录。解析结果写入 `request.state.workspace`，由 main.py 的中间件以
    X-Jobws-Workspace 回显（issue #22）：让「实际服务的是哪个工作区」从不可见
    变为调用方一读就能察觉——静默返回别的工作区数据比报错危险得多。细节分别在
    `reject_bad_param_name`（参数名，在 request_guard.py）与
    `_resolve_relative_workspace`（相对名）。
    """
    reject_bad_param_name(request)

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
    且保证以 workspace 为前缀（或就是 workspace 自身——无片段调用）。

    2026-09-25 收口批：归属判定统一到 `jobws_core.containment`（realpath +
    commonpath）——此前是 normpath 字符串前缀，不解析链接；工作区内的
    junction 指向外部时可读穿（`ro_files.inside` 与 MCP 侧早已 realpath，
    这里是最后一个漂移点）。**返回值仍是 normpath 拼接**（不是 realpath）：
    判定与返回分离，调用方看到的路径形态不变。
    """
    for p in parts:
        # 盘符相对（`C:foo`）：`isabs()` 为 False、join 时却把根重置到盘根——此前
        # 漏检（落到归属判定，分类成 path.escape；CWD 恰在工作区内时还会放行）。
        # 用平台原生判定：posix 上 `C:foo` 是普通文件名，跨平台严格版在 MCP 侧
        # （`containment.escape_reason`），两处差异有意保留（test_dedup_parity 钉住）。
        if (os.path.isabs(p) or ".." in p.split(os.sep) + p.split("/")
                or os.path.splitdrive(p)[0]):
            raise ApiError(400, "path.illegalSegment", "非法路径片段: %r" % p, part=p)

    full = os.path.normpath(os.path.join(workspace, *parts))
    if not containment.is_within_or_equal(full, workspace):
        raise ApiError(400, "path.escape", "路径越出工作区")

    return full
