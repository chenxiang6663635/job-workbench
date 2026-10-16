# -*- coding: utf-8 -*-
"""回滚判据（P1-B 方案①）：四个信号的**纯函数**直测。

为什么单独一个文件：`tests/test_dataroot_migrate.py` 锁事务的端到端现场（中断 /
完成 / 崩溃窗口 / 重复 / 生效后新增记录）；本文件把四个来源（事务记录 / 相位 /
选择文档 / 目标根标记 + 切换证据）显式喂进 `dataroot_rollback.signals`，
逐信号钉住三件事：

1. 谁**单独**就能触发拒绝——`completed` / `selection_on_target` /
   `switch_landed_unfinished`；
2. `identity_on_target` 只作**佐证**：唯一能让它单独成立的在途现场是
   `switching`（数据已 rename 上位、根标记已钉、指针还没翻），那里拒绝会误伤
   「中断后回滚」这条通道——它替用户把话说明白，但不作拒绝依据；
3. 在途与「已回滚」永远不在拒绝集里——判据不是「迁移过就一律拒绝」。

判别位置与理由见 `jobws_core.dataroot_rollback` 的模块说明。
"""

import os

import pytest

from jobws_core import dataroot_rollback as guard

SOURCE = os.path.join(os.path.sep, "old", "root")
TARGET = os.path.join(os.path.sep, "new", "root")
ROOT_ID = "abcdef0123456789"
OTHER_ID = "0123456789abcdef"


def _journal(**over):
    """事务记录的最小形态（字段与 `dataroot_migrate._journal_doc` 同形状）。"""
    doc = {"format": 1, "source_root": SOURCE, "target_root": TARGET,
           "workspace": "personal",
           "staging": os.path.join(TARGET, ".jobws-migration", "personal"),
           "root_id": ROOT_ID, "completed_at": None, "rolled_back_at": None}
    doc.update(over)
    return doc


def _found(journal, **over):
    """跑一遍判据；缺省现场 = 在途（copying）、指针还在旧根、身份没落目标。"""
    kwargs = {"phase": "copying", "doc": {"data_root": SOURCE, "root_id": ROOT_ID},
              "marker": None, "landed": False}
    kwargs.update(over)
    return guard.signals(journal, **kwargs)


def _hits(journal, **over):
    return {item["name"]: item["hit"] for item in _found(journal, **over)}


def test_signal_vocabulary_is_fixed_and_ordered():
    """四个信号的词表与顺序：跨端复用同一份判据，改词表就是改契约。"""
    assert [item["name"] for item in _found(_journal())] == [
        "completed", "selection_on_target", "switch_landed_unfinished",
        "identity_on_target"]


def test_completed_transaction_is_refused_on_its_own():
    """完成位一写就再也回不去——哪怕此后有人手工把指针改回了旧根。"""
    found = _found(_journal(completed_at="2026-10-16T10:00:00"),
                   doc={"data_root": SOURCE, "root_id": ROOT_ID})
    assert guard.refused_by(found) == ["completed"]


def test_selection_pointing_at_the_target_is_refused_whatever_the_phase_says():
    """选择指着目标根 = 目标根就是活动数据根：相位说什么都不该再翻指针。"""
    found = _found(_journal(), phase="failed",
                   doc={"data_root": TARGET, "root_id": ROOT_ID})
    assert guard.refused_by(found) == ["selection_on_target"]


def test_the_switch_crash_window_is_covered_without_the_completion_mark():
    """切换生效写已发生、完成记录未落盘（崩溃窗口）：选择已指向目标 + 相位 idle。

    这条是**独立**用例：不能只检查 `completed_at`——那个窗口里它是 None。
    """
    found = _found(_journal(), phase="idle",
                   doc={"data_root": TARGET, "root_id": ROOT_ID},
                   marker={"root_id": ROOT_ID}, landed=True)
    assert guard.refused_by(found) == ["selection_on_target",
                                       "switch_landed_unfinished"]


def test_phase_idle_without_the_switch_evidence_is_not_a_refusal():
    """相位 idle 但切换没有上位（例如用户手工改过选择、事务并未切过）：不拒绝。"""
    assert guard.refused_by(_found(_journal(), phase="idle", landed=False)) == []


def test_phase_idle_after_a_rollback_is_not_a_refusal():
    """已回滚（`rolled_back_at` 已写）的收尾：重复回滚仍是幂等的收尾动作。"""
    journal = _journal(rolled_back_at="2026-10-16T11:00:00")
    assert guard.refused_by(_found(journal, phase="idle", landed=True)) == []


def test_identity_on_target_only_corroborates_while_the_switch_is_in_flight():
    """硬杀在 switch 里（rename 与根标记已就位、生效写还没写）：拒绝就是误伤。

    这是 `identity_on_target` 唯一能单独成立的现场——所以它只作佐证。
    """
    journal = _journal()
    found = _found(journal, phase="switching",
                   doc={"data_root": SOURCE, "root_id": ROOT_ID},
                   marker={"root_id": ROOT_ID}, landed=True)
    assert _hits(journal, phase="switching", doc={"data_root": SOURCE, "root_id": ROOT_ID},
                 marker={"root_id": ROOT_ID}, landed=True)["identity_on_target"] is True
    assert guard.refused_by(found) == [], "在途现场（含 switching）不许被误拒"


def test_identity_signal_needs_the_same_root_id_in_both_places():
    """身份佐证要求「选择文件」与「目标根标记」都记着事务的 root_id。"""
    journal = _journal()
    assert _hits(journal, marker={"root_id": OTHER_ID})["identity_on_target"] is False
    assert _hits(journal, doc={"data_root": TARGET, "root_id": OTHER_ID},
                 marker={"root_id": ROOT_ID})["identity_on_target"] is False
    assert _hits(journal, doc={"data_root": TARGET, "root_id": ROOT_ID},
                 marker={"root_id": ROOT_ID})["identity_on_target"] is True


@pytest.mark.parametrize("phase", ["planned", "copying", "verifying", "switching", "failed"])
def test_in_flight_phases_are_never_refused(phase):
    """在途的每一个相位：回滚照旧可用（判据不是「一律拒绝」）。"""
    assert guard.refused_by(_found(_journal(), phase=phase)) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
