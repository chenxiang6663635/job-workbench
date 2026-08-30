# -*- coding: utf-8 -*-
"""校验 JD 解析卡的评分小节是否自洽，并按阈值输出结论档位。

本脚本不打分——评分由 AI 读 JD 原文与 CODEBUDDY.md 后填进解析卡。
脚本只做三件事：校验各维度分子不超过分母、校验四项之和等于总分、套阈值出档位。
这样设计是为了让评分标准可改在 Markdown 里，改完可以对历史 JD 批量重算。

用法：
    python tools/jd_score.py <解析卡路径>
    python tools/jd_score.py 01_岗位池/某某公司_某岗位/解析卡.md

退出码：0 成功，1 校验失败或文件错误。
输出到 stdout 的是 Markdown 片段，供命令直接回填解析卡的「结论」小节。
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

# 维度名 -> 满分。顺序即解析卡中的书写顺序
DIMENSIONS = [
    ("技术匹配", 30),
    ("经历匹配", 25),
    ("方向契合", 30),
    ("培养与稳定性", 15),
]

# (下界, 上界, 档位, 动作)
THRESHOLDS = [
    (75, 100, "强烈建议投", "立即执行 /apply 生成投递包"),
    (60, 74, "建议投", "执行 /apply 生成投递包"),
    (45, 59, "斟酌", "先看关键缺口能否在一周内补齐，再决定是否投递"),
    (30, 44, "大概率跳过", "除非有内推或岗位调整等额外信息，否则不投"),
    (0, 29, "不投", "终止，不生成任何材料"),
]

TOTAL_MAX = sum(m for _, m in DIMENSIONS)

FIELD_RE = re.compile(r"^\s*(?P<key>[^:：]+)\s*[:：]\s*(?P<value>.*?)\s*$")


def parse_score_section(text):
    """提取 ## 评分 小节中的 key: value 行，返回 dict。"""
    lines = text.splitlines()
    in_section = False
    result = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            # 遇到下一个二级标题即退出评分小节
            if in_section:
                break
            if stripped.replace(" ", "").startswith("##评分"):
                in_section = True
            continue
        if not in_section:
            continue

        m = FIELD_RE.match(line)
        if m:
            result[m.group("key").strip()] = m.group("value").strip()

    return result


def parse_dimension(raw, name, maximum):
    """解析 `24/30` 形式的取值，返回 (分子, 错误列表)。"""
    errors = []
    if not raw:
        return None, ["`%s` 未填写" % name]

    m = re.match(r"^(?P<num>\d+(?:\.\d+)?)\s*/\s*(?P<den>\d+)$", raw)
    if not m:
        return None, ["`%s: %s` 格式错误，应为 `分子/%d` 形式，如 `24/%d`" % (name, raw, maximum, maximum)]

    num = float(m.group("num"))
    den = int(m.group("den"))

    if den != maximum:
        errors.append("`%s` 分母应为 %d，实际为 %d" % (name, maximum, den))
    if num > maximum:
        errors.append("`%s` 分子 %g 超过满分 %d" % (name, num, maximum))
    if num < 0:
        errors.append("`%s` 分子不能为负" % name)

    return num, errors


def verdict(total):
    for low, high, level, action in THRESHOLDS:
        if low <= total <= high:
            return level, action
    return THRESHOLDS[-1][2], THRESHOLDS[-1][3]


def main():
    parser = argparse.ArgumentParser(description="校验 JD 解析卡评分并输出结论档位")
    parser.add_argument("card", help="解析卡路径")
    parser.add_argument("--quiet", action="store_true", help="只输出结论，不输出评分明细")
    args = parser.parse_args()

    path = args.card
    if not os.path.isfile(path):
        print("错误：找不到解析卡 `%s`" % path)
        return 1

    with io.open(path, "r", encoding="utf-8") as f:
        text = f.read()

    fields = parse_score_section(text)

    if not fields:
        print("错误：解析卡中找不到 `## 评分` 小节，或其下没有 `key: value` 行")
        return 1

    errors = []
    values = {}
    for name, maximum in DIMENSIONS:
        raw = fields.get(name, "")
        num, errs = parse_dimension(raw, name, maximum)
        errors.extend(errs)
        if num is not None and not errs:
            values[name] = num

    # 总分校验
    total_raw = fields.get("总分", "")
    total = None
    if not total_raw:
        errors.append("`总分` 未填写")
    else:
        m = re.match(r"^\d+(?:\.\d+)?$", total_raw)
        if not m:
            errors.append("`总分: %s` 格式错误，应为纯数字" % total_raw)
        else:
            total = float(total_raw)
            if total > TOTAL_MAX:
                errors.append("总分 %g 超过满分 %d" % (total, TOTAL_MAX))

    # 加总一致性：只在四个维度都成功解析时才校验
    if len(values) == len(DIMENSIONS) and total is not None:
        calc = sum(values.values())
        if abs(calc - total) > 1e-6:
            errors.append(
                "加总不一致：四项之和为 %g，但总分为 %g（差 %g）"
                % (calc, total, calc - total)
            )

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n请修正解析卡的 `## 评分` 小节后重新运行。")
        return 1

    # 输出结论
    level, action = verdict(total)

    print("## 评分明细\n")
    print("| 维度 | 得分 |")
    print("|---|---:|")
    for name, maximum in DIMENSIONS:
        print("| %s | %g / %d |" % (name, values[name], maximum))
    print("| **总分** | **%g / %d** |" % (total, TOTAL_MAX))
    print("")
    print("## 结论\n")
    print("- **档位**：%s" % level)
    print("- **下一步**：%s" % action)

    return 0


if __name__ == "__main__":
    sys.exit(main())
