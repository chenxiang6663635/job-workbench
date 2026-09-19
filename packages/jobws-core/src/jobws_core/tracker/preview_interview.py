# -*- coding: utf-8 -*-
"""面试表的两段式：预览（不落盘）→ 令牌 → apply。

结构照 `preview_app.py`（主表新增的两段式）。为什么面试要单独一层：
CLI 的 `track interview` 原本是**直写**，而 MCP 与 GUI 都需要同一份「预览给差异、
确认后落盘」的语义——把校验与载荷构造收在这里，三处共用，避免各拼一份之后
「预览说 X、落盘写 Y」。

校验口径与 `_cli_interview.py` 保持一致（同一组枚举、同一条外键规则）：
- 关联记录非空时必须存在于主表；
- 未关联记录时必须给公司；
- 轮次 / 形式 / 结果必须是 schema 里的枚举值。
"""

import logging


from jobws_core.filelock import file_lock  # noqa: E402

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (ConflictError, _lock_path, _tracking_targets, resolve_ws)
from ._schema import (INTERVIEW_FIELDS, INTERVIEW_FORMS, INTERVIEW_RESULTS,
                      INTERVIEW_ROUNDS)
from .applications import (append_history, read_rows)
from .interviews import (find_interview, next_interview_id, read_interviews,
                         write_interviews)


# 可更新字段：与 CLI 的 update 分支同集合（面试 id / 关联记录 / 公司 / 岗位
# 不在其内——改归属要另建一条，避免把时间线接错）。
INTERVIEW_UPDATABLE = ("面试时间", "轮次", "形式", "链接", "面试官",
                       "问题记录", "我的回答要点", "复盘与改进", "结果")


def _validate_add_fields(fields, workspace=None):
    """面试新增字段校验（预览与落盘两段共用）。返回错误列表，空列表表示可写。"""
    errors = []
    link = (fields.get("关联记录") or "").strip()
    if link:
        main_rows = read_rows(workspace)
        if not any((r.get("id") or "").strip() == link for r in main_rows):
            errors.append("找不到关联记录 `%s`，先 track add 或省略关联记录" % link)
    elif not (fields.get("公司") or "").strip():
        errors.append("未关联记录时必须给公司")

    round_value = fields.get("轮次") or ""
    if round_value not in INTERVIEW_ROUNDS:
        errors.append("轮次必须是 %s 之一，实际为 `%s`"
                      % ("/".join(INTERVIEW_ROUNDS), round_value))

    form = fields.get("形式") or ""
    if form and form not in INTERVIEW_FORMS:
        errors.append("形式必须是 %s 之一，实际为 `%s`" % ("/".join(INTERVIEW_FORMS), form))

    result = fields.get("结果") or ""
    if result not in INTERVIEW_RESULTS:
        errors.append("结果必须是 %s 之一，实际为 `%s`"
                      % ("/".join(INTERVIEW_RESULTS), result))
    return errors


def _validate_update_fields(changes):
    """面试更新的字段校验（只校验实际要改的字段）。"""
    errors = []
    if "轮次" in changes and changes["轮次"] not in INTERVIEW_ROUNDS:
        errors.append("轮次必须是 %s 之一，实际为 `%s`"
                      % ("/".join(INTERVIEW_ROUNDS), changes["轮次"]))
    if "形式" in changes and changes["形式"] and changes["形式"] not in INTERVIEW_FORMS:
        errors.append("形式必须是 %s 之一，实际为 `%s`"
                      % ("/".join(INTERVIEW_FORMS), changes["形式"]))
    if "结果" in changes and changes["结果"] not in INTERVIEW_RESULTS:
        errors.append("结果必须是 %s 之一，实际为 `%s`"
                      % ("/".join(INTERVIEW_RESULTS), changes["结果"]))
    return errors


def _row_diff(record):
    """把一行渲染成「字段 | 值」两列表（预览用）。"""
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in INTERVIEW_FIELDS:
        if record.get(field):
            diff.append("| %s | %s |" % (field, record[field]))
    return diff


def _change_diff(record, changes):
    """逐字段差异表：原值 -> 新值。"""
    diff = ["| 字段 | 原值 | 新值 |", "|---|---|---|"]
    for field, value in changes.items():
        diff.append("| %s | %s | %s |" % (field, record.get(field) or "（空）", value))
    return diff


def preview_interview_add_fields(fields, workspace=None):
    """按**中文字段**预览一次面试新增（**不落盘**）：返回 (errors, plan)。

    给了关联记录但没给公司/岗位时，从主表带出（与 CLI 同口径），保证列表可读。
    """
    record = {field: (fields.get(field) or "") for field in INTERVIEW_FIELDS}
    for field in ("关联记录", "公司", "岗位"):
        record[field] = record[field].strip()
    # 默认值与 CLI parser 一致（--round 默认「一面」、--result 默认「待定」）：
    # 两段式的第一段必须与命令行同一口径，否则不吃 argparse 的调用方（MCP）
    # 少给这两个字段就会被枚举校验拦下——枚举校验本身是对的，缺的是默认值。
    record["轮次"] = record["轮次"] or "一面"
    record["结果"] = record["结果"] or "待定"

    link = record["关联记录"]
    if link:
        src = next((r for r in read_rows(workspace)
                    if (r.get("id") or "").strip() == link), None)
        if src:
            record["公司"] = record["公司"] or src.get("公司", "")
            record["岗位"] = record["岗位"] or src.get("岗位", "")

    errors = _validate_add_fields(record, workspace)
    if errors:
        return errors, None

    plan = {
        "payload": {"fields": record},
        "summary": "新增面试：%s %s（%s）" % (record["公司"], record["岗位"],
                                           record["轮次"]),
        "diff": _row_diff(record),
        "targets": _tracking_targets(workspace),
    }
    return [], plan


def preview_interview_update_fields(payload, workspace=None):
    """预览一次面试更新（**不落盘**）：返回 (errors, plan)。

    只列**要改**的字段；changes 里没提到的字段不动。没有实际变化时返回错误
    （与 CLI 的「没有字段变化，未写入」同语义）。
    """
    ws = resolve_ws(workspace)
    interview_id = (payload.get("id") or "").strip()
    changes = {key: value for key, value in (payload.get("changes") or {}).items()
               if key in INTERVIEW_UPDATABLE}

    row = find_interview(read_interviews(ws), interview_id)
    if not row:
        return ["找不到面试 `%s`" % interview_id], None

    effective = {key: value for key, value in changes.items()
                 if (row.get(key) or "") != (value or "")}
    if not effective:
        return ["没有字段变化（要改什么就传什么）"], None

    errors = _validate_update_fields(effective)
    if errors:
        return errors, None

    plan = {
        "payload": {"id": interview_id, "changes": effective},
        "summary": "更新面试 %s（%s %s）：%s"
                   % (interview_id, row.get("公司", ""), row.get("岗位", ""),
                      "、".join(effective.keys())),
        "diff": _change_diff(row, effective),
        "targets": _tracking_targets(ws),
    }
    return [], plan


def apply_approved_interview_add(payload, workspace=None):
    """两段式的第二步：按已确认的载荷新增一条面试记录。

    重校验在锁内跑：预览到确认之间若关联记录被删或枚举被改，拒绝比硬写安全。
    """
    ws = resolve_ws(workspace)
    fields = dict(payload.get("fields") or {})
    with file_lock(_lock_path(ws)):
        errors = _validate_add_fields(fields, ws)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))
        rows = read_interviews(ws)
        record = {field: "" for field in INTERVIEW_FIELDS}
        record.update(fields)
        record["面试id"] = next_interview_id(rows)
        rows.append(record)
        write_interviews(rows, ws)
        # 面试也入账时间线：它是岗位推进的一部分，与 CLI 的 _interview_add 同款
        if record["关联记录"]:
            append_history([{
                "id": record["关联记录"],
                "字段": "面试",
                "原值": "",
                "新值": "%s %s（%s）" % (record["轮次"],
                                     record["面试时间"] or "时间待定",
                                     record["面试id"]),
            }], ws)
        return {"id": record["面试id"], "written": 1,
                "summary": "已记录面试 %s：%s %s %s"
                           % (record["面试id"], record["公司"], record["岗位"],
                              record["轮次"])}


def apply_approved_interview_update(payload, workspace=None):
    """两段式的第二步：按已确认的载荷更新一条面试记录（锁内重校验）。"""
    ws = resolve_ws(workspace)
    interview_id = (payload.get("id") or "").strip()
    # 锁内**再次**按白名单过滤：预览段签发时已滤过一次，这里再滤是防御纵深——
    # 任何未来绕过 preview 直构 payload 的调用方（新端、脚本、测试 helper）
    # 都不能借道把「面试id / 关联记录 / 公司」这类归属字段顺手改掉。
    changes = {key: value for key, value in (payload.get("changes") or {}).items()
               if key in INTERVIEW_UPDATABLE}
    with file_lock(_lock_path(ws)):
        rows = read_interviews(ws)
        row = find_interview(rows, interview_id)
        if not row:
            raise ConflictError("预览之后找不到面试 `%s`（请重新预览）" % interview_id)
        errors = _validate_update_fields(changes)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))
        changed = []
        for field, value in changes.items():
            if row.get(field, "") != (value or ""):
                changed.append(field)
                row[field] = value
        if not changed:
            return {"id": interview_id, "written": 0,
                    "summary": "没有字段变化，未写入"}
        write_interviews(rows, ws)
        return {"id": interview_id, "written": 1,
                "summary": "已更新面试 %s：%s" % (interview_id, "、".join(changed))}
