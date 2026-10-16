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
# 2026-10-16 #307 收口批：工作区内读取（归属 + 有界 + 换行归一）收口到
# `workspace_read`——本模块的 `*_in_workspace` 三函数改为薄转发，实现只有一份
# （领域层；CLI / Web / MCP 同源），修口径不必再三个端各改一遍。`workspace_read`
# 只依赖 containment（零副作用、不碰 ROOT），故与上面的 import 同段无顺序问题。
from jobws_core import (  # noqa: E402
    containment,
    dataroot,
    pathres,
    workspace_read,
)

# 给 pathres 一个「应用根」＝**数据根**，且**必须在此刻**——领域层（`tracker/_core`、
# `jd_score`）在**导入期**就求值 `ROOT`，晚一步下面的 import 直接 RuntimeError。
#
# 为什么给的是数据根而不是「应用目录」：本包没有那个概念（`template/` 与 `dist/`
# 都不随包发），数据根是它真正需要的那个（工作区在它下面）。领域层里靠 ROOT 找的
# 东西（如 `jd_score` 的 `template/profiles`）在独立安装下不存在，各自有回退
# ——`resolve_profile` 会看工作区自己的 `config/`。
#
# B3 起与 `data_root()` **同一条解析链**（env > persisted > legacy 保留/新默认）：
# 此前这里只认 env 与 user_data_dir，用户设了持久化选择后领域层 ROOT 与数据根
# 会分叉——那正是 spec 要消灭的「同一包内两个事实源」。
pathres.set_app_root(dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).path)

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

    2026-10-04 A1：规则**逐字**搬进 `jobws_core.dataroot`（`FORM_MCP_ONLY`），
    本函数只做转发——返回值与搬前逐字相同（对账见 `tests/test_dataroot.py`）；
    `allowed_roots()` / `resolve_workspace()` 与导入期的应用根注入都不受影响。
    """
    return dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).path


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


# 越界原因（`containment.escape_reason` 的返回值）→ 工具层文案：三类各自的说明
# 不同，措辞是既有对外形态（`mcp/tests` 钉住「盘符」等关键词）。
_ESCAPE_MESSAGES = {
    "是绝对路径": "%s 必须是工作区内的相对路径（不能是绝对路径）：%s",
    "含 .. 段": "%s 不能包含 .. 段：%s",
    "含盘符": "%s 不能包含盘符（`C:foo` 这类盘符相对路径会让 join 重置到盘根）：%s",
}


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
    # 三类越界写法（绝对 / `..` 段 / 盘符相对）的判据来自 `containment.escape_reason`
    # ——唯一实现（2026-10-09 收编批）；文案映射留在这边，措辞是既有的对外形态。
    reason = containment.escape_reason(raw)
    if reason and reason != "为空":
        template = _ESCAPE_MESSAGES.get(reason)
        if template:
            return None, None, template % (label, raw)
        return None, None, "%s 含越界写法（%s）：%s" % (label, reason, raw)
    normalized = raw.replace("\\", "/")
    segments = [seg for seg in normalized.split("/") if seg not in ("", ".")]
    if not segments:
        return None, None, "%s 不能为空" % label
    ws_real = containment.real(workspace)
    real = containment.real(os.path.join(ws_real, *segments))
    if not containment.is_within_or_equal(real, ws_real):
        return None, None, "%s 越出工作区：%s" % (label, raw)
    return real, "/".join(segments), None


# --- 工作区内读取：归属 + 有界（2026-10-16，外部审计 P1-A / P2-A）-------------
#
# 2026-10-16 #307 收口批：实现已下沉领域层 `jobws_core.workspace_read`（tracker 读 /
# jd_score 预检 / append_history 判据都走它；CLI 与 Web 同源）。本模块保留函数名
# 与签名**逐字不动**——这里是 MCP 的受控通道（job_files、tools_readonly、resources
# 都经这四个名字读工作区），转发后它们零改动。
#
# 判据与口径不再在这里维护：realpath 归属（含「等于工作区」）、越界 fail-closed、
# 字节上限（数的是字节、超限拒绝）、换行归一——全部只有领域层一份。


def is_in_workspace(workspace, *parts):
    """`workspace/parts...` 的归属校验（realpath 展开）；**不要求路径存在**。

    判据 = `containment.is_within_or_equal`（原语义含「等于工作区」）。链接目标
    仍在工作区内时**不做限制**：用户把工作区分片放在同步盘再链进来是合法用法
    （`resolve_workspace` 同样只对「读穿到外面」动手）。契约：部件须是单段
    相对名（拼绝对路径 / `..` 段会重置根，判据 fail-closed 兜住）。
    """
    return workspace_read.is_in_workspace(workspace, *parts)


def exists_in_workspace(workspace, *parts):
    """工作区内是否存在该文件：**归属校验通过之后**才算存在。

    不能直接用 `os.path.isfile`：它**跟随链接**——数据目录是 junction 时，
    「有 tracker.csv」 / 「有解析卡」会正判定出一个工作区外文件，而这个布尔
    本身就是泄漏（宿主据此能探测工作区外有没有某个文件）。越界一律按「不存在」
    给（False）；指向**工作区内**的链接照旧为 True（目标在区内，不是泄漏面）。
    """
    return workspace_read.exists_in_workspace(workspace, *parts)


def read_in_workspace(workspace, *parts, max_bytes=None):
    """读工作区内的文本：realpath 归属校验（+可选字节上限）；越界 / 读不到返回 None。

    fail-closed：越界、不是普通文件、打不开、读不了**一律 None**，不抛错。链接
    跳转照旧：归属判的是**链接目标**，目标在工作区内就照读（换行归一并进原语）。

    `max_bytes` 是**二进制**有界读：文本模式的 `read(n)` 数的是**字符**，纯中文时
    n 个字符 ≈ 3n 字节。超限**拒绝（None）而不是截断**——截断后的正文会被解析成
    「半真半假」的结果，比明确的「读不到」更坏。**无上限只给体量可控的小文件**。
    """
    return workspace_read.read_in_workspace(workspace, *parts, max_bytes=max_bytes)


# --- tracker 读取的协议层转译（#307）---------------------------------------------
#
# 领域层 `tracker.read_rows` / `read_history` 现在先过归属判据，越界抛
# `WorkspaceBoundaryError`（显式拒绝，不返空列表）。MCP 的既有范式是「返回结构、
# 不抛栈」，故转译放在**这几个读点上**：


def read_tracker_rows(workspace):
    """主表读取 + 转译：返回 (行, None)；越界返回 (None, 可读错误)。

    为什么不放 `tools_readonly`：那是登记过的水位文件（只许变小）；本模块是
    MCP 的受控通道，「工作区解析 + 归属 + 有界读」都住这里，转译跟着判据走。
    惰性 import `tracker`：它导入期求值 `ROOT`，必须排在本模块注入应用根之后。
    """
    from jobws_core import tracker  # noqa: E402  （导入期求值 ROOT，晚于上方注入）
    try:
        return tracker.read_rows(workspace), None
    except workspace_read.WorkspaceBoundaryError as exc:
        return None, str(exc)


def read_tracker_history(workspace):
    """时间线读取 + 转译：同上（`05_投递追踪` / `history.csv` 经链接指向工作区外时）。"""
    from jobws_core import tracker  # noqa: E402
    try:
        return tracker.read_history(workspace), None
    except workspace_read.WorkspaceBoundaryError as exc:
        return None, str(exc)


def workspace_profile(workspace):
    """工作区是否已初始化：判定标准是含 `config/profile.md`（与后端
    `routers/workspace.py:44` 同一口径）。缺它时工具返回空集而不是报错——
    没数据不等于出错。"""
    return os.path.isfile(os.path.join(workspace, "config", "profile.md"))
