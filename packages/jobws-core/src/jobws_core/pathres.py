# -*- coding: utf-8 -*-
"""路径解析：区分「只读资源」与「可写数据」，并在打包后正确定位。

2026-09-19 批 6 第二批：本模块从 `web/backend/pathres.py` 搬进领域包。
搬家与「改成注入式」是同一笔——正是这次搬迁暴露了 `__file__` 推断法的致命处：
住 `web/backend/` 时向上三级是仓库根，住 site-packages 时同一个表达式指向
安装目录的上层，数据根**静默**漂移（论证见 `tests/test_domain_root.py`）。
所以现在由入口显式 `set_app_root()`，没注入就报错。旧路径留转发 shim。

PyInstaller 打包后 __file__ 指向临时解压目录（sys._MEIPASS），
原有的「三层向上推仓库根」会失效，故用 sys.frozen 分支处理。

两类路径必须分开：
- 只读资源（tools/、dist/）：随应用分发，放应用目录即可，不可写也无妨。
- 可写数据（personal/ 工作区）：用户数据，必须落在**可写**目录。
  若应用装在 Program Files 等不可写位置，放 exe 旁会 PermissionError，
  甚至被 UAC 虚拟化重定向到 VirtualStore 导致数据「消失」。
  故可写数据走优先级链：环境变量 → 便携模式 → 系统用户目录。
"""

from __future__ import annotations

import os
import sys

from . import containment  # 越界判定唯一原语（escape_reason / is_within）

# 可写数据目录的环境变量覆盖（最高优先级）
ENV_DATA_DIR = "JOBWS_DATA_DIR"
# 默认工作区名的环境变量（legacy 保留判据要按它找旧数据；与 deps.py 同值）
ENV_WORKSPACE = "JOBWS_WORKSPACE"
# 便携模式标记文件：存在则允许用 exe 同级目录存数据
PORTABLE_MARKER = "portable.txt"
# B3 起的新装默认数据根名：`<user_data_dir>/data`（spec 决策 6——四端可共同
# 计算，不依赖应用根；MCP 没有应用根概念，这是契约成立的前提）
DEFAULT_DATA_DIR_NAME = "data"

# 旧默认位置「已有真实工作区」的信号文件（与 dataroot_probe.SIGNALS 同源：
# 模板工作区建 config/profile.md；老工作区至少会有追踪表）。
_LEGACY_SIGNALS = (("config", "profile.md"), ("05_投递追踪", "tracker.csv"))
_DEFAULT_WORKSPACE = "personal"


def is_frozen():
    """是否运行在 PyInstaller 打包环境。"""
    return getattr(sys, "frozen", False)


# 应用根（只读资源）——由**入口显式注入**。
#
# 为什么不再从 `__file__` 推断（2026-09-19 批 6 第二批）：本模块要搬进可安装包
# （`packages/jobws-core`），那时「向上三层」会落进 site-packages 的上层目录，
# 数据根随之漂移，而故障**全程静默**（完整论证见 `tests/test_domain_root.py`）。
# 所以非打包形态下没注入就**直接报错**：宁可起不来，也不要写错地方。
_APP_ROOT = None


def set_app_root(path):
    """显式注入应用根。入口进程在启动时调用（它们各自知道自己在哪里）。

    传 `None` 可清除注入值——**仅供测试**重置全局状态用。
    """
    global _APP_ROOT
    _APP_ROOT = None if path is None else os.path.abspath(path)


def set_app_root_if_unset(path):
    """已注入则不动——兼容层可以安全地「确保有值」。

    用途：旧路径 shim（`tools/tracker/__init__.py`）会在导入真身**之前**调用它。
    真身的 `_core` 在模块顶层就 `resolve_root()`，而 `tools/report.py` 这类
    「直跑只给迁移提示」的脚本会先 import 那个 shim——没有这一手，
    它们会在拿到提示之前就 ImportError。
    """
    global _APP_ROOT
    if _APP_ROOT is None:
        _APP_ROOT = os.path.abspath(path)


def resolve_root(root=None):
    """应用根目录。

    - 显式传参 / 已注入：用那个值；
    - 打包（onedir）：exe 同级目录（资源与数据都以此为基）；
    - 非打包且未注入：**报错**（不再从 `__file__` 推断，见 `_APP_ROOT` 处注释）。
    """
    if root is not None:
        return os.path.abspath(root)
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    if _APP_ROOT is None:
        raise RuntimeError(
            "应用根未注入：非打包形态下 pathres 不再从 __file__ 推断根目录"
            "（本模块要搬进可安装包，推断值会静默变成 site-packages 的上层）。"
            "入口进程请先调用 pathres.set_app_root(<仓库根>)——见 web/backend/main.py、"
            "tools/jobws.py、mcp/jobws_mcp/paths.py 三处注入点。"
        )
    return _APP_ROOT


def resolve_dist_dir(root=None):
    """前端静态产物目录（只读）。

    解包：web/frontend/dist；打包：dist（exe 同级）。
    """
    if root is None:
        root = resolve_root()
    if is_frozen():
        return os.path.join(root, "dist")
    return os.path.join(root, "web", "frontend", "dist")


def resolve_tools_dir(root=None):
    """tools/ 脚本目录（只读，后端 import 用）。

    解包：仓库根 tools/；打包：优先 exe 同级 tools/，回退 sys._MEIPASS。
    """
    if root is None:
        root = resolve_root()
    if is_frozen():
        sibling = os.path.join(root, "tools")
        if os.path.isdir(sibling):
            return sibling
        # 回退：打包进 exe 内的 tools（sys._MEIPASS）
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, "tools")
        return sibling
    return os.path.join(root, "tools")


def user_data_dir():
    """系统用户数据目录（跨平台，标准库实现，不引入 platformdirs）。

    Windows: %APPDATA%/<app>；macOS: ~/Library/Application Support/<app>；
    Linux:   ~/.config/<app>（XDG_DATA_HOME 优先时也可，但 config 更通用）。
    """
    app = "job-workbench"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, app)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), app)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, app)


def _writable(path):
    """目录是否可写；不存在则**走到最近的已存在祖先**测它（B3 起）。

    为什么不只是看一层父目录：B3 的新默认是 `<user_data_dir>/data`——全新
    机器上 `<user_data_dir>` 本身也还不存在，只看一层父目录会得出「不可写」，
    三态判定于是把「正常首启」误报成不可写。问题其实是「`makedirs(parents=)`
    能不能成」，所以要走到最近的真实祖先。
    """
    try:
        probe = os.path.abspath(path)
        while not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                return False                     # 走到盘根都没有 → 放弃
            probe = parent
        return os.access(probe, os.W_OK)
    except OSError:
        return False


def default_data_root():
    """B3 起的**新装默认数据根**：`<user_data_dir>/data`（spec 决策 6）。

    四端可共同计算——MCP 没有应用根概念，这是数据根契约成立的前提。
    目录**不在这里创建**（解析器绝不写盘）：首启由初始化流程建工作区。
    """
    return os.path.join(user_data_dir(), DEFAULT_DATA_DIR_NAME)


def _legacy_workspace_present(root):
    """旧默认位置是否已有**真实工作区**（B3 的 legacy 保留判据，O(1) stat）。

    只 stat `<root>/<工作区名>/` 下的两个信号文件（工作区名取
    `JOBWS_WORKSPACE`，缺省 personal——旧默认位置的数据就在那里，这是历史
    事实）。与 `dataroot_probe.has_workspace` 的宽口径（扫全部一级子目录、
    服务歧义检测）刻意分工：本判据落在**解析热路径**上，每条命令都要走，
    必须保持纯 stat、不做目录扫描。
    """
    name = (os.environ.get(ENV_WORKSPACE) or "").strip() or _DEFAULT_WORKSPACE
    for parts in _LEGACY_SIGNALS:
        if os.path.isfile(os.path.join(root, name, *parts)):
            return True
    return False


def resolve_default_root():
    """无应用根形态（MCP-only）的默认解析：legacy 保留 → 新默认（B3）。"""
    legacy = user_data_dir()
    if _legacy_workspace_present(legacy):
        return legacy, "legacy_userdata"
    return default_data_root(), "userdata"


class WorkspaceOutOfRange(ValueError):
    """`JOBWS_WORKSPACE` 越出数据根（默认工作区解析的唯一失败形态）。

    与 Web `deps.resolve_default_workspace` 的 400 `ws.outOfRange`、MCP 的
    containment 兜底同口径：坏配置 fail-closed，不退化成"用别的目录继续"。
    """


def default_workspace(root=None):
    """默认工作区绝对路径 = `<数据根>/<工作区名>`（B4 整改 A：与 API/MCP 同源）。

    2026-10-05 前 CLI 的默认工作区锚在**应用根**（`<repo>/personal`），B3 把
    数据根默认切到 `<user_data_dir>/data` 后，新装场景 CLI 与 API/MCP 默认分叉
    ——本函数把 CLI 侧收口到同一条链（数据根 + `JOBWS_WORKSPACE`，缺省
    `personal`），与 `deps.resolve_default_workspace` / MCP 的
    `resolve_default_workspace` 口径一致。

    **越界必须拒绝**（2026-10-09 审计 1.1-3）：CLI 此前是唯一静默口——环境变量
    写成 `..` 段 / 绝对路径 / 盘符相对会让默认工作区落到数据根之外；Web 已
    fail-closed、MCP 由 `within_any` 兜住。现在同一道闸（`escape_reason` +
    `is_within`，含经链接读穿），违规抛 `WorkspaceOutOfRange`（入口层映射为
    退出码 2）。

    **调用时求值**（不缓存）：解析链依赖环境变量，模块级常量会在测试与长驻
    进程里静默过期。
    """
    data_root, _mode = resolve_workspace_root(root)
    name = (os.environ.get(ENV_WORKSPACE) or "").strip() or _DEFAULT_WORKSPACE
    reason = containment.escape_reason(name)
    full = os.path.normpath(os.path.join(data_root, name))
    if reason or not containment.is_within(full, data_root):
        raise WorkspaceOutOfRange(
            "默认工作区越出数据根（%s）：JOBWS_WORKSPACE=%s —— 请改成数据根内的"
            "相对目录名（如 personal），或清掉该配置使用默认值。"
            % (reason or "经链接指向界外", name))
    return full


def resolve_workspace_root(root=None):
    """可写的数据根目录——即 personal/ 的**父目录**（不是 personal 本身）。

    优先级（B3 起，spec 决策 6 + §九目标矩阵）：
      1. 环境变量 JOBWS_DATA_DIR（显式指定，最高优先级）
      2. 便携标记 `<root>/portable.txt`：**显式才便携**——frozen 与非 frozen
         同一判据。「非打包可写即便携」的旧规则就此降级：可写只是能力，
         不是选择（NSIS 安装版落在可写目录会被误判的老缺陷，根因就是拿
         「能力」当「意愿」）。
      3. **legacy 保留**：旧默认位置已有真实工作区 → 原样继续，**不搬迁、
         不静默换根**（搬家是 `jobws data-root migrate` 的事，必须经确认）：
           - 应用根下有 → (root, "legacy_portable")；
           - 系统用户目录下有 → (user_data_dir(), "legacy_userdata")。
         空骨架（personal/ 在但没有信号文件）**不算**——那是未初始化，
         该走新默认由首启引导建工作区。
      4. 新默认：(user_data_dir()/data, "userdata")——源码形态「无配置＝
         仓库根」的那一格就此改掉（spec §九注明这是 B3 要改的最后一格）。

    返回 (路径, 模式说明) 便于排障与 UI 展示。
    """
    if root is None:
        root = resolve_root()

    # 1. 环境变量显式指定
    env_dir = os.environ.get(ENV_DATA_DIR, "").strip()
    if env_dir:
        return os.path.abspath(env_dir), "env"

    # 2. 便携标记（显式选择，两种形态同一判据）
    if os.path.isfile(os.path.join(root, PORTABLE_MARKER)):
        return root, "portable"

    # 3. legacy 保留：旧默认位置已有真实工作区的，原样继续
    if _legacy_workspace_present(root):
        return root, "legacy_portable"
    return resolve_default_root()


def snapshot_root():
    """快照备份根目录——**必须落在工作区之外**。

    与源数据同盘同目录的备份等于没备份：会被误删、被 git、被同步工具一并波及。
    Obsidian 的成熟做法就是把快照放 vault 之外的系统目录。

    Windows: %APPDATA%\\job-workbench\\snapshots
    macOS:   ~/Library/Application Support/job-workbench/snapshots
    Linux:   ~/.local/share/job-workbench/snapshots

    注意：有意**不**跟随 resolve_workspace_root 的便携模式。便携模式的语义是
    "数据放 exe 旁"，若快照也放 exe 旁，就退化成了同盘同目录。
    """
    return os.path.join(user_data_dir(), "snapshots")
