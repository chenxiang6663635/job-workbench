# -*- coding: utf-8 -*-
"""主表新增的两段式：预览（不落盘）→ 令牌 → apply。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import logging


from jobws_core.filelock import file_lock  # noqa: E402

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (ConflictError, TERMINAL_STAGES, _lock_path, _tracking_targets, check_date, check_direction, check_reason_required, find_duplicate, next_id, resolve_ws)
from ._schema import (BATCHES, FIELDS, SOURCES, STAGES)
from .applications import (append_history, read_rows, write_rows)
from .importing import (commit_import)



def _validate_add_fields(fields, workspace=None):
    """新增字段的校验（与命令行同一口径，预览与落盘两段共用）。

    fields 用**中文列名**（与 CSV 表头一致），返回错误列表；空列表表示可写。
    刻意不在这里写盘：两段式的第一步与第二步各要跑一遍（第二步是重校验）。
    """
    errors = []
    if not fields.get("公司"):
        errors.append("`--company` 不能为空")
    if not fields.get("岗位"):
        errors.append("`--role` 不能为空")

    errs = check_direction(fields.get("方向") or "", workspace)
    if errs:
        errors.extend(errs)
    batch = fields.get("批次") or ""
    if batch not in BATCHES:
        errors.append("`--batch` 必须是 %s 之一，实际为 `%s`" % ("/".join(BATCHES), batch))
    # strip 后再判：与 import / Web API / run_check 三处同一口径。
    # 注意：落盘值的归一在 preview_add_fields 完成（本函数只负责判定）——
    # 绕过它直接拿返回字段落盘的调用方，需自行 strip。
    source = (fields.get("来源") or "").strip()
    if source and source not in SOURCES:
        errors.append("`--source` 必须是 %s 之一，实际为 `%s`" % ("/".join(SOURCES), source))
    stage = fields.get("当前阶段") or ""
    if stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一，实际为 `%s`"
                      % ("/".join(STAGES + TERMINAL_STAGES), stage))

    for key in ("截止日期", "投递日期", "下次动作日期"):
        errs = check_date(fields.get(key) or "", key)
        if errs:
            errors.extend(errs)

    score = fields.get("评分") or ""
    if score:
        try:
            if not 0 <= int(score) <= 100:
                errors.append("`--score` 必须在 0–100 之间，实际为 %s" % score)
        except ValueError:
            errors.append("`--score` 不是整数：%s" % score)

    errors.extend(check_reason_required(stage, fields.get("状态原因") or ""))

    # canonical 去重：同公司+岗位且既有记录非终态则拒绝
    rows = read_rows(workspace)
    dup, dup_is_terminal = find_duplicate(rows, fields.get("公司"), fields.get("岗位"))
    if dup and not dup_is_terminal:
        errors.append("已存在相同公司+岗位的记录 `%s`（当前阶段：%s），请勿重复录入"
                      % (dup.get("id", ""), dup.get("当前阶段", "")))
    return errors



def preview_add_fields(fields, workspace=None):
    """按**中文字段**预览一次新增（**不落盘**）：返回 (errors, plan)。

    不吃 argparse 的调用方（MCP 包）用这个入口；CLI 的 `preview_add(args, …)`
    只是把命令行参数转成字段再调它——两段式的两边必须走同一份校验。
    """
    fields = {field: (fields.get(field) or "") for field in FIELDS}
    # 「来源 / 链接」进入即归一化（去首尾空白）：枚举校验是按 strip 后的值判的，
    # 若把带空格的原文写进 CSV，「 内推 」这类值会绕过一切枚举检查（独立审查）。
    # 只收这两列——本批新增的口径；其它列维持现状，避免悄悄改变既有行为。
    for field in ("来源", "链接"):
        fields[field] = fields[field].strip()
    errors = _validate_add_fields(fields, workspace)
    if errors:
        return errors, None
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in FIELDS:
        if fields.get(field):
            diff.append("| %s | %s |" % (field, fields[field]))
    plan = {
        "payload": {"fields": fields},
        "summary": "新增投递：%s %s（%s）" % (fields["公司"], fields["岗位"],
                                          fields["当前阶段"]),
        "diff": diff,
        "targets": _tracking_targets(workspace),
    }
    return [], plan



def preview_add(args, workspace=None):
    """命令行入口：把参数转成字段，其余交给 `preview_add_fields`。"""
    return preview_add_fields({
        "公司": args.company or "", "岗位": args.role or "",
        "方向": args.direction or "", "批次": args.batch or "",
        "来源": args.source or "", "截止日期": args.deadline or "",
        "投递日期": args.applied or "", "当前阶段": args.stage or "",
        "状态原因": args.reason or "", "下次动作": args.next or "",
        "下次动作日期": args.next_date or "", "简历版本": args.resume or "",
        "评分": "" if args.score is None else str(args.score),
        "归档目录": args.archive or "", "备注": args.note or "",
        "链接": args.link or "",
    }, workspace)



def apply_approved_add(payload, workspace=None):
    """两段式的第二步：按已确认的载荷新增一条记录。

    重校验：预览到确认之间可能已经有人加了同公司+岗位的记录——那种情况下
    拒绝比"硬写第二条"安全（ConflictError → 调用方提示重新预览）。
    """
    ws = resolve_ws(workspace)
    fields = dict(payload.get("fields") or {})
    # 「读最新 → 重校验 → 写」整段持锁：与 Web 直写路径同一把锁，防止并发的
    # 两次落盘各自算出同一个 next_id（后写覆盖前写）——详见 _lock_path。
    with file_lock(_lock_path(ws)):
        errors = _validate_add_fields(fields, ws)
        if errors:
            raise ConflictError("预览之后数据有变化，已拒绝写入：%s（请重新预览）"
                                % "；".join(errors))
        rows = read_rows(ws)
        record = {field: "" for field in FIELDS}
        record.update(fields)
        record["id"] = next_id(rows)
        rows.append(record)
        write_rows(rows, ws)
        # 时间线：新建也入账，作为停留天数与首次活动的基准
        append_history([{"id": record["id"], "字段": "创建", "原值": "",
                         "新值": "%s %s（%s）" % (record["公司"], record["岗位"],
                                             record["当前阶段"])}], ws)
        return {"id": record["id"], "written": 1,
                "summary": "已新增 %s %s（id=%s）" % (record["公司"], record["岗位"],
                                                      record["id"])}



def apply_approved_import(payload, workspace=None):
    """两段式的第二步：按已确认的载荷批量导入。

    复用 `commit_import` 的重校验：预览到确认之间出现新的重复行时整批拒绝
    （它返回 -1），绝不半批写入。
    """
    ws = resolve_ws(workspace)
    preview = payload.get("preview")
    if not isinstance(preview, dict):
        raise ConflictError("令牌里的导入预览数据不完整——请重新预览。")
    # commit_import 的「按锁内最新主表重校验 + 写入」必须在锁内整段完成
    with file_lock(_lock_path(ws)):
        written = commit_import(preview, ws)
    if written < 0:
        raise ConflictError("预览之后出现了新的重复行，整批未写入。请重新预览。")
    return {"written": written, "summary": "已导入 %d 条投递记录" % written}
