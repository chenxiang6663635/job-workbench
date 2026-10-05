# -*- coding: utf-8 -*-
"""数据根解析的**唯一入口**：把「传不传应用根」这件事显式化为 `form`（A1）。

为什么要有这个模块（spec: `docs/specs/2026-10-04-single-canonical-data-root.md`）：

现状是两条互不知情的解析链——Web / CLI 给 `pathres` 传应用根（非打包即便携，
数据根＝仓库根），打包形态与 MCP 不给（落系统用户目录）。同一台机器上四端可能
解析到不同数据根，且已真实发生过一次静默分叉（spec §一/§1.2）。本模块把
「四端各自决定传不传应用根」收成显式的四种 `form`；A2 起的三态守卫与四端
可见性、A3 的持久化选择都从这里长。

为什么不发明第二套解析：带应用根的三种形态**整体委托**
`pathres.resolve_workspace_root(app_root)`——`pathres` 仍是唯一实现，本模块
不复制它的判定分支；只有 `FORM_MCP_ONLY`（MCP / 任意 venv，没有应用根可传）
按现状规则复刻（`JOBWS_DATA_DIR` → `pathres.user_data_dir()`，来源见
`mcp/jobws_mcp/paths.py` 的 `data_root()`）。

**A1 的行为零变更边界**（改动必须与之一致）：
- env 是相对值仍会被 `os.path.abspath()` 绑到 cwd（A2 才收紧为「只接受绝对路径」）；
- env 空串（含纯空白）仍视为未设置；
- 打包形态是否便携仍由 `portable.txt` 与可写性判定，默认值一律不变。
锁见 `tests/test_dataroot.py`；四端取值矩阵见 spec §九。

`form` 取值对应 spec §九 契约矩阵的「形态」列：源码 checkout / 便携标记 /
打包 NSIS / MCP-only 安装。
"""

from __future__ import annotations

import os
from typing import NamedTuple

from . import pathres  # 唯一实现：可写数据根的优先级链（env → 便携 → 用户目录）

FORM_SOURCE = "source_form"   # 源码 checkout：非 frozen → 可写即便携（仓库根）
FORM_PORTABLE = "portable"    # 显式便携标记（frozen + portable.txt）
FORM_PACKAGED = "packaged"    # 打包形态：无 portable.txt 即 userdata
FORM_MCP_ONLY = "mcp_only"    # 无应用根的独立安装（MCP / 任意 venv）

# 带应用根、整体委托 pathres 的形态；MCP-only 是唯一例外。
_APP_ROOT_FORMS = (FORM_SOURCE, FORM_PORTABLE, FORM_PACKAGED)

# pathres 的「解析原因」→ 诊断对象的 `source` 词表（spec §五）。
# 便携与用户目录两种来源都加 `legacy_` 前缀：它们在 A3 引入持久化选择后
# 都属于「旧默认」——没有前缀，将来 `persisted` 接进来就分不清新旧（spec §九）。
_SOURCE_BY_MODE = {
    "env": "env",
    "portable": "legacy_portable",
    "userdata": "legacy_userdata",
}


class DataRootResolution(NamedTuple):
    """一次数据根解析的结果（A1 的形状契约）。

    - `path`：数据根（`personal/` 的父目录）；
    - `form`：本次解析的调用形态（`source_form | portable | packaged | mcp_only`）
      ——与诊断对象的 `form` 同一含义，**刻意不叫 `mode`**（理由见 `describe()`）；
    - `source`：解析来源（`env | persisted | legacy_portable | legacy_userdata`）
      ——pathres 的「解析原因」按 spec §五 词表映射；A1 只可能产出
      `env` / `legacy_portable` / `legacy_userdata`（`persisted` 留给 A3）。
    """

    path: str
    form: str
    source: str


def resolve_data_root(form, app_root=None, env=os.environ):
    """解析数据根——CLI / Web / 桌面端 / MCP 共用的**唯一入口**。

    `form` 见模块 docstring；`app_root` 是应用根（源码＝仓库根、打包＝exe 同级），
    `FORM_MCP_ONLY` 没有它、传了也忽略。

    `env` 的 A1 边界：只有 `FORM_MCP_ONLY` 从传入映射读 `JOBWS_DATA_DIR`
    （默认 `os.environ`；纯函数测试可直接传字典）；其余三种形态**整体委托**
    pathres，由它读取进程环境——A1 不复制它的判定分支，A2 收紧绝对路径时再
    统一两边的 env 口径（见本模块 docstring 的「零变更边界」）。
    """
    if form == FORM_MCP_ONLY:
        return _resolve_mcp_only(form, env)
    if form in _APP_ROOT_FORMS:
        path, mode = pathres.resolve_workspace_root(app_root)
        return DataRootResolution(path, form, _SOURCE_BY_MODE[mode])
    raise ValueError(
        "未知 form：%r（可选：%s）"
        % (form, " / ".join((FORM_SOURCE, FORM_PORTABLE, FORM_PACKAGED, FORM_MCP_ONLY))))


def _resolve_mcp_only(form, env):
    """`FORM_MCP_ONLY`：**逐字复刻** `mcp/jobws_mcp/paths.py` 的既有规则。

    为什么不能委托 pathres 的便携分支：MCP 包可能装在任意 venv，没有「应用根」；
    给它传 site-packages 就等于把用户数据写到 Python 安装目录旁边（pathres 的
    注释正在警告这件事）。所以只认两条：`JOBWS_DATA_DIR`（非空、strip 后）→
    `pathres.user_data_dir()`（与 pathres 第三级同源）。空串/纯空白视为未设置。
    """
    env_dir = (env.get(pathres.ENV_DATA_DIR) or "").strip()
    if env_dir:
        return DataRootResolution(os.path.abspath(env_dir), form, "env")
    return DataRootResolution(pathres.user_data_dir(), form, "legacy_userdata")


def _writable(path):
    """数据根**自身**（不存在则其父目录）能否写入——诊断对象 `writable` 的判据。

    **与 pathres 的便携判据不是同一件事、不要混用**：`resolve_workspace_root`
    判定「便携」拷问的是 `<root>/personal` 能否写入（将来要写工作区的地方），
    是**默认位置选择**的输入；这里回答的是另一个问题——「这个数据根本身能不能
    落数据」，供诊断与将来换根用。二者可以不同（如根可写、`personal/` 尚未创建），
    混用会在换根 / 迁移场景里得出错答案。

    判据来源：`packages/jobws-core/src/jobws_core/pathres.py` 的 `_writable`
    （存在则测自身写权限；不存在则测其父目录，因为可能需先创建）。本模块
    **实现等价判断**而不是引用私有函数：A1 明确不为此改 pathres 的可见性；
    两边语义由 `tests/test_dataroot.py` 对账。
    """
    try:
        if os.path.isdir(path):
            return os.access(path, os.W_OK)
        parent = os.path.dirname(path) or "."
        return os.access(parent, os.W_OK)
    except OSError:
        return False


def describe(form, app_root=None, env=os.environ):
    """诊断对象——字段名逐字取 spec §五 的 `ResolvedDataRootDiagnostic`。

    **词表**（spec §五）：
    - `source`：解析来源 `env | persisted | legacy_portable | legacy_userdata`
      ——A1 只可能产出 `env` / `legacy_portable` / `legacy_userdata`；`persisted`
      随 A3 的持久化选择接入。
    - `form`：本次解析的**调用形态** `source_form | portable | packaged | mcp_only`
      ——**刻意不叫 `mode`**：API 响应里已有 `mode` 字段表示 `portable | user` 的
      解析结果（`/api/system/paths`），同一个响应里出现两个 "mode" 会制造同名两义。
    - `writable`：数据根自身（不存在则其父目录）能否写入；与 pathres 的便携判据
      （判定 `<root>/personal`）不是同一件事，不要混用（见 `_writable`）。

    呈现分工（spec §五）：CLI / API / MCP / 设置页**只做序列化与呈现**，都从这里
    取同一份对象，不各自再算一份。A1 只填当下能填的：`path` / `source` / `form` /
    `state`（固定 "ok"）/ `writable`——A1 没有三态与失效检测（那是 A2，先不装
    守卫，也不猜状态）；其余字段依赖 A2（三态与候选检测）、A3（持久化选择）与
    B 批（迁移状态机），统一占位（None / [] / "idle"），**不猜值**。
    """
    res = resolve_data_root(form, app_root, env)
    return {
        "path": res.path,
        "source": res.source,
        "form": res.form,
        "state": "ok",
        "writable": _writable(res.path),
        "root_id": None,
        "schema_version": None,
        "persisted_selection": None,
        "legacy_candidates": [],
        "migration_state": "idle",
    }
