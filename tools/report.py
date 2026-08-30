# -*- coding: utf-8 -*-
"""由投递追踪表生成 Markdown 漏斗看板。

用法：
    python tools/report.py
    python tools/report.py --out 05_投递追踪/看板.md
    python tools/report.py --stdout          # 只打印，不写文件

看板包含五部分：投递漏斗、按方向统计、按批次统计、近 7 天待办、已过截止日提醒。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys
from datetime import date, timedelta

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tracker import (  # noqa: E402 - 需先设置 sys.path
    DEFAULT_WORKSPACE, ROOT, STAGES, TERMINAL_STAGES,
    csv_path, read_rows, set_workspace,
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 漏斗顺序：正常流转 + 终态
FUNNEL_ORDER = STAGES + TERMINAL_STAGES


def parse_date(value):
    if value and DATE_RE.match(value.strip()):
        y, m, d = (int(x) for x in value.strip().split("-"))
        return date(y, m, d)
    return None


def count_by(rows, field, order=None):
    counts = {}
    for row in rows:
        key = (row.get(field) or "（空）").strip()
        counts[key] = counts.get(key, 0) + 1
    if order:
        ordered = [(k, counts[k]) for k in order if k in counts]
        rest = [(k, v) for k, v in counts.items() if k not in order]
        rest.sort(key=lambda kv: (-kv[1], kv[0]))
        return ordered + rest
    result = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return result


def build_report(rows, today):
    lines = []
    total = len(rows)

    lines.append("# 投递看板")
    lines.append("")
    lines.append("> 生成日期：%s　总记录：%d 条" % (today.isoformat(), total))
    lines.append("")
    lines.append("数据源：`05_投递追踪/tracker.csv`")
    lines.append("")

    if not rows:
        lines.append("追踪表为空。先用 `/jd` 解析岗位，再用 `/apply` 生成投递包。")
        return "\n".join(lines) + "\n"

    # 一、投递漏斗
    lines.append("## 一、投递漏斗")
    lines.append("")
    lines.append("| 阶段 | 数量 | 占比 |")
    lines.append("|---|---:|---:|")
    funnel = count_by(rows, "当前阶段", FUNNEL_ORDER)
    for stage, count in funnel:
        pct = count * 100.0 / total
        bar = "#" * int(round(pct / 5))
        lines.append("| %s | %d | %.0f%% %s |" % (stage, count, pct, bar))
    lines.append("")

    active = sum(1 for r in rows if r.get("当前阶段") not in TERMINAL_STAGES)
    terminal = total - active
    lines.append("在流程中 %d 条，已结束 %d 条。" % (active, terminal))
    lines.append("")

    # 二、按方向
    lines.append("## 二、按方向")
    lines.append("")
    lines.append("| 方向 | 数量 |")
    lines.append("|---|---:|")
    for key, count in count_by(rows, "方向"):
        lines.append("| %s | %d |" % (key, count))
    lines.append("")

    # 三、按批次
    lines.append("## 三、按批次")
    lines.append("")
    lines.append("| 批次 | 数量 |")
    lines.append("|---|---:|")
    for key, count in count_by(rows, "批次"):
        lines.append("| %s | %d |" % (key, count))
    lines.append("")

    # 四、近 7 天待办
    lines.append("## 四、近 7 天待办")
    lines.append("")
    limit = today + timedelta(days=7)
    todo = []
    for row in rows:
        if row.get("当前阶段") in TERMINAL_STAGES:
            continue
        nd = parse_date(row.get("下次动作日期"))
        dl = parse_date(row.get("截止日期"))
        soonest = None
        reason = ""
        if nd and today <= nd <= limit:
            soonest, reason = nd, "下次动作"
        elif dl and today <= dl <= limit:
            soonest, reason = dl, "截止"
        if soonest:
            todo.append((soonest, row, reason))
    todo.sort(key=lambda t: (t[0], t[1].get("id", "")))

    if todo:
        lines.append("| 日期 | id | 公司 | 岗位 | 事项 | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        for when, row, reason in todo:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                when.isoformat(),
                row.get("id", ""),
                row.get("公司", ""),
                row.get("岗位", ""),
                reason,
                row.get("下次动作", "") or "",
            ))
    else:
        lines.append("未来 7 天没有到期事项。")
    lines.append("")

    # 五、已过截止日提醒
    lines.append("## 五、已过截止日提醒")
    lines.append("")
    overdue = []
    for row in rows:
        if row.get("当前阶段") in TERMINAL_STAGES:
            continue
        if row.get("当前阶段") != "待投":
            continue
        dl = parse_date(row.get("截止日期"))
        if dl and dl < today:
            overdue.append((dl, row))
    overdue.sort(key=lambda t: t[0])

    if overdue:
        lines.append("| 截止日期 | id | 公司 | 岗位 | 阶段 |")
        lines.append("|---|---|---|---|---|")
        for dl, row in overdue:
            lines.append("| %s | %s | %s | %s | %s |" % (
                dl.isoformat(), row.get("id", ""), row.get("公司", ""),
                row.get("岗位", ""), row.get("当前阶段", ""),
            ))
        lines.append("")
        lines.append("以上记录仍处于「待投」但已过截止日，确认是否放弃或更新状态。")
    else:
        lines.append("无已过截止日且未投递的记录。")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成投递漏斗看板")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    parser.add_argument("--out", help="输出文件路径，默认工作区下 05_投递追踪/看板.md")
    parser.add_argument("--stdout", action="store_true", help="只打印到标准输出，不写文件")
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    if not os.path.isdir(workspace):
        print("错误：工作区不存在 %s" % workspace)
        print("先运行 python tools/init_workspace.py 初始化。")
        return 1
    set_workspace(workspace)

    if not os.path.isfile(csv_path()):
        print("追踪表尚未创建，无数据可生成看板。")
        print("先用 jd 工作流解析岗位，再用 apply 工作流生成投递包，追踪表会自动建立。")
        return 0

    rows = read_rows()
    content = build_report(rows, date.today())

    if args.stdout:
        print(content)
        return 0

    out_path = os.path.abspath(args.out) if args.out else os.path.join(
        workspace, "05_投递追踪", "看板.md")
    directory = os.path.dirname(out_path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    print("已生成看板：%s" % os.path.relpath(out_path, ROOT))
    print("共 %d 条记录。" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
