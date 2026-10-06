# -*- coding: utf-8 -*-
"""数据根**迁移事务**（B1）：`plan → copy → verify → switch → done/failed`。

为什么单独一个模块：`dataroot.py`（解析与编排）、`dataroot_probe`（只读探测）、
`dataroot_state`（选择文件与根标记）各自已有明确职责，迁移是**另一件事**——
它是唯一会碰用户文件的动作，必须能逐相测试（phase 可注入失败、可硬杀、可续跑）。

三条纪律（spec 决策 5，逐条都在测试里有对应用例）：

1. **copy-first / switch-second / delete-never**：旧目录在 `done` 之前**只读不删**，
   第一版**完全不自动删**。数据先拷进目标根下的暂存目录
   （`<目标根>/.jobws-migration/<工作区>`），校验过了才 `os.replace` 上位——
   同卷 rename 只是加速，次序一步都不能换。
2. **switch 是唯一生效点且最后写**：相位值写在 `state/data-root.json` 的
   `migration_state`（spec §五 词表），但 `data_root` 只在最后那一次写里变成目标。
   之前的每一个相位，选择文件都仍指向**源根**——崩在任何一步，机器都还在读源。
3. **幂等**：选择已指向目标、或目标已带同一 `root_id` → 直接跳过（跨版本重复升级安全）。

两件持久化物（都在 `state/`，都不含路径以外的机器相关字段）：

- `state/data-root.json`：`migration_state` = 当前相位（`dataroot_migrate` 是**唯一**
  写口，见 `_write_selection`）；`root_id` 是数据身份，搬家时**带过去**（`root_id`
  不变正是「同一份数据搬了家」的唯一判据）。
- `state/data-root-migration.json`：事务记录（清单 + 哈希 + 起止时间 + 失败原因）。
  相位**不在**这里——同一个事实只留一处真值；记录只在开始 / 失败 / 完成时改写。
  清单里只有**引用串**，绝不含明文凭据（本模块也从不解密任何东西）。

续跑判定（`resume`）：相位是 `switching`，或「暂存没了但目标工作区在」（硬杀在
rename 之后）→ 只补最后一步；其余（`planned` / `copying` / `verifying` / `failed`）
→ 重跑 copy（**按清单 + 哈希差量**，已落位的不重拷）→ verify → switch。
失败语义：任何阶段失败都不影响源目录可用，相位写 `failed` 并在事务记录里留原因。

**回滚**（`rollback`）= 把持久化选择指回旧根（源未删、目标原样留着）：本批**不做**
自动删除与自动回搬——观察期里两份历史根都在磁盘上是设计接受的状态（spec §七 风险 6），
清理由人裁决。
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import uuid

from . import dataroot_manifest as manifest_mod
from . import dataroot_probe as probe
from . import dataroot_semantics as semantics
from . import dataroot_state as state
from . import pathres

logger = logging.getLogger(__name__)

# 事务记录的相对位置（相对 user_data_dir()）；与选择文件同处控制面。
JOURNAL_REL = os.path.join("state", "data-root-migration.json")
JOURNAL_FORMAT = 1

# 步骤 → 相位（spec §九 词表的取值）。
PHASE_FOR_STEP = {"copy": "copying", "verify": "verifying", "switch": "switching"}
ALL_STEPS = ("copy", "verify", "switch")

# 失败原因里最多列几条校验问题（逐条列全反而看不清主因）。
MAX_REASON_PARTS = 3


# --- 事务记录 -------------------------------------------------------------------

def journal_file():
    """事务记录的绝对路径（与选择文件同在 `<user_data_dir>/state/`）。"""
    return os.path.join(pathres.user_data_dir(), *JOURNAL_REL.split(os.sep))


def read_journal():
    """读事务记录；缺失 / 坏 / 不是对象 → None（「没有在途事务」由相位一并判断）。"""
    try:
        with io.open(journal_file(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_journal(journal):
    journal["updated_at"] = state.now_iso()
    state.atomic_write_json(journal_file(), journal)
    return journal


def current_phase():
    """当前相位（读 `state/data-root.json` 的 `migration_state`）。"""
    return probe.read_migration_phase()


# --- 唯一写口 -------------------------------------------------------------------

def _write_selection(root, phase, root_id=None):
    """写选择文件：`data_root=root` + `migration_state=phase`。**本模块唯一的写口**。

    为什么不复用 `dataroot_state.write_persisted_selection`：那个函数会给写侧指向的
    根补根标记——事务期指向的是**源根**，那等于往源目录里写文件，直接违反纪律 1。
    身份的搬运由 switch 显式做（`ensure_root_marker(目标, root_id)` 后再走本写口）。
    """
    doc = probe.read_selection_document() or {}
    data = {
        "format": state.SELECTION_FORMAT,
        "data_root": os.path.normpath(str(root)),
        "root_id": root_id or doc.get("root_id") or uuid.uuid4().hex,
        "selected_at": state.now_iso(),
        "selected_by": "migration",
        "migration_state": phase,
        "schema_version": doc.get("schema_version"),
    }
    state.atomic_write_json(probe.selection_file(), data)
    return data


def _set_phase(journal, phase):
    """相位写：**始终指向源根**（生效写是 switch 里最后那一次，见 `_switch_phase`）。"""
    return _write_selection(journal["source_root"], phase, journal["root_id"])


# --- plan -----------------------------------------------------------------------

def _default_workspace():
    """缺省工作区名——从 `dataroot` 取（**不在这里抄字面量**；局部 import 免循环）。"""
    from .dataroot import DEFAULT_WORKSPACE_NAME
    return DEFAULT_WORKSPACE_NAME


def _root_id_for(source_root):
    """这次迁移要带的身份：源根标记 → 源根的选择文件 → 新生成（记进事务记录即稳定）。"""
    marker = state.read_root_marker(source_root)
    if marker:
        return marker["root_id"]
    doc = probe.read_selection_document() or {}
    if state.same_root(doc.get("data_root"), source_root) and doc.get("root_id"):
        return doc["root_id"]
    return uuid.uuid4().hex


def _already_current(target):
    """幂等判据（spec 决策 5）：选择已指向目标，或目标已带**同一个** `root_id`。"""
    if not target:
        return False
    doc = probe.read_selection_document() or {}
    if state.same_root(doc.get("data_root"), target):
        return True
    marker = state.read_root_marker(target)
    return bool(marker and doc.get("root_id")
                and marker.get("root_id") == doc.get("root_id"))


def plan(target, source, workspace=None):
    """计划一次迁移：**纯读**（清单 + 预检），一个字节都不写。

    返回 `{ok, reasons, already_current, source_root, target_root, workspace,
    source_workspace, target_workspace, staging, root_id, manifest, free_bytes}`；
    `reasons` 是 `[{kind: usage|blocked, message}]`（CLI 据此映射退出码）。
    幂等命中时 `ok=True`、`already_current=True`、`manifest=None`（不必再扫源目录）。
    """
    workspace = workspace or _default_workspace()
    source_root = os.path.normpath(str(source))
    raw_target = str(target or "").strip()
    if os.path.isabs(raw_target):
        raw_target = os.path.normpath(raw_target)
    doc = {
        "ok": False, "reasons": [], "already_current": False,
        "source_root": source_root, "target_root": raw_target, "workspace": workspace,
        "source_workspace": os.path.join(source_root, workspace),
        "target_workspace": os.path.join(raw_target, workspace) if raw_target else "",
        "staging": manifest_mod.staging_workspace(raw_target, workspace) if raw_target else "",
        "root_id": _root_id_for(source_root), "manifest": None, "free_bytes": None,
    }
    if _already_current(raw_target):
        doc["ok"] = True
        doc["already_current"] = True
        return doc
    doc["manifest"] = manifest_mod.build_manifest(doc["source_workspace"])
    doc["reasons"] = manifest_mod.preflight(source_root, raw_target, workspace, doc["manifest"])
    doc["ok"] = not doc["reasons"]
    doc["free_bytes"] = manifest_mod.free_bytes(raw_target) if raw_target else None
    return doc


def reasons_text(plan_doc):
    """把预检理由拼成一行人读文案（CLI 与失败原因共用一份）。"""
    return "；".join(item["message"] for item in plan_doc.get("reasons") or []) or "（无）"


def plan_fingerprint(plan_doc):
    """计划的指纹——预览 → 确认协议的「确认凭据」（spec 决策 5 的形状复用）。

    apply 侧重算并比对：清单（相对路径 / 大小 / sha256）、跳过项、预检理由任一
    变化都会换指纹——源数据在预览与确认之间被人动过，就绝不按旧计划执行。
    只取**稳定字段**：不含 `free_bytes`（探测值，两次读取天然可以不同）、不含
    `root_id`（无身份的源根每次计划都会新铸 uuid——身份由事务记录与根标记承载，
    不是计划内容的一部分）。
    """
    manifest = plan_doc.get("manifest") or {}
    stable = {
        "source_root": plan_doc.get("source_root"),
        "target_root": plan_doc.get("target_root"),
        "workspace": plan_doc.get("workspace"),
        "entries": manifest.get("entries"),
        "skipped": manifest.get("skipped"),
        "total_bytes": manifest.get("total_bytes"),
        "reasons": plan_doc.get("reasons"),
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply(plan_doc):
    """执行计划：写事务记录 → copy → verify → switch（生效写）。"""
    if not plan_doc.get("ok"):
        raise ValueError("计划未通过预检，拒绝执行：%s" % reasons_text(plan_doc))
    if plan_doc.get("already_current"):
        raise ValueError("当前数据根已指向该目标（root_id 相同），无需迁移")
    journal = _journal_doc(plan_doc)
    _write_journal(journal)
    # 事务开相：spec §五 词表里的 planned（此后 copy/verify/switch 各归其位）。
    _set_phase(journal, "planned")
    return _run(journal, _steps_for(journal, "planned"))


def _journal_doc(plan_doc):
    manifest = plan_doc["manifest"]
    stamp = state.now_iso()
    return {
        "format": JOURNAL_FORMAT,
        "source_root": plan_doc["source_root"],
        "target_root": plan_doc["target_root"],
        "workspace": plan_doc["workspace"],
        "staging": plan_doc["staging"],
        "root_id": plan_doc["root_id"],
        "entries": manifest["entries"],
        "skipped": manifest["skipped"],
        "total_bytes": manifest["total_bytes"],
        "started_at": stamp, "updated_at": stamp,
        "completed_at": None, "rolled_back_at": None, "reason": None,
    }


# --- 执行 -----------------------------------------------------------------------

def _run(journal, steps):
    """按 steps 跑事务；`OSError` 折算成 `failed`（硬杀不清算：Resume 靠它）。"""
    summary = {"status": "done", "steps": list(steps), "copy": None, "verify": None,
               "reason": None, "source_root": journal["source_root"],
               "target_root": journal["target_root"], "root_id": journal["root_id"]}
    try:
        for step in steps:
            _set_phase(journal, PHASE_FOR_STEP[step])
            if step == "copy":
                summary["copy"] = _copy_phase(journal)
            elif step == "verify":
                summary["verify"] = _verify_phase(journal)
                if summary["verify"]["problems"]:
                    return _fail(journal, summary, "校验未通过：%s"
                                 % "；".join(summary["verify"]["problems"][:MAX_REASON_PARTS]))
            else:
                _switch_phase(journal)
    except OSError as exc:
        return _fail(journal, summary, "IO 失败（%s）：%s" % (type(exc).__name__, exc))
    journal["completed_at"] = state.now_iso()
    _write_journal(journal)
    return summary


def _fail(journal, summary, reason):
    """失败收尾：相位 `failed` + 原因进事务记录；**源目录不会被碰**。"""
    journal["reason"] = reason
    try:
        _set_phase(journal, probe.MIGRATION_FAILED)
        _write_journal(journal)
    except OSError as exc:
        # 写不出状态不等于没失败：至少让原因跟着本次调用的返回值出去（不静默）。
        journal["reason"] = "%s（另外：写失败相位也失败：%s）" % (reason, exc)
    summary["status"] = "failed"
    summary["reason"] = journal["reason"]
    return summary


def _copy_file(src, dst):
    """单文件复制（独立函数：失败注入与「拷贝期间源被改」的测试都挂在这里）。"""
    shutil.copy2(src, dst)


def _same_bytes(path, item):
    """目标侧那个文件与清单条目逐字节相同？（续跑的差量判据）"""
    if not os.path.isfile(path) or os.path.getsize(path) != item["size"]:
        return False
    return manifest_mod.sha256_file(path) == item["sha256"]


def _rel_path(root, rel):
    """`root` 下的绝对路径（`rel` 一律是清单里那种正斜杠形状）。"""
    return os.path.join(str(root), *rel.split("/"))


def _ws_path(root, workspace, rel):
    """工作区根（`<root>/<工作区>`）下的绝对路径。"""
    return _rel_path(os.path.join(str(root), str(workspace)), rel)


def _copy_phase(journal):
    """复制/暂存：清单里的每个文件落到暂存目录；已落位且哈希一致的跳过（续跑）。"""
    stats = {"copied": 0, "reused": 0, "bytes": 0}
    for item in journal["entries"]:
        src = _ws_path(journal["source_root"], journal["workspace"], item["rel"])
        dst = _rel_path(journal["staging"], item["rel"])
        if _same_bytes(dst, item):
            stats["reused"] += 1
            continue
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        _copy_file(src, dst)
        stats["copied"] += 1
        stats["bytes"] += item["size"]
    return stats


def _leftover_problems(journal):
    """暂存目录里有清单外的文件 → 事务记录与磁盘不一致（重跑或人工动过）。"""
    known = {item["rel"] for item in journal["entries"]}
    walked = manifest_mod.walk_workspace(journal["staging"], with_hash=False)
    extra = [item["rel"] for item in walked["entries"] if item["rel"] not in known]
    if not extra:
        return []
    return ["暂存目录里有清单外的文件（事务记录与磁盘不一致）：%s"
            % " / ".join(extra[:MAX_REASON_PARTS])]


def _verify_phase(journal):
    """校验：暂存 vs 清单（大小 + 哈希）、源是否漂移、工作区语义、凭据引用告警。"""
    problems = []
    checked = 0
    for item in journal["entries"]:
        src = os.path.join(journal["source_root"], journal["workspace"],
                           *item["rel"].split("/"))
        dst = _rel_path(journal["staging"], item["rel"])
        if not os.path.isfile(dst):
            problems.append("暂存里缺文件：%s" % item["rel"])
        elif os.path.getsize(dst) != item["size"]:
            problems.append("暂存文件大小不符：%s" % item["rel"])
        elif manifest_mod.sha256_file(dst) != item["sha256"]:
            problems.append("暂存文件哈希不符：%s" % item["rel"])
        elif not os.path.isfile(src):
            problems.append("源文件在迁移期间被删除：%s" % item["rel"])
        elif manifest_mod.sha256_file(src) != item["sha256"]:
            problems.append("源文件在迁移期间发生了变化：%s（请让源工作区在迁移期间保持"
                            "只读，再重新运行）" % item["rel"])
        else:
            checked += 1
    problems.extend(_leftover_problems(journal))
    source_ws = os.path.join(journal["source_root"], journal["workspace"])
    problems.extend(semantics.compare(semantics.snapshot(source_ws),
                                      semantics.snapshot(journal["staging"]))["problems"])
    return {"problems": problems, "checked": checked,
            "warnings": semantics.credential_warnings(journal["staging"])}


def _switch_phase(journal):
    """切换：数据先上位（同卷 rename），再写**唯一生效点**。

    次序不能反：选择一旦指向目标，那边就必须**已经在**（反过来崩在中间会留下一个
    指向空目录的根）。rename 是原子的，生效写是普通原子写——崩在两者之间由
    `resume` 的「只补最后一步」兜住。
    """
    target_root = journal["target_root"]
    target_ws = os.path.join(target_root, journal["workspace"])
    if os.path.isdir(journal["staging"]):
        if os.path.exists(target_ws):
            raise OSError("目标工作区已存在，拒绝覆盖：%s" % target_ws)
        os.makedirs(target_root, exist_ok=True)
        os.replace(journal["staging"], target_ws)
        _drop_empty_staging(os.path.dirname(journal["staging"]))
    elif not os.path.isdir(target_ws):
        raise OSError("暂存与目标工作区都不在（事务记录与磁盘不一致）：%s"
                      % journal["staging"])
    # 身份先钉进目标根，再写选择：这样 `root_id` 跨搬家保持不变（决策 2）。
    state.ensure_root_marker(target_root, root_id=journal["root_id"])
    _write_selection(target_root, probe.MIGRATION_IDLE, journal["root_id"])


def _drop_empty_staging(directory):
    """暂存目录空了就收掉；收不掉只记日志（它不影响事务成败，但**不静默**）。"""
    try:
        os.rmdir(directory)
    except OSError as exc:
        logger.warning("迁移暂存目录未能清理（可手工删）：%s（%s）", directory, exc)


# --- resume / rollback ----------------------------------------------------------

def _switch_pending(journal):
    """数据已上位、只差生效写？（硬杀在 rename 之后、写选择之前的现场）"""
    return (not os.path.isdir(journal["staging"])
            and os.path.isdir(os.path.join(journal["target_root"], journal["workspace"])))


def _steps_for(journal, phase):
    """从当前相位接着跑哪几步（`switching` 只补最后一步；其余从头补差量）。"""
    if phase == "switching" or _switch_pending(journal):
        return ["switch"]
    return list(ALL_STEPS)


def _staged_counts(journal):
    staged = 0
    for item in journal["entries"]:
        if _same_bytes(_rel_path(journal["staging"], item["rel"]), item):
            staged += 1
    return staged, len(journal["entries"]) - staged


def resume(apply=False):
    """续跑在途事务；`apply=False` 是演练（只报告相位与差量，不写任何东西）。"""
    journal = read_journal()
    phase = current_phase()
    if journal is None:
        if phase != probe.MIGRATION_IDLE:
            # 相位说有事、事务记录却读不出：报出来（含处置建议），不假装「没有事务」。
            return {"status": "unknown", "phase": phase,
                    "reason": "选择文件记着相位 %s，但事务记录（%s）读不出或不存在；"
                              "请人工确认后清理，或用 `data-root set/clear` 重选"
                              % (phase, JOURNAL_REL)}
        return {"status": "nothing"}
    if journal.get("completed_at") and phase == probe.MIGRATION_IDLE:
        return {"status": "nothing"}
    steps = _steps_for(journal, phase)
    if not apply:
        staged, remaining = _staged_counts(journal)
        return {"status": "dry-run", "phase": phase, "steps": steps, "staged": staged,
                "remaining": remaining, "source_root": journal["source_root"],
                "target_root": journal["target_root"]}
    return _run(journal, steps)


def rollback(apply=False):
    """回滚：把持久化选择指回旧根。**不删、不回搬**（源未删，目标原样留着）。"""
    journal = read_journal()
    if journal is None:
        return {"status": "nothing"}
    source_root = journal["source_root"]
    if not apply:
        return {"status": "dry-run", "to": source_root,
                "from": (probe.read_selection_document() or {}).get("data_root"),
                "target_root": journal["target_root"]}
    already = state.same_root(
        (probe.read_selection_document() or {}).get("data_root"), source_root)
    _write_selection(source_root, probe.MIGRATION_IDLE, journal["root_id"])
    journal["rolled_back_at"] = state.now_iso()
    _write_journal(journal)
    return {"status": "noop" if already else "rolled-back", "source_root": source_root,
            "target_root": journal["target_root"],
            "target_kept": os.path.isdir(os.path.join(journal["target_root"],
                                                      journal["workspace"])),
            "staging_kept": os.path.isdir(journal["staging"])}
