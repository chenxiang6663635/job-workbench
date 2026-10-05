# -*- coding: utf-8 -*-
"""数据根**只读探测**：持久化选择的读取 + 候选根的「像不像工作区」扫描。

为什么单独一个模块（spec §四/§五）：
- 三态计算需要两类探测——读 `<user_data_dir>/state/data-root.json` 与对已知
  候选根做「有没有工作区」的浅扫描；本模块**只读**，写入（选择 / 根标记）在
  `dataroot_state`（A3 起），两侧共享 `selection_file()` 与原始文档读取；
- 探测纪律是性能铁律：只做 `stat` / **单层** `listdir`、绝不哈希、绝不递归；
  目录条目数超过 `SCAN_LIMIT` 直接视为「有工作区」并提前退出（超过这个量级
  大概率是真实数据目录，不值得再逐条 stat）；
- `dataroot.py` 因此保持「解析 + 状态判定」的编排层，文件行数留在规模闸门内。

**盲区**（spec §三决策 3）：MCP-only 形态拿不到源码形态的应用根——候选集由
调用方显式给 `include_app_root`，探测层不猜。state / source / form 词表见
`dataroot.py` 与 spec §五。
"""

from __future__ import annotations

import io
import json
import os

from . import pathres

# 「像真实工作区」的现成信号（spec §三决策 3 的检测口径）：候选根下某个一级
# 子目录出现这些文件之一即认定。两个信号覆盖两种初始化形态——模板工作区建
# `config/profile.md`；老工作区至少会有追踪表。
SIGNALS = (("config", "profile.md"), ("05_投递追踪", "tracker.csv"))

# 单层扫描的条目上限：超过就提前判「有工作区」——避免在大目录上做几百次 stat。
SCAN_LIMIT = 200

# 持久化选择的相对位置（相对 user_data_dir()）；名字与 schema 见 spec 决策 2。
SELECTION_REL = os.path.join("state", "data-root.json")

# 迁移相位词表（spec §五 的 `migration_state`）：跨端契约值，不许漂。
# `idle` = 没有在途事务（迁移成功也回到它——spec 决策 5 的 "done" 就是 idle）；
# `failed` = 事务失败且源目录未受影响，等下一次续跑或干净放弃。
# 词表放在**读侧**（本模块）：它只是「选择文件里的一个字段怎么读」，
# 写入侧（`dataroot_migrate`）引用同一份常量，不另抄一套字面量。
MIGRATION_IDLE = "idle"
MIGRATION_FAILED = "failed"
MIGRATION_PHASES = ("idle", "planned", "copying", "verifying", "switching", MIGRATION_FAILED)


def selection_file():
    """持久化选择的绝对路径（A2 只读；写入属于 A3）。"""
    return os.path.join(pathres.user_data_dir(), SELECTION_REL)


def read_selection_document():
    """选择文件的**原始文档**（宽读：只要 JSON dict 就返回；缺失 / 坏 → None）。

    与 `read_persisted_selection`（校验后给诊断用的三键对象）分开：A3 的写侧
    （保留既有 `root_id`）与 `describe()` 的 `root_id` 回落读原始字段，坏文件
    在这里同样按「未设置」处理。
    """
    try:
        with io.open(selection_file(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_persisted_selection(env=os.environ):
    """只读探测持久化选择——返回 `{path, readable, shadowed_by}` 或 None（未设置）。

    - 文件不存在 → None（「无持久化选择」）；
    - 文件存在但坏（非 JSON / 结构不对 / `data_root` 不是绝对路径）→ 按
      **「未设置」处理**（读不出的选择不该把用户锁死），但仍返回对象并让
      `readable=false`——诊断要如实报「这里有个坏了的选择」；
    - `shadowed_by`：env（`JOBWS_DATA_DIR` 非空）遮蔽一个**可读**的选择时报
      "env"（决策 1：遮蔽必须可见；读不出来的选择谈不上被遮蔽）。
    """
    if not os.path.isfile(selection_file()):
        return None
    data = read_selection_document()
    root = data.get("data_root") if data else None
    sel = {"path": None, "readable": False, "shadowed_by": None}
    if isinstance(root, str) and os.path.isabs(root.strip()):
        sel["path"] = os.path.normpath(root.strip())
        sel["readable"] = True
    if sel["readable"] and (env.get(pathres.ENV_DATA_DIR) or "").strip():
        sel["shadowed_by"] = "env"
    return sel


def read_migration_phase():
    """只读：选择文件里的 `migration_state`（B1 起是真值，A3 时是占位 `idle`）。

    缺失 / 坏文件 / 值不在词表内 → `idle`（读不出的相位按「没有在途事务」处理，
    与「坏选择文件按未设置处理」同一条纪律）；`state/` 之外不碰任何东西。
    """
    data = read_selection_document() or {}
    phase = data.get("migration_state")
    return phase if phase in MIGRATION_PHASES else MIGRATION_IDLE


def candidate_roots(app_root=None, env=os.environ, include_app_root=True):
    """已知候选根（spec §三决策 3 的固定集合）：env → user_data_dir → 应用根（可选）。

    去重按 normcase + normpath——同一处被两种来源指向时只算一个候选，
    否则会「自己和自己歧义」。应用根只在源码形态参与（`include_app_root`）；
    MCP-only 看不到它（盲区，见模块 docstring）。
    """
    roots = []
    env_dir = (env.get(pathres.ENV_DATA_DIR) or "").strip()
    if env_dir:
        roots.append(os.path.abspath(env_dir))  # 与 pathres 同口径：abspath 绑 cwd
    roots.append(pathres.user_data_dir())
    if include_app_root and app_root:
        roots.append(os.path.abspath(app_root))
    out, seen = [], set()
    for root in roots:
        root = os.path.normpath(root)
        key = os.path.normcase(root)
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def has_workspace(root):
    """候选根下是否有「像真实工作区」的一级子目录——**有界**单层扫描。

    只 stat 一级子目录下的两个信号文件；条目数超过 `SCAN_LIMIT` 直接返回 True
    并提前退出（见模块 docstring 的性能铁律）。
    """
    try:
        entries = os.scandir(root)
    except OSError:
        return False
    count = 0
    with entries:
        for entry in entries:
            count += 1
            if count > SCAN_LIMIT:
                return True
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            for parts in SIGNALS:
                if os.path.isfile(os.path.join(entry.path, *parts)):
                    return True
    return False


def survey(app_root=None, env=os.environ, include_app_root=True):
    """候选清单：`[{path, has_workspace}]`（顺序即优先级：env → user_data → app）。"""
    return [{"path": root, "has_workspace": has_workspace(root)}
            for root in candidate_roots(app_root, env, include_app_root)]
