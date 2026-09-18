# -*- coding: utf-8 -*-
"""tools/tracker 包：求职工作台的投递追踪领域层（7 张表）。

**门面契约（改动前必读）**：本 `__init__` 不导入任何绑定，只用 PEP 562 的
模块级 `__getattr__` 把属性读取**转发**到内部模块——因为 `WORKSPACE` 是
**可变模块全局**（`set_workspace()` / `main()` 会重绑定；测试也按模块全局做
隔离）。若写成 `from ._core import WORKSPACE`（值快照），重绑定的就只是
`_core.WORKSPACE`、外部读到的 `tracker.WORKSPACE` 不跟随——静默行为漂移。
转发则两条语义都与单文件版一致。

**测试提示**：monkeypatch 要打到「调用点所在的子模块」而不是包门面
（如 `tracker._core.WORKSPACE`、`tracker.applications.write_rows`），
只改门面命名空间时真实调用方不受影响（静默失效）。

（2026-09-16 重构批：由单文件 tracker.py 拆出，对外 41 个引用点零改动。）
"""

_HOME = ("_core", "_schema", "_check", "applications", "interviews", "talks",
         "mails", "contacts", "offers", "importing", "preview_app",
         "preview_interview", "preview_update", "_cli", "_cli_interview",
         "_cli_talk", "_cli_mail", "_cli_contact", "_cli_offer", "_cli_misc")


def __getattr__(name):
    import importlib
    if name.startswith("__") and name.endswith("__"):
        # 魔术属性（copy / pickle 的探测）直接失败：不为此实体化全部子模块
        raise AttributeError(name)
    if name in _HOME:                     # tracker._core 这类也直接可达
        return importlib.import_module("." + name, __name__)
    for mod in _HOME:
        m = importlib.import_module("." + mod, __name__)
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(__all__)


__all__ = ['BATCHES', 'CONTACT_FIELDS', 'CONTACT_FILE', 'ConflictError', 'DATE_RE', 'DEFAULT_WORKSPACE', 'DIRECTIONS', 'FAIL_STAGES', 'FIELDS', 'HEALTH_LEVELS', 'HISTORY_FIELDS', 'HISTORY_FILE', 'HISTORY_TRACKED', 'IMPORT_REQUIRED', 'INTERVIEW_FIELDS', 'INTERVIEW_FILE', 'INTERVIEW_FORMS', 'INTERVIEW_RESULTS', 'INTERVIEW_ROUNDS', 'INTERVIEW_UPDATABLE', 'MAIL_DIRECTIONS', 'MAIL_FIELDS', 'MAIL_FILE', 'MAIL_TAGS', 'OFFER_FIELDS', 'OFFER_FILE', 'QUARANTINE_DIR', 'QUESTION_DIFFICULTY', 'QUESTION_FIELDS', 'QUESTION_FILE', 'QUESTION_ORIGINS', 'QUESTION_STATUS', 'ROOT', 'SCHEMA_FILE', 'SOURCES', 'STAGES', 'STALE_DAYS', 'TALK_ATTEND', 'TALK_FIELDS', 'TALK_FILE', 'TALK_FORMS', 'TERMINAL_STAGES', 'TMP_PREFIX', 'TRACKING_SCHEMA_VERSION', 'UPDATABLE', 'URGENT_DAYS', 'WORKSPACE', '_add_app_parsers', '_add_contact_parser', '_add_interview_parser', '_add_mail_parser', '_add_misc_parsers', '_add_offer_parser', '_add_talk_parser', '_atomic_write_csv', '_check_file_rows', '_check_main_table', '_contact_add', '_ensure_schema_sidecar', '_find_by_id', '_history_date', '_inspect_tracking_file', '_interview_add', '_lock_path', '_mail_add', '_mail_targets', '_mail_update', '_offer_add', '_quarantine', '_read_csv_checked', '_talk_add', '_talk_targets', '_tracking_targets', '_validate_add_fields', '_validate_import_row', '_validate_mail_fields', '_validate_talk_fields', '_validate_update', 'append_history', 'apply_approved_add', 'apply_approved_import', 'apply_approved_interview_add', 'apply_approved_interview_update', 'apply_approved_mail', 'apply_approved_talk', 'apply_approved_update', 'available_directions', 'build_parser', 'check_date', 'check_direction', 'check_reason_required', 'check_terminal_transition', 'cmd_add', 'cmd_check', 'cmd_contact', 'cmd_history', 'cmd_import', 'cmd_interview', 'cmd_list', 'cmd_mail', 'cmd_offer', 'cmd_show', 'cmd_talk', 'cmd_update', 'commit_import', 'contact_path', 'csv_path', 'dedup_key', 'diff_entries', 'filter_rows', 'find_contact', 'find_duplicate', 'find_interview', 'find_mail', 'find_offer', 'find_talk', 'format_table', 'health_score', 'history_path', 'interview_path', 'last_activity_date', 'last_stage_change_date', 'mail_path', 'main', 'next_contact_id', 'next_id', 'next_interview_id', 'next_mail_id', 'next_offer_id', 'next_talk_id', 'normalize_message_id', 'offer_path', 'parse_import_csv', 'parse_iso_date', 'plan_import', 'preview_add', 'preview_add_fields', 'preview_import', 'preview_interview_add_fields', 'preview_interview_update_fields', 'preview_mail_fields', 'preview_talk_fields', 'preview_update_fields', 'read_contacts', 'read_history', 'read_interviews', 'read_mails', 'read_offers', 'read_rows', 'read_talks', 'resolve_ws', 'run_check', 'set_workspace', 'sort_key', 'stage_base_date', 'stale_days', 'talk_path', 'tracking_targets', 'write_contacts', 'write_interviews', 'write_mails', 'write_offers', 'write_rows', 'write_talks']
