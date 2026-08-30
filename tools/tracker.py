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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "05_投递追踪", "tracker.csv")

# 输出时保持固定字段顺序
FIELDS = [
    "id", "公司", "岗位", "方向", "批次", "来源", "截止日期", "投递日期",
    "当前阶段", "下次动作", "下次动作日期", "简历版本", "评分", "归档目录", "备注",
]

DIRECTIONS = ["datacenter", "hvac", "other"]
BATCHES = ["提前批", "正式批", "补录"]
SOURCES = ["应届生求职网", "牛客", "企业校招官网", "学校就业网", "内推", "其他"]

# 正常流转顺序；终态单独处理
STAGES = ["待投", "已投", "笔试", "一面", "二面", "三面", "HR面", "offer", "签约"]
TERMINAL_STAGES = ["已挂", "已放弃"]

# update 只允许改这五项，公司与岗位不可改（改则需新建记录并作废原记录）
UPDATABLE = ["当前阶段", "下次动作", "下次动作日期", "备注", "评分", "投递日期", "截止日期"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_rows():
    if not os.path.isfile(CSV_PATH):
        return []
    # utf-8-sig 读取时自动去掉 BOM
    with io.open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def write_rows(rows):
    directory = os.path.dirname(CSV_PATH)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    # utf-8-sig 写入时加 BOM，Excel 直接打开不乱码
    with io.open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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


def cmd_add(args):
    errors = []

    if not args.company:
        errors.append("`--company` 不能为空")
    if not args.role:
        errors.append("`--role` 不能为空")

    if args.direction not in DIRECTIONS:
        errors.append("`--direction` 必须是 %s 之一，实际为 `%s`" % ("/".join(DIRECTIONS), args.direction))
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

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    rows = read_rows()
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
        "下次动作": args.next or "",
        "下次动作日期": args.next_date or "",
        "简历版本": args.resume or "",
        "评分": "" if args.score is None else str(args.score),
        "归档目录": args.archive or "",
        "备注": args.note or "",
    })
    rows.append(row)
    write_rows(rows)

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

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    changes = []
    mapping = [
        ("当前阶段", args.stage), ("下次动作", args.next),
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


def cmd_list(args):
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

    # 活跃记录在前，终态在后；按下次动作日期升序，空日期排最后
    def sort_key(r):
        terminal = 1 if r.get("当前阶段") in TERMINAL_STAGES else 0
        nd = (r.get("下次动作日期") or "").strip()
        return (terminal, "9999" if not nd else nd, r.get("id", ""))

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


def build_parser():
    parser = argparse.ArgumentParser(description="投递追踪表增删查改")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="新增投递记录")
    p_add.add_argument("--company", required=True, help="公司")
    p_add.add_argument("--role", required=True, help="岗位")
    p_add.add_argument("--direction", required=True, choices=DIRECTIONS, help="方向")
    p_add.add_argument("--batch", required=True, choices=BATCHES, help="批次")
    p_add.add_argument("--source", choices=SOURCES, help="来源")
    p_add.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_add.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_add.add_argument("--stage", default="待投", help="当前阶段")
    p_add.add_argument("--next", dest="next", help="下次动作")
    p_add.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_add.add_argument("--resume", help="简历版本")
    p_add.add_argument("--score", type=int, help="评分 0-100")
    p_add.add_argument("--archive", help="归档目录相对路径")
    p_add.add_argument("--note", help="备注")

    p_upd = sub.add_parser("update", help="更新记录")
    p_upd.add_argument("--id", required=True, help="记录 id，如 A001")
    p_upd.add_argument("--stage", help="当前阶段")
    p_upd.add_argument("--next", dest="next", help="下次动作")
    p_upd.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_upd.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_upd.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_upd.add_argument("--note", help="备注")
    p_upd.add_argument("--score", type=int, help="评分 0-100")

    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--stage", help="按阶段过滤")
    p_list.add_argument("--direction", choices=DIRECTIONS, help="按方向过滤")
    p_list.add_argument("--batch", choices=BATCHES, help="按批次过滤")
    p_list.add_argument("--company", help="按公司名模糊过滤")
    p_list.add_argument("--due-within", dest="due_within", type=int,
                        help="只看未来 N 天内到期（下次动作日期或截止日期）")

    p_show = sub.add_parser("show", help="查看单条记录")
    p_show.add_argument("--id", required=True, help="记录 id")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return 1

    handlers = {
        "add": cmd_add,
        "update": cmd_update,
        "list": cmd_list,
        "show": cmd_show,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
