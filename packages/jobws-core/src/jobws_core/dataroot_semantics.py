# -*- coding: utf-8 -*-
"""工作区**语义**快照与比对（B1 的 verify 相里「不只是字节」的那一半）。

为什么单独一个模块：`dataroot_manifest` 管清单与哈希（字节层），本模块管「这份拷贝
还是一个**能用的**工作区吗」——spec 决策 5 点名的四项：`tracker.csv` 主键集合与行数、
`config/profile.md`、`config/directions/*.md` 数量、`config/imap.json` /
`provider.json` 的凭据引用。字节相等看不出这些退化（清单漏了整棵子树、拷贝目标被
手工动过、凭据引用没搬过来），所以两者都要有。

两条刻意的边界：

1. **比对方向是「源有的，目标都要有」**：目标多出文件不算问题（目标可能本来就有
   别的东西），源有的丢了才算。
2. **凭据引用取不到 ≠ 迁移失败**：引用是 uuid（与路径无关），「引用在手却取不到」
   是迁移**之前**就存在的健康状态——#203 对它的处置是界面提示「重新保存」，不是
   拒绝一切操作。因此它是 `credential_warnings()`（进诊断的告警面），而**不是**
   `compare()` 的 problems：拿一个既存问题阻断迁移，只会把用户锁在原地。
   另外，机器上有没有系统存储决定这条判得动判不动：明文形态（源码 / CLI 回退）
   下 `get` 恒为 None，那不是「引用丢了」，所以直接不报。

只读、纯逻辑：本模块不写任何文件，也不解密任何东西（只读配置里的**引用串**）。
"""

from __future__ import annotations

import csv
import io
import json
import os

from . import credentials

# 语义项的路径（工作区内相对路径；顺序即各自在 messages 里出现的顺序）。
TRACKER_REL = ("05_投递追踪", "tracker.csv")
PROFILE_REL = ("config", "profile.md")
DIRECTIONS_REL = ("config", "directions")
# (相对路径, 引用字段名)。**不含** legacy 明文字段：快照会落进 state/ 的 journal。
CREDENTIAL_FILES = (
    (("config", "imap.json"), "auth_ref"),
    (("config", "provider.json"), "api_key_ref"),
)
ID_COLUMN = "id"


def read_tracker(workspace):
    """追踪表读数：`{rows, ids}`；文件不在 / 读不出 → None。

    `ids` 是**非空**主键（按文件顺序）——空 id 行不参与集合比对，但照样计入行数：
    行数对不上是硬错，主键集合对不上同样是。旧工作区没有 id 列时 `ids` 为空列表
    （只比行数），不抛——语义项不该把一个老工作区挡在门外。
    """
    path = os.path.join(str(workspace), *TRACKER_REL)
    if not os.path.isfile(path):
        return None
    try:
        # utf-8-sig：与 tracker 的读侧同口径（BOM 由它吃掉）。
        with io.open(path, "r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    ids = [(row.get(ID_COLUMN) or "").strip() for row in rows]
    return {"rows": len(rows), "ids": [item for item in ids if item]}


def credential_refs(workspace):
    """两个凭据配置里的**引用串**：`[{file, key, ref}]`（只取引用，不取明文）。"""
    found = []
    for rel, key in CREDENTIAL_FILES:
        data = _read_json(os.path.join(str(workspace), *rel))
        ref = (data or {}).get(key)
        if isinstance(ref, str) and ref.strip():
            found.append({"file": "/".join(rel), "key": key, "ref": ref.strip()})
    return found


def snapshot(workspace):
    """工作区语义快照（比对与展示共用同一份形状）。"""
    workspace = os.path.normpath(str(workspace))
    return {
        "profile": os.path.isfile(os.path.join(workspace, *PROFILE_REL)),
        "directions": _directions_count(workspace),
        "tracker": read_tracker(workspace),
        "credentials": credential_refs(workspace),
    }


def compare(source, target):
    """源快照 → 目标快照的语义比对；返回 `{problems, warnings}`。"""
    problems = []
    if source["profile"] and not target["profile"]:
        problems.append("目标工作区缺 config/profile.md（个人档案没搬过去）")
    if source["directions"] != target["directions"]:
        problems.append("方向文件数量不一致（config/directions/*.md：源 %s / 目标 %s）"
                        % (_count_text(source["directions"]),
                           _count_text(target["directions"])))
    problems.extend(_tracker_problems(source["tracker"], target["tracker"]))
    problems.extend(_credential_problems(source["credentials"], target["credentials"]))
    return {"problems": problems, "warnings": []}


def credential_warnings(workspace, store=None):
    """凭据引用在当前形态下解析不了的告警（不阻断迁移；见模块 docstring）。"""
    refs = credential_refs(workspace)
    if not refs:
        return []
    if store is None:
        store = credentials.select_store()
    if getattr(store, "kind", "") == credentials.KIND_PLAINTEXT:
        return []
    warnings = []
    for item in refs:
        try:
            secret = store.get(item["ref"])
        except Exception as exc:  # 存储实现承诺不抛；这里只兜住，不让校验炸掉（且不吞）
            warnings.append("凭据引用校验失败（%s：%s）：%s"
                            % (item["file"], item["ref"], exc))
            continue
        if not secret:
            warnings.append("凭据引用取不到（%s：%s）——迁移后仍需到设置页重新保存"
                            % (item["file"], item["ref"]))
    return warnings


def _directions_count(workspace):
    """`config/directions/*.md` 的数量；目录不在 → None（与「空目录 = 0」区分开）。"""
    directory = os.path.join(workspace, *DIRECTIONS_REL)
    if not os.path.isdir(directory):
        return None
    try:
        return len([name for name in os.listdir(directory) if name.lower().endswith(".md")])
    except OSError:
        return None


def _count_text(count):
    return "无" if count is None else str(count)


def _tracker_problems(source, target):
    if source is None and target is None:
        return []
    if (source is None) != (target is None):
        return ["追踪表存在性不一致（源 %s / 目标 %s）——拷贝不是源的忠实副本"
                % ("有" if source else "无", "有" if target else "无")]
    if source["rows"] != target["rows"]:
        return ["追踪表行数不一致（源 %d / 目标 %d）" % (source["rows"], target["rows"])]
    if source["ids"] != target["ids"]:
        missing = [item for item in source["ids"] if item not in target["ids"]][:3]
        return ["追踪表主键集合不一致（目标缺 %s%s）"
                % (" / ".join(missing),
                   " 等" if len(missing) < len(source["ids"]) else "")]
    return []


def _credential_problems(source, target):
    """源里的凭据引用必须在目标里逐条都在（丢了 = 界面声称「还没配置」）。"""
    have = {(item["file"], item["key"], item["ref"]) for item in target}
    lost = [item for item in source if (item["file"], item["key"], item["ref"]) not in have]
    if not lost:
        return []
    return ["凭据引用没搬过去（%s）——界面会从「重新保存凭据」退化成「还没配置」"
            % " / ".join("%s:%s" % (item["file"], item["ref"]) for item in lost[:3])]


def _read_json(path):
    """宽读：不是合法 JSON / 读不出 → None（语义项按「没有这条」处理）。"""
    try:
        with io.open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
