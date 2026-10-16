# -*- coding: utf-8 -*-
"""**回滚规则**（P1-B 方案①）：迁移已生效后不再支持无内容核对的指针式回滚。

为什么单独一个模块：`dataroot_migrate` 是事务状态机（相位 / 唯一写口 / 续跑），
而「现在还能不能回滚」是一件**只读判别**——它要同时看四个来源（事务记录、
`state/data-root.json` 的相位、选择文档本身、目标根的根标记），而且是**跨端契约**：
CLI、API 与将来的宿主入口都只经 `dataroot_migrate.rollback()` 走这一条规则，
判别独立成模块才能逐信号测试，也才不会被某一个界面单独绕过。

四个信号（`signals()`；前三个**任一**成立即拒绝）：

1. `completed`：事务记录写了 `completed_at`——迁移完成，目标根生效过；
2. `selection_on_target`：当前持久化选择指向 `target_root`（用 `state.same_root`
   同源比较，不做字符串直比）——选择文件就是「现在读哪个根」的真值；
3. `switch_landed_unfinished`：相位是 `idle`、事务记录既没完成位也没回滚位、而切换的
   物理证据在（暂存已不在、目标工作区在）——这正是**已切换、完成记录未落盘**的崩溃
   窗口指纹（能把相位写成 `idle` 的事务动作只有最后那一步生效写，见 `_switch_phase`）。
   只查 `completed_at` 会漏掉它；
4. `identity_on_target`（**佐证，不单独触发拒绝**）：事务的 `root_id` 同时出现在选择
   文档与目标根标记上——「同一份数据身份已经落在目标根」。它不单独触发，因为唯一能让
   它单独成立的在途现场是 `switching`（数据已 rename 上位、根标记已钉、指针还没翻）：
   那里拒绝会误伤用户明确要保留的「中断后回滚」通道，而那个现场的正确出路是
   `--resume`。它用来把拒绝理由说得更准，并作为结果里 `signals` 的一部分上报。

为什么要守这道闸（危害不是丢数据，是「看起来丢数据」）：delete-never 保证源目录一个
字节都没删，指针式回滚不会真的毁东西；但它会让**目标根上新增的记录看起来凭空消失**
（产品转身去读旧根那份较老的副本）。所以拒绝时要把三件事一次说清：为什么拒、数据都在
哪（目标根没删、旧根仍在）、确实要搬回该怎么走（重新发起一次受控迁移，它有清单与预检、
逐字节校验通过才切换）。

在途不在拒绝集里（判据不是「一律拒绝」）：`planned` / `copying` / `verifying` /
`switching` / `failed` 与「已回滚」都照旧可以回滚——选择本就指着旧根，那是幂等收尾。
"""

from __future__ import annotations

import os

from . import dataroot_probe as probe
from . import dataroot_state as state

# 信号 → 人话（拒绝理由按命中顺序拼；跨端共用这一份文案，别在各端另写一遍）。
SIGNAL_TEXT = {
    "completed": "这次迁移已经完成并生效（事务记录里写了完成位）",
    "selection_on_target": "当前持久化选择已经指向目标根",
    "switch_landed_unfinished": "切换的生效写已经发生（数据已上位目标根），"
                                "只是完成记录还没落盘——典型的崩溃窗口",
    "identity_on_target": "这次事务的 root_id 已经钉在目标根上",
}

# 拒绝时给的两条出路（与「为什么拒」拼成同一句人话，CLI / API / 界面原样呈现）。
HINT_RESUME = "这次事务还差收尾（完成记录没落盘），`jobws data-root migrate --resume --apply` 可以把它做完；"
HINT_CONTROLLED = ("确实要搬回旧位置，请重新发起一次受控迁移："
                   "`jobws data-root migrate <旧位置>`（先出清单与预检、逐字节校验通过才切换）"
                   "——不要绕过安全检查直接改指针。")


def switch_landed(journal):
    """切换的物理证据：暂存已不在而目标工作区在（`_switch_phase` 的 rename 已发生）。

    与 `dataroot_migrate._steps_for` 的续跑判据是**同一个事实**——这两行只有这一处
    实现，别处不要再写第二份（同一个物理事实两处抄，迟早漂移）。
    """
    return (not os.path.isdir(journal["staging"])
            and os.path.isdir(os.path.join(journal["target_root"], journal["workspace"])))


def signals(journal, phase, doc, marker, landed):
    """四个判据信号（**纯函数**：四个来源显式传入，便于逐信号直测与复用）。

    返回 `[{"name", "hit", "refusing"}]`，顺序即信号词表的顺序；`refusing=False`
    的那个只作佐证（见模块说明）。读不出来的东西按「未成立」处理——判据只在能
    **确认**目标根已生效时收紧，不靠猜。
    """
    completed = bool(journal.get("completed_at"))
    on_target = state.same_root(doc.get("data_root"), journal["target_root"])
    unfinished_switch = (phase == probe.MIGRATION_IDLE and not completed
                         and not journal.get("rolled_back_at") and landed)
    identity = (doc.get("root_id") == journal["root_id"]
                and (marker or {}).get("root_id") == journal["root_id"])
    return [
        {"name": "completed", "hit": completed, "refusing": True},
        {"name": "selection_on_target", "hit": on_target, "refusing": True},
        {"name": "switch_landed_unfinished", "hit": unfinished_switch, "refusing": True},
        {"name": "identity_on_target", "hit": identity, "refusing": False},
    ]


def refused_by(found):
    """命中的**拒绝**信号名（`identity_on_target` 不在此列：它只作佐证）。"""
    return [item["name"] for item in found if item["hit"] and item["refusing"]]


def refusal_reason(hits, unfinished):
    """拒绝的人话理由：为什么拒 + 数据都在哪 + 确实要搬回怎么走（三条缺一不可）。"""
    why = "；".join(SIGNAL_TEXT[name] for name in hits)
    return ("拒绝回滚：%s。指针式回滚只改选择文件里那一行、不核对两边内容——"
            "迁移一旦生效，它会让目标根上新增的记录看起来凭空消失。"
            "目标根的数据没有被删除，旧根也仍然在磁盘上（delete-never）。"
            "%s%s" % (why, HINT_RESUME if unfinished else "", HINT_CONTROLLED))


def kept(journal):
    """两份目录的现状（拒绝与回滚都要如实报：「不删、不回搬」是承诺）。"""
    return {"target_kept": os.path.isdir(os.path.join(journal["target_root"],
                                                      journal["workspace"])),
            "staging_kept": os.path.isdir(journal["staging"])}


def inspect(journal, phase=None, doc=None, marker=None, landed=None):
    """读四个只读来源给判据结论（缺省从磁盘取；测试可显式喂）。

    返回 `{"refused_by", "signals", "phase", "doc", "reason"}`：`refused_by` 非空
    即「已生效，禁止指针式回滚」。**纯读**——一个字节都不写，拒绝路径的幂等性
    （第二次仍然拒绝、状态不变）就建立在这上面。
    """
    if phase is None:
        phase = probe.read_migration_phase()
    if doc is None:
        doc = probe.read_selection_document() or {}
    if marker is None:
        marker = state.read_root_marker(journal["target_root"])
    if landed is None:
        landed = switch_landed(journal)
    found = signals(journal, phase, doc, marker, landed)
    hits = refused_by(found)
    return {"refused_by": hits, "signals": found, "phase": phase, "doc": doc,
            "reason": (refusal_reason(hits, unfinished=not journal.get("completed_at"))
                       if hits else None)}


def refusal(journal, verdict):
    """结构化拒绝结果（dry-run 与 apply **同形**：预览不打折、执行不打回）。"""
    return {"status": "refused", "reason": verdict["reason"],
            "source_root": journal["source_root"], "target_root": journal["target_root"],
            "phase": verdict["phase"], "signals": verdict["refused_by"], **kept(journal)}


def rollback(journal, *, apply, write_selection, write_journal):
    """回滚的完整形态（语义见 `dataroot_migrate.rollback` 的 docstring）。

    两个写口由调用方（`dataroot_migrate`）注入：选择文件与事务记录仍然只有那一处写
    实现（`_write_selection` / `_write_journal`），本模块不自己拼 JSON、也不新增第二个写口。
    """
    verdict = inspect(journal)
    if verdict["refused_by"]:
        return refusal(journal, verdict)
    source_root = journal["source_root"]
    from_root = (verdict["doc"] or {}).get("data_root")
    if not apply:
        return {"status": "dry-run", "to": source_root, "from": from_root,
                "target_root": journal["target_root"]}
    already = state.same_root(from_root, source_root)
    write_selection(source_root, probe.MIGRATION_IDLE, journal["root_id"])
    journal["rolled_back_at"] = state.now_iso()
    write_journal(journal)
    return {"status": "noop" if already else "rolled-back", "source_root": source_root,
            "target_root": journal["target_root"], **kept(journal)}
