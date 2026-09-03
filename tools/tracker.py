# -*- coding: utf-8 -*-
"""投递追踪表增删查改。

数据存为 CSV（UTF-8 with BOM，Excel 直接打开中文不乱码）。
每次写入前全量重读并做字段级校验，校验失败不落盘。

用法：
    python tools/tracker.py add --company "某某" --role "热管理工程师" \
        --direction datacenter --batch 正式批 --source 企业校招官网 \
        --deadline 2026-09-30 --resume datacenter --score 78 \
        --archive "05_投递追踪/applications/某某_热管理工程师"

    python tools/tracker.py list [--stage 笔试] [--direction datacenter]
                                 [--batch 提前批] [--due-within 7]
    python tools/tracker.py show --id A001
    python tools/tracker.py update --id A001 --stage 一面 --next "准备项目二口述"
    python tools/tracker.py history [--id A001] [--limit 20]

变更时间线：每次 add/update 会把字段级差异追加到
<工作区>/05_投递追踪/history.csv（时间, id, 字段, 原值, 新值），
供停留天数统计与前端时间线展示使用。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import csv
import io
import os
import re
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORKSPACE = os.path.join(ROOT, "personal")

# 由 main() 在解析 --workspace 后赋值；模块级常量仅供被 report.py 导入时兜底
WORKSPACE = DEFAULT_WORKSPACE


def set_workspace(path):
    """供 report.py 等导入方设置工作区。"""
    global WORKSPACE
    WORKSPACE = os.path.abspath(path)


def resolve_ws(workspace=None):
    """显式传参优先，缺省回退全局。Web 并发场景必须显式传参。"""
    return os.path.abspath(workspace) if workspace else WORKSPACE


def available_directions(workspace=None):
    """读取工作区装入的领域插件支持的方向 ID。

    读不到时返回空列表——此时调用方应放行而非报错，
    因为用户可能还没装入插件，或使用了自定义方向。
    """
    d = os.path.join(resolve_ws(workspace), "config", "directions")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md"))


def check_direction(value, workspace=None):
    """校验方向 ID。插件不可用时放行，可用时严格校验。"""
    valid = available_directions(workspace)
    if not valid:
        return None
    if value in valid or value in DIRECTIONS:
        return None
    return ["`--direction` 必须是 %s 或 other，实际为 `%s`" % ("/".join(valid), value)]


def csv_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", "tracker.csv")

# 输出时保持固定字段顺序
FIELDS = [
    "id", "公司", "岗位", "方向", "批次", "来源", "截止日期", "投递日期",
    "当前阶段", "状态原因", "下次动作", "下次动作日期", "简历版本", "评分",
    "归档目录", "备注",
]

# 方向 ID 取决于工作区装入的领域插件，不在脚本里写死。
# 校验时动态读取 <工作区>/config/directions/*.md，读不到则放行（只记录不拦截）。
DIRECTIONS = ["other"]
BATCHES = ["提前批", "正式批", "补录"]
SOURCES = ["应届生求职网", "牛客", "企业校招官网", "学校就业网", "内推", "其他"]

# 正常流转顺序；终态单独处理
STAGES = ["待投", "已投", "笔试", "一面", "二面", "三面", "HR面", "offer", "签约"]
TERMINAL_STAGES = ["已挂", "已放弃"]

# update 只允许改这些字段，公司与岗位不可改（改则需新建记录并作废原记录）
UPDATABLE = ["当前阶段", "状态原因", "下次动作", "下次动作日期", "备注", "评分",
             "投递日期", "截止日期"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 变更时间线：独立 CSV，主表保持「一行一岗位」的当前状态快照
HISTORY_FILE = "history.csv"
HISTORY_FIELDS = ["时间", "id", "字段", "原值", "新值"]
# 记入时间线的字段。公司与岗位不可改，故不在其中。
HISTORY_TRACKED = ["当前阶段", "状态原因", "下次动作", "下次动作日期",
                   "投递日期", "截止日期", "评分", "备注"]

# 静默提醒默认阈值：非终态记录距最后一次推进超过该天数即提示
STALE_DAYS = 14


def parse_iso_date(value):
    """解析 YYYY-MM-DD，非法返回 None。与 report.parse_date 同规则，
    但 tracker 不 import report（脚本互不调用，report 才导入 tracker）。
    """
    raw = (value or "").strip()
    if not DATE_RE.match(raw):
        return None
    y, m, d = (int(x) for x in raw.split("-"))
    try:
        return date(y, m, d)
    except ValueError:
        return None


def history_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", HISTORY_FILE)


def read_history(workspace=None, app_id=None):
    """读取时间线。按写入顺序（时间升序）返回，app_id 非空时只返回该记录。"""
    path = history_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("id") or "").strip() == app_id]
    return rows


def append_history(entries, workspace=None):
    """追加变更条目。entries 为字典列表，键为 id / 字段 / 原值 / 新值。

    新建文件用 utf-8-sig 补 BOM（与主表一致，Excel 中文不乱码）；
    已有文件改用 utf-8 追加——utf-8-sig 每次 open 都会写 BOM，
    在追加场景下会把 BOM 插进文件中间。
    """
    if not entries:
        return 0
    path = history_path(workspace)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)

    is_new = not os.path.isfile(path) or os.path.getsize(path) == 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with io.open(path, "w" if is_new else "a",
                 encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS,
                                extrasaction="ignore", restval="")
        if is_new:
            writer.writeheader()
        for entry in entries:
            row = {"时间": now, "id": entry.get("id", ""), "字段": entry.get("字段", ""),
                   "原值": entry.get("原值", ""), "新值": entry.get("新值", "")}
            writer.writerow(row)
    return len(entries)


def diff_entries(app_id, old_row, new_row, fields=None):
    """对比两行，返回有变化的字段条目列表（空列表表示无变化）。"""
    out = []
    for field in (fields or HISTORY_TRACKED):
        before = ((old_row or {}).get(field) or "").strip()
        after = ((new_row or {}).get(field) or "").strip()
        if before != after:
            out.append({"id": app_id, "字段": field, "原值": before, "新值": after})
    return out


def _history_date(entries, app_id, field=None):
    """取某记录最后一次变更（或最后一次指定字段变更）的日期。"""
    best = None
    for entry in entries:
        if (entry.get("id") or "").strip() != app_id:
            continue
        if field and (entry.get("字段") or "").strip() != field:
            continue
        when = parse_iso_date((entry.get("时间") or "")[:10])
        if when and (best is None or when > best):
            best = when
    return best


def last_stage_change_date(app_id, entries):
    """最后一次「当前阶段」变更日期，无则 None。"""
    return _history_date(entries, app_id, "当前阶段")


def last_activity_date(app_id, entries):
    """最后一次任意变更日期（含创建），无则 None。"""
    return _history_date(entries, app_id)


def stage_base_date(row, entries, app_id=None):
    """停留天数的基准日，按优先级回退。

    最后一次阶段变更 → 投递日期 → 最后一次任意变更 → None。

    投递日期排在「任意变更」之前：投递日期是用户声明的流程起点，
    而「任意变更」里包含记录录入时间——补录一条一个月前投的岗位时，
    若以录入时间为准就永远不会触发静默提醒，与语义相反。
    「任意变更」只在既无阶段变更、又没填投递日期时兜底。

    旧数据没有 history.csv 时自动退到投递日期，不需要迁移。
    """
    app_id = app_id or (row.get("id") or "").strip()
    when = last_stage_change_date(app_id, entries)
    if when:
        return when
    when = parse_iso_date(row.get("投递日期"))
    if when:
        return when
    return last_activity_date(app_id, entries)


def stale_days(row, entries, today=None):
    """当前阶段已停留天数。无基准日返回 None（不参与静默判定）。"""
    base = stage_base_date(row, entries)
    if base is None:
        return None
    today = today or date.today()
    return (today - base).days


def read_rows(workspace=None):
    path = csv_path(workspace)
    if not os.path.isfile(path):
        return []
    # utf-8-sig 读取时自动去掉 BOM
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def write_rows(rows, workspace=None):
    path = csv_path(workspace)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    # utf-8-sig 写入时加 BOM，Excel 直接打开不乱码
    # restval 保证旧文件（缺新增列）写回时补出空列，避免 None 落盘成 "None"
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore",
                                restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})


def next_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^A(\d+)$", (row.get("id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "A%03d" % (max_num + 1)


def check_date(value, label, allow_empty=True):
    if not value:
        if allow_empty:
            return None
        return ["`%s` 不能为空" % label]
    if not DATE_RE.match(value):
        return ["`%s: %s` 日期格式错误，应为 YYYY-MM-DD" % (label, value)]
    return None


def check_terminal_transition(old_stage, new_stage):
    """终态不回退：原阶段已是终态时禁止再改阶段。

    终态记录仍可更新备注等其他字段（挂了之后仍想记一句话），
    但「当前阶段」一旦落入终态即锁定。返回错误列表，空列表表示通过。
    """
    if not old_stage or not new_stage:
        return []
    if old_stage in TERMINAL_STAGES and new_stage != old_stage:
        return ["记录已处于终态 `%s`，不能再改阶段（如需重新投递，请新建一条记录）" % old_stage]
    return []


def check_reason_required(stage, reason):
    """终态必填原因：阶段属终态而原因为空则报错。正常流转阶段选填。"""
    if stage in TERMINAL_STAGES and not (reason or "").strip():
        return ["进入终态 `%s` 时必须填写「状态原因」" % stage]
    return []


def find_duplicate(rows, company, role):
    """canonical 去重：按 (公司, 岗位) trim + 大小写不敏感匹配。

    返回 (既有行, 该行是否终态)；找不到返回 (None, False)。
    调用方据此决定：非终态则拒绝（409），终态则放行（允许挂了之后再投一次）。
    """
    c = (company or "").strip().lower()
    r = (role or "").strip().lower()
    if not c or not r:
        return None, False
    for row in rows:
        if ((row.get("公司") or "").strip().lower() == c
                and (row.get("岗位") or "").strip().lower() == r):
            return row, (row.get("当前阶段") or "") in TERMINAL_STAGES
    return None, False


def cmd_add(args):
    errors = []

    if not args.company:
        errors.append("`--company` 不能为空")
    if not args.role:
        errors.append("`--role` 不能为空")

    errs = check_direction(args.direction)
    if errs:
        errors.extend(errs)
    if args.batch not in BATCHES:
        errors.append("`--batch` 必须是 %s 之一，实际为 `%s`" % ("/".join(BATCHES), args.batch))
    if args.source and args.source not in SOURCES:
        errors.append("`--source` 必须是 %s 之一，实际为 `%s`" % ("/".join(SOURCES), args.source))

    if args.stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一，实际为 `%s`"
                      % ("/".join(STAGES + TERMINAL_STAGES), args.stage))

    for value, label in ((args.deadline, "截止日期"),
                         (args.applied, "投递日期"),
                         (args.next_date, "下次动作日期")):
        errs = check_date(value, label)
        if errs:
            errors.extend(errs)

    if args.score is not None:
        if not (0 <= args.score <= 100):
            errors.append("`--score` 必须在 0–100 之间，实际为 %d" % args.score)

    # 终态必须填原因
    errors.extend(check_reason_required(args.stage, args.reason))

    rows = read_rows()

    # canonical 去重：同公司+岗位且既有记录非终态则拒绝
    dup, dup_is_terminal = find_duplicate(rows, args.company, args.role)
    if dup and not dup_is_terminal:
        errors.append("已存在相同公司+岗位的记录 `%s`（当前阶段：%s），请勿重复录入"
                      % (dup.get("id", ""), dup.get("当前阶段", "")))

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    new_id = next_id(rows)
    row = {field: "" for field in FIELDS}
    row.update({
        "id": new_id,
        "公司": args.company,
        "岗位": args.role,
        "方向": args.direction,
        "批次": args.batch,
        "来源": args.source or "",
        "截止日期": args.deadline or "",
        "投递日期": args.applied or "",
        "当前阶段": args.stage,
        "状态原因": args.reason or "",
        "下次动作": args.next or "",
        "下次动作日期": args.next_date or "",
        "简历版本": args.resume or "",
        "评分": "" if args.score is None else str(args.score),
        "归档目录": args.archive or "",
        "备注": args.note or "",
    })
    rows.append(row)
    write_rows(rows)
    # 时间线：新建也入账，作为停留天数与首次活动的基准
    append_history([{"id": new_id, "字段": "创建", "原值": "",
                     "新值": "%s %s（%s）" % (args.company, args.role, args.stage)}])

    print("## 已写入\n")
    print("| 字段 | 值 |")
    print("|---|---|")
    for field in FIELDS:
        if row[field]:
            print("| %s | %s |" % (field, row[field]))
    print("\n归档目录建议：`05_投递追踪/applications/%s_%s`" % (args.company, args.role))
    return 0


def cmd_update(args):
    rows = read_rows()
    target = None
    for row in rows:
        if (row.get("id") or "").strip() == args.id:
            target = row
            break

    if target is None:
        print("错误：找不到 id 为 `%s` 的记录" % args.id)
        return 1

    errors = []
    if args.stage and args.stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一" % "/".join(STAGES + TERMINAL_STAGES))
    if args.score is not None and not (0 <= args.score <= 100):
        errors.append("`--score` 必须在 0–100 之间")
    for value, label in ((args.next_date, "下次动作日期"),
                         (args.applied, "投递日期"),
                         (args.deadline, "截止日期")):
        errs = check_date(value, label)
        if errs:
            errors.extend(errs)

    # 终态不回退：原阶段已是终态时不可再改阶段
    if args.stage:
        errors.extend(check_terminal_transition(target.get("当前阶段", ""), args.stage))

    # 终态必填原因：按更新后的最终阶段与最终原因判定
    final_stage = args.stage or target.get("当前阶段", "")
    final_reason = args.reason if args.reason is not None else target.get("状态原因", "")
    errors.extend(check_reason_required(final_stage, final_reason))

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    changes = []
    before = dict(target)
    mapping = [
        ("当前阶段", args.stage), ("状态原因", args.reason), ("下次动作", args.next),
        ("下次动作日期", args.next_date), ("备注", args.note),
        ("投递日期", args.applied), ("截止日期", args.deadline),
    ]
    for field, value in mapping:
        if value is not None:
            old = target.get(field, "")
            target[field] = value
            changes.append("| %s | %s | %s |" % (field, old or "（空）", value or "（空）"))
    if args.score is not None:
        old = target.get("评分", "")
        target["评分"] = str(args.score)
        changes.append("| 评分 | %s | %d |" % (old or "（空）", args.score))

    if not changes:
        print("没有提供任何要更新的字段。可更新字段：%s" % "、".join(UPDATABLE))
        return 1

    write_rows(rows)
    append_history(diff_entries(args.id, before, target))
    print("## 已更新 %s（%s %s）\n" % (args.id, target.get("公司", ""), target.get("岗位", "")))
    print("| 字段 | 原值 | 新值 |")
    print("|---|---|---|")
    for line in changes:
        print(line)
    return 0


def format_table(rows):
    if not rows:
        return "（无匹配记录）"
    lines = []
    header = ["id", "公司", "岗位", "方向", "批次", "当前阶段", "截止日期", "下次动作", "下次动作日期", "评分"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        lines.append("| " + " | ".join(
            (row.get(h) or "") for h in header
        ) + " |")
    return "\n".join(lines)


def filter_rows(rows, args):
    result = rows
    if getattr(args, "stage", None):
        result = [r for r in result if r.get("当前阶段") == args.stage]
    if getattr(args, "direction", None):
        result = [r for r in result if r.get("方向") == args.direction]
    if getattr(args, "batch", None):
        result = [r for r in result if r.get("批次") == args.batch]
    if getattr(args, "company", None):
        result = [r for r in result if args.company in (r.get("公司") or "")]
    return result


def sort_key(row):
    """活跃记录在前、终态在后；按下次动作日期升序，空日期排最后。

    提升为模块级函数，供 CLI 与 Web 共用同一排序规则——
    两处各写一份迟早会不一致。
    """
    terminal = 1 if row.get("当前阶段") in TERMINAL_STAGES else 0
    nd = (row.get("下次动作日期") or "").strip()
    return (terminal, "9999" if not nd else nd, row.get("id", ""))


def cmd_list(args):
    if getattr(args, "direction", None):
        errs = check_direction(args.direction)
        if errs:
            print("## 校验失败\n")
            for e in errs:
                print("- %s" % e)
            return 1

    rows = read_rows()
    if not rows:
        print("追踪表为空。用 `tracker.py add` 添加第一条记录。")
        return 0

    result = filter_rows(rows, args)

    due_within = getattr(args, "due_within", None)
    if due_within is not None:
        from datetime import date, timedelta
        today = date.today()
        limit = today + timedelta(days=due_within)
        kept = []
        for r in result:
            for field in ("下次动作日期", "截止日期"):
                raw = (r.get(field) or "").strip()
                if DATE_RE.match(raw):
                    y, m, d = (int(x) for x in raw.split("-"))
                    if today <= date(y, m, d) <= limit:
                        kept.append(r)
                        break
        result = kept

    result.sort(key=sort_key)

    print("## 共 %d 条（总记录 %d 条）\n" % (len(result), len(rows)))
    print(format_table(result))
    return 0


def cmd_show(args):
    rows = read_rows()
    for row in rows:
        if (row.get("id") or "").strip() == args.id:
            print("## %s %s（%s）\n" % (row.get("公司", ""), row.get("岗位", ""), args.id))
            print("| 字段 | 值 |")
            print("|---|---|")
            for field in FIELDS:
                print("| %s | %s |" % (field, row.get(field, "") or "（空）"))
            return 0
    print("错误：找不到 id 为 `%s` 的记录" % args.id)
    return 1


def cmd_history(args):
    entries = read_history(app_id=args.id)
    if not entries:
        print("（暂无变更记录%s）" % ("：%s" % args.id if args.id else ""))
        return 0

    # 倒序展示：最近的变更在最上面
    entries = list(reversed(entries))
    if args.limit and args.limit > 0:
        entries = entries[:args.limit]

    print("## 变更时间线（共 %d 条）\n" % len(entries))
    print("| 时间 | id | 字段 | 原值 | 新值 |")
    print("|---|---|---|---|---|")
    for e in entries:
        print("| %s | %s | %s | %s | %s |" % (
            e.get("时间", ""), e.get("id", ""), e.get("字段", ""),
            e.get("原值", "") or "（空）", e.get("新值", "") or "（空）"))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="投递追踪表增删查改")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="新增投递记录")
    p_add.add_argument("--company", required=True, help="公司")
    p_add.add_argument("--role", required=True, help="岗位")
    # 不在 argparse 层写死 choices：合法方向取决于工作区装入的插件，
    # 交给 check_direction() 在运行时校验，才能给出「可用方向」的具体提示
    p_add.add_argument("--direction", required=True, help="方向 ID，取决于装入的领域插件")
    p_add.add_argument("--batch", required=True, choices=BATCHES, help="批次")
    p_add.add_argument("--source", choices=SOURCES, help="来源")
    p_add.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_add.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_add.add_argument("--stage", default="待投", help="当前阶段")
    p_add.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_add.add_argument("--next", dest="next", help="下次动作")
    p_add.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_add.add_argument("--resume", help="简历版本")
    p_add.add_argument("--score", type=int, help="评分 0-100")
    p_add.add_argument("--archive", help="归档目录相对路径")
    p_add.add_argument("--note", help="备注")

    p_upd = sub.add_parser("update", help="更新记录")
    p_upd.add_argument("--id", required=True, help="记录 id，如 A001")
    p_upd.add_argument("--stage", help="当前阶段")
    p_upd.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_upd.add_argument("--next", dest="next", help="下次动作")
    p_upd.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_upd.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_upd.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_upd.add_argument("--note", help="备注")
    p_upd.add_argument("--score", type=int, help="评分 0-100")

    # 方向选项取决于工作区装入的插件，此处不在定义时写死，
    # 改为在 cmd_list 中校验，以便给出「可用方向」的具体提示
    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--stage", help="按阶段过滤")
    p_list.add_argument("--direction", help="按方向过滤")
    p_list.add_argument("--batch", choices=BATCHES, help="按批次过滤")
    p_list.add_argument("--company", help="按公司名模糊过滤")
    p_list.add_argument("--due-within", dest="due_within", type=int,
                        help="只看未来 N 天内到期（下次动作日期或截止日期）")

    p_show = sub.add_parser("show", help="查看单条记录")
    p_show.add_argument("--id", required=True, help="记录 id")

    p_hist = sub.add_parser("history", help="查看变更时间线")
    p_hist.add_argument("--id", help="只看某条记录，省略则看全部")
    p_hist.add_argument("--limit", type=int, help="只显示最近 N 条")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    global WORKSPACE
    WORKSPACE = os.path.abspath(args.workspace)
    if not os.path.isdir(WORKSPACE):
        print("错误：工作区不存在 %s" % WORKSPACE)
        print("先运行 python tools/init_workspace.py 初始化。")
        return 1

    if not args.cmd:
        parser.print_help()
        return 1

    handlers = {
        "add": cmd_add,
        "update": cmd_update,
        "list": cmd_list,
        "show": cmd_show,
        "history": cmd_history,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
