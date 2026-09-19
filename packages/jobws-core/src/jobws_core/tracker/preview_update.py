# -*- coding: utf-8 -*-
"""主表更新的两段式：预览（不落盘）→ 令牌 → apply。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import logging
import re


from jobws_core.filelock import file_lock  # noqa: E402

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (ConflictError, TERMINAL_STAGES, _lock_path, _tracking_targets, check_date, check_reason_required, check_terminal_transition, resolve_ws)
from ._schema import (STAGES, UPDATABLE)
from .applications import (append_history, diff_entries, read_rows, write_rows)



def _validate_update(target, changes, workspace=None):
    """更新字段的校验（与命令行同一口径，预览与落盘两段共用）。

    target 是主表里那一行（调用方已按 id 找好）；changes 是**要改的字段**
    （中文列名 → 新值字符串）——不在 changes 里的字段不动。
    """
    errors = []
    stage = changes.get("当前阶段")
    if stage is not None and stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一" % "/".join(STAGES + TERMINAL_STAGES))
    score = changes.get("评分")
    if score is not None and score != "":
        try:
            if not 0 <= int(score) <= 100:
                errors.append("`--score` 必须在 0–100 之间")
        except ValueError:
            errors.append("`--score` 不是整数：%s" % score)
    for key in ("下次动作日期", "投递日期", "截止日期"):
        value = changes.get(key)
        if value:
            errs = check_date(value, key)
            if errs:
                errors.extend(errs)

    # 终态不回退：原阶段已是终态时不可再改阶段
    if stage:
        errors.extend(check_terminal_transition(target.get("当前阶段", ""), stage))
    # 终态必填原因：按更新后的最终阶段与最终原因判定。
    # 注意 `"" 也是显式值`：`--reason ""` 表示"清空原因"，它会被收进 changes
    # （cmd_update 按 `is not None` 收），所以这里用 `in changes` 而**不是**
    # `changes.get(...) or ...`——后者会把"清空"悄悄当成"没提供"（独立审查 MAJOR-1）。
    final_stage = stage if stage is not None else target.get("当前阶段", "")
    final_reason = (changes["状态原因"] if "状态原因" in changes
                    else target.get("状态原因", ""))
    errors.extend(check_reason_required(final_stage, final_reason))
    return errors



def _find_by_id(rows, app_id):
    for row in rows:
        if (row.get("id") or "").strip() == app_id:
            return row
    return None



def preview_update_fields(payload, workspace=None):
    """按载荷预览一次更新（**不落盘**）：返回 (errors, plan)。

    payload = {"id": "A001", "changes": {字段: 新值}}——只列**要改**的字段。
    """
    ws = resolve_ws(workspace)
    app_id = (payload.get("id") or "").strip()
    changes = dict(payload.get("changes") or {})
    # 「链接」与新增路径同一口径：落盘前归一（校验与写入都不该看到带空格的原值；
    # 两段式的两边都经过这里，归一后的值随载荷进令牌，落盘段不再二次处理）
    if "链接" in changes:
        changes["链接"] = (changes["链接"] or "").strip()
    target = _find_by_id(read_rows(ws), app_id)
    if target is None:
        return ["找不到 id 为 `%s` 的记录" % app_id], None

    errors = _validate_update(target, changes, ws)
    if errors:
        return errors, None
    if not changes:
        return ["没有提供任何要更新的字段。可更新字段：%s" % "、".join(UPDATABLE)], None

    diff = ["| 字段 | 原值 | 新值 |", "|---|---|---|"]
    for field in sorted(changes):
        diff.append("| %s | %s | %s |" % (
            field, target.get(field, "") or "（空）", changes[field] or "（空）"))
    return [], {
        "payload": {"id": app_id, "changes": changes},
        "summary": "更新 %s（%s %s）：改 %d 个字段" % (
            app_id, target.get("公司", ""), target.get("岗位", ""), len(changes)),
        "diff": diff,
        "targets": _tracking_targets(ws),
    }



def apply_approved_update(payload, workspace=None):
    """两段式的第二步：按已确认的载荷更新一条记录。

    重校验（含"终态不回退"）：预览到确认之间记录可能已被改动——不通过就拒绝，
    宁可让用户重新预览，也不在半信半疑的状态下落盘。
    """
    ws = resolve_ws(workspace)
    app_id = payload.get("id")
    changes = dict(payload.get("changes") or {})
    with file_lock(_lock_path(ws)):
        rows = read_rows(ws)
        target = _find_by_id(rows, app_id)
        if target is None:
            raise ConflictError("记录 `%s` 不存在了（预览之后被改过 id 或删除）——请重新预览。"
                                % app_id)
        errors = _validate_update(target, changes, ws)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))

        before = dict(target)
        for field, value in changes.items():
            target[field] = value
        write_rows(rows, ws)
        append_history(diff_entries(app_id, before, target), ws)
        # 回传**实际**差异：预览到确认之间可能隔了很久，主表里的"原值"未必还是预览
        # 时那个——展示落盘时的真实前后值才算数（独立审查 MAJOR-2）。
        diff = ["| 字段 | 原值 | 新值 |", "|---|---|---|"]
        for field in sorted(changes):
            diff.append("| %s | %s | %s |" % (
                field, before.get(field, "") or "（空）",
                target.get(field, "") or "（空）"))
        return {"id": app_id, "diff": diff,
                "summary": "已更新 %s（%s %s）" % (app_id, target.get("公司", ""),
                                                target.get("岗位", ""))}
