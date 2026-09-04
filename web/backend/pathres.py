# -*- coding: utf-8 -*-
"""路径解析：区分「只读资源」与「可写数据」，并在打包后正确定位。

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

# 可写数据目录的环境变量覆盖（最高优先级）
ENV_DATA_DIR = "JOBWS_DATA_DIR"
# 便携模式标记文件：存在则允许用 exe 同级目录存数据
PORTABLE_MARKER = "portable.txt"


def is_frozen():
    """是否运行在 PyInstaller 打包环境。"""
    return getattr(sys, "frozen", False)


def resolve_root():
    """应用根目录。

    解包（源码运行）：web/backend/ 向上三层 = 仓库根。
    打包（onedir）：exe 同级目录（资源与数据都以此为基）。
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def _user_data_dir():
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
    """目录是否可写（不存在则检查其父目录，因为可能需先创建）。"""
    try:
        if os.path.isdir(path):
            return os.access(path, os.W_OK)
        parent = os.path.dirname(path) or "."
        return os.access(parent, os.W_OK)
    except OSError:
        return False


def resolve_workspace_root(root=None):
    """可写的数据根目录——即 personal/ 的**父目录**（不是 personal 本身）。

    优先级：
      1. 环境变量 JOBWS_DATA_DIR（显式指定，最高优先级）
      2. 应用根可写：直接用应用根（解包=仓库根，打包=exe 同级）
         —— personal/ 位于其下，即「数据放 exe 旁」的便携模式
      3. 应用根不可写（如装在 Program Files）：回退系统用户数据目录

    返回 (路径, 模式说明) 便于排障与 UI 展示。
    """
    if root is None:
        root = resolve_root()

    # 1. 环境变量显式指定
    env_dir = os.environ.get(ENV_DATA_DIR, "").strip()
    if env_dir:
        return os.path.abspath(env_dir), "env"

    # 2. 应用根可写 → 便携模式（personal/ 在应用根下）
    if _writable(os.path.join(root, "personal")):
        return root, "portable"

    # 3. 应用根不可写（Program Files 等）→ 系统用户目录
    return _user_data_dir(), "userdata"


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
    return os.path.join(_user_data_dir(), "snapshots")
