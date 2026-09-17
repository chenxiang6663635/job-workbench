# -*- coding: utf-8 -*-
"""tracker 包门面契约（2026-09-16 重构批）。

包化目标：「对外零改动」——41 个引用点全部是 `import tracker` + 属性访问。
本测试把契约钉死：

1. **名字完整性**：从全仓引用面反推的名字全部可达（拆分漏导即红）；
2. **可变全局语义**：`set_workspace()` 后 `tracker.WORKSPACE` 必须跟随——
   门面用 PEP 562 转发而非值快照，这条断言就是"转发正确性"的守卫
   （若有人把门面改成 `from ._core import WORKSPACE`，这里会红）;
3. **子模块直达**：`tracker._core` 等可达（monkeypatch 的入口）。

维护约定：拆分增删对外名字时同步更新 CONTRACT_NAMES——它就是契约的成文版
（清单生成法：全仓 grep `tracker.<名>` 的引用面 ∩ 包内真实顶层名）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import tracker  # noqa: E402

CONTRACT_NAMES = [
    "CONTACT_FIELDS", "ConflictError", "FIELDS", "HEALTH_LEVELS",
    "INTERVIEW_FIELDS", "INTERVIEW_FORMS", "INTERVIEW_RESULTS",
    "INTERVIEW_ROUNDS", "MAIL_DIRECTIONS", "MAIL_FIELDS", "MAIL_FILE",
    "MAIL_TAGS", "OFFER_FIELDS", "QUESTION_FIELDS", "QUESTION_FILE",
    "SOURCES", "STAGES", "STALE_DAYS", "TALK_ATTEND", "TALK_FIELDS",
    "TALK_FILE", "TALK_FORMS", "TERMINAL_STAGES", "TMP_PREFIX", "UPDATABLE",
    "WORKSPACE", "_atomic_write_csv", "_lock_path", "_validate_mail_fields",
    "append_history", "apply_approved_add", "apply_approved_import",
    "apply_approved_mail", "apply_approved_talk", "apply_approved_update",
    "build_parser", "check_date", "check_direction", "check_reason_required",
    "check_terminal_transition", "commit_import", "dedup_key", "diff_entries",
    "find_contact", "find_duplicate", "find_interview", "find_mail",
    "find_offer", "find_talk", "health_score", "mail_path", "main",
    "next_contact_id", "next_id", "next_interview_id", "next_mail_id",
    "next_offer_id", "next_talk_id", "normalize_message_id",
    "parse_import_csv", "parse_iso_date", "plan_import", "preview_add",
    "preview_add_fields", "preview_import", "preview_mail_fields",
    "preview_talk_fields", "preview_update_fields", "read_contacts",
    "read_history", "read_interviews", "read_mails", "read_offers",
    "read_rows", "read_talks", "resolve_ws", "run_check", "set_workspace",
    "sort_key", "stage_base_date", "stale_days", "write_contacts",
    "write_interviews", "write_mails", "write_offers", "write_rows",
    "write_talks",
]


def test_facade_exposes_every_contract_name():
    """引用面用到的每个名字都必须可达——拆分漏导时这里点名。"""
    missing = [n for n in CONTRACT_NAMES if not hasattr(tracker, n)]
    assert missing == [], "门面缺名（拆分时漏导？）：%s" % missing


def test_workspace_follows_set_workspace():
    """PEP 562 转发的意义：set_workspace 后 tracker.WORKSPACE 必须跟随。"""
    original = tracker.WORKSPACE
    try:
        tracker.set_workspace("/tmp/facade-check")
        followed = tracker.WORKSPACE.replace("\\", "/").endswith("tmp/facade-check")
    finally:
        tracker.set_workspace(original)
    assert followed, "tracker.WORKSPACE 未跟随 set_workspace——门面写成了值快照？"


def test_submodules_directly_reachable():
    """tracker.<子模块> 直接可达（monkeypatch 与调试的入口）。"""
    for name in ("_core", "_schema", "_check", "applications", "interviews",
                 "talks", "mails", "contacts", "offers", "importing",
                 "preview_app", "preview_update", "_cli", "_cli_misc"):
        mod = getattr(tracker, name)
        assert mod.__name__ == "tracker." + name
