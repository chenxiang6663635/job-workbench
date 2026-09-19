# -*- coding: utf-8 -*-
"""CSV 批量导入：解析、逐行校验、预览、提交与 CLI 命令。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import logging


# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core
from ._core import (TERMINAL_STAGES, _tracking_targets, check_direction, check_reason_required, dedup_key, find_duplicate, next_id, parse_iso_date, resolve_ws)
from ._schema import (BATCHES, FIELDS, IMPORT_REQUIRED, SOURCES, STAGES)
from .applications import (append_history, read_rows, write_rows)



def parse_import_csv(text):
    """解析 CSV 文本（utf-8 兼容 Excel 导出的 BOM），表头与 FIELDS 宽松匹配。

    允许缺列（缺的留空）、未知列忽略；「公司」「岗位」缺一不可。
    返回 (rows, unknown_columns)。解析失败抛 ValueError（人话，可直接展示）。
    """
    raw = (text or "").lstrip("\ufeff")
    if not raw.strip():
        raise ValueError("CSV 内容为空")
    values = list(csv.reader(io.StringIO(raw)))
    header = [(h or "").strip() for h in (values[0] or [])]
    if not any(header):
        raise ValueError("CSV 缺少表头行")
    if "公司" not in header or "岗位" not in header:
        raise ValueError("CSV 必须包含「公司」与「岗位」两列（表头行需与追踪表字段同名）")
    known = [f for f in FIELDS if f != "id"]
    unknown = [h for h in header if h and h not in known]
    rows = []
    for line in values[1:]:
        if not any((v or "").strip() for v in line):
            continue  # 整行为空（Excel 常见的拖尾空行）直接跳过
        row = {f: "" for f in known}
        for name, value in zip(header, line):
            if name in row:
                row[name] = (value or "").strip()
        rows.append(row)
    return rows, unknown



def _validate_import_row(row, existing_rows, seen_in_batch, workspace=None):
    """校验一行导入数据，返回 (status, errors)。

    status：ok（可导入）/ duplicate（与既有非终态记录或同批前文重复，跳过）
    / error（数据问题，必须修正后才允许提交）。duplicate 不是错误——
    「挂了再投一次」是合法动作，但同公司+岗位活跃记录已存在时不应重复建行。
    """
    errors = []
    for col in IMPORT_REQUIRED:
        if not (row.get(col) or "").strip():
            errors.append("「%s」为空" % col)
    for col in ("截止日期", "投递日期", "下次动作日期"):
        value = (row.get(col) or "").strip()
        if value and not parse_iso_date(value):
            errors.append("「%s」的「%s」不是 YYYY-MM-DD" % (col, value))
    stage = (row.get("当前阶段") or "").strip()
    if stage and stage not in STAGES + TERMINAL_STAGES:
        errors.append("当前阶段「%s」不在 %s" % (stage, "/".join(STAGES + TERMINAL_STAGES)))
    batch = (row.get("批次") or "").strip()
    if batch and batch not in BATCHES:
        errors.append("批次「%s」不在 %s" % (batch, "/".join(BATCHES)))
    source = (row.get("来源") or "").strip()
    if source and source not in SOURCES:
        errors.append("来源「%s」不在 %s" % (source, "/".join(SOURCES)))
    score_raw = (row.get("评分") or "").strip()
    if score_raw:
        try:
            if not 0 <= int(score_raw) <= 100:
                errors.append("评分「%s」超出 0–100" % score_raw)
        except ValueError:
            errors.append("评分「%s」不是整数" % score_raw)
    direction = (row.get("方向") or "").strip()
    if direction:
        errs = check_direction(direction, workspace)
        if errs:
            errors.extend(errs)
    errors.extend(check_reason_required(stage, row.get("状态原因") or ""))
    if errors:
        return "error", errors

    dup, dup_terminal = find_duplicate(existing_rows, row.get("公司"), row.get("岗位"))
    if dup and not dup_terminal:
        return "duplicate", ["与既有记录 %s（%s）重复" % (dup.get("id", ""), dup.get("当前阶段", ""))]
    key = dedup_key(row.get("公司"), row.get("岗位"))
    if key in seen_in_batch:
        return "duplicate", ["与本批前面的行重复"]
    seen_in_batch.add(key)
    return "ok", []



def preview_import(csv_rows, existing_rows=None, workspace=None):
    """逐行预校验，返回 {"ok": [...], "duplicate": [...], "error": [...]}。

    每个条目为 {"line": 行号（从 2 起，1 是表头）, "row": 原始行, "errors": [...]}。
    existing_rows 缺省时读当前主表——Web 预览与 CLI --dry-run 共用此入口。
    """
    if existing_rows is None:
        existing_rows = read_rows(workspace)
    result = {"ok": [], "duplicate": [], "error": []}
    seen = set()
    for i, row in enumerate(csv_rows, start=2):
        status, errors = _validate_import_row(row, existing_rows, seen, workspace)
        result[status].append({"line": i, "row": row, "errors": errors})
    return result



def commit_import(preview, workspace=None):
    """把 preview 中 ok 的行写入主表并逐条入账时间线，返回写入条数。

    调用方必须持 tracker.lock。提交前基于锁内最新主表**重新校验**：
    预览到提交之间用户可能又手工加过记录，重校验不过的行整批拒绝
    （返回 -1 表示冲突），绝不半批写入——与「失败整批回滚」的约定一致。
    """
    accepted = preview.get("ok") or []
    if not accepted:
        return 0
    ws = resolve_ws(workspace)
    rows = read_rows(ws)
    seen = set()
    for item in accepted:
        status, errors = _validate_import_row(item["row"], rows, seen, ws)
        if status != "ok":
            return -1
    entries = []
    for item in accepted:
        row = item["row"]
        record = {f: "" for f in FIELDS}
        record["id"] = next_id(rows)
        for field in FIELDS:
            if field != "id":
                record[field] = (row.get(field) or "").strip()
        rows.append(record)
        entries.append({"id": record["id"], "字段": "创建", "原值": "",
                        "新值": "%s %s（%s）" % (record["公司"], record["岗位"],
                                            record["当前阶段"])})
    write_rows(rows, ws)
    append_history(entries, ws)
    return len(accepted)



def plan_import(preview, workspace=None):
    """把导入预览整理成两段式所需的载荷与差异表（CLI 与网页端共用一份构造）。

    `preview` 是 `preview_import()` 的结果；返回 `approval.preview()` 要的
    四个参数。刻意只留这一份构造：两处各自拼 diff，迟早出现「预览说 X、
    落盘写 Y」——那比不预览更糟。
    """
    accepted = preview.get("ok") or []
    diff = ["| 状态 | 行 | 公司 | 岗位 |", "|---|---|---|---|"]
    for item in accepted:
        diff.append("| 将新增 | %d | %s | %s |" % (
            item["line"], item["row"].get("公司", ""), item["row"].get("岗位", "")))
    return {
        "payload": {"preview": preview},
        "summary": "导入 %d 条投递记录" % len(accepted),
        "diff": diff,
        "targets": _tracking_targets(workspace),
    }



def cmd_import(args):
    """CSV 批量导入：--dry-run 只预览；默认预览通过即提交（与 Web 同一校验）。"""
    try:
        with io.open(args.file, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except OSError as exc:
        print("错误：读不到文件 %s（%s）" % (args.file, exc))
        return 1
    try:
        csv_rows, unknown = parse_import_csv(text)
    except ValueError as exc:
        print("错误：%s" % exc)
        return 1
    if unknown:
        print("（忽略未知列：%s）" % "、".join(unknown))

    preview = preview_import(csv_rows, workspace=_core.WORKSPACE)
    print("## 导入预览\n")
    print("| 状态 | 行 | 公司 | 岗位 | 原因 |")
    print("|---|---|---|---|---|")
    for status, label in (("ok", "将新增"), ("duplicate", "重复跳过"), ("error", "错误")):
        for item in preview[status]:
            print("| %s | %d | %s | %s | %s |" % (
                label, item["line"], item["row"].get("公司", ""),
                item["row"].get("岗位", ""), "；".join(item["errors"]) or "—"))

    print("\n将新增 %d 条 / 跳过 %d 条（重复 %d、错误 %d）" % (
        len(preview["ok"]), len(preview["duplicate"]) + len(preview["error"]),
        len(preview["duplicate"]), len(preview["error"])))
    if preview["error"]:
        print("\n存在错误行，未写入。请修正后重试。")
        return 1
    if args.dry_run:
        print("\n--dry-run：未写入。")
        return 0
    if getattr(args, "preview", False):
        import approval
        plan = plan_import(preview, _core.WORKSPACE)
        result = approval.preview(
            "track.import", _core.WORKSPACE, plan["payload"],
            plan["summary"], plan["diff"], plan["targets"])
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0
    written = commit_import(preview, workspace=_core.WORKSPACE)
    if written < 0:
        print("\n提交时发现新的重复（预览后数据有变化），整批未写入。请重新预览。")
        return 1
    print("\n已写入 %d 条，并逐条记入变更时间线。" % written)
    return 0
