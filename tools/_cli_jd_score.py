# -*- coding: utf-8 -*-
"""`jobws jd` 的命令层：解析参数、校验解析卡、输出档位与差距清单。

（2026-09-21 从 `jobws_core.jd_score` 拆出：领域层不 import argparse——后端与
将来进包的版本都只需要解析与评分函数，命令行是仓库侧的事。命令名与参数逐字未变。）
退出码：0 成功 / 1 校验失败或文件错误 / 2 用法错误。
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from jobws_core.jd_score import (DEFAULT_WORKSPACE, DIMENSIONS, TOTAL_MAX,  # noqa: E402
                                 gap_analysis, parse_dimension,
                                 parse_score_section, resolve_profile, verdict)


def _build_parser():
    parser = argparse.ArgumentParser(description="校验 JD 解析卡评分并输出结论档位")
    # --show-profile 只查插件路径，不需要解析卡，故设为可选
    parser.add_argument("card", nargs="?", help="解析卡路径")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    parser.add_argument("--domain", help="领域插件 ID，如 hvac-cooling")
    parser.add_argument("--direction", help="方向 ID，如 datacenter / hvac")
    parser.add_argument("--show-profile", action="store_true",
                        help="打印命中的插件与方向文件路径后退出")
    parser.add_argument("--gap", action="store_true",
                        help="输出 JD↔简历差距清单（需配合 --resume）")
    parser.add_argument("--resume", help="简历版本（source/resume_<版本>.json 的版本名）")
    return parser


def _run_show_profile(workspace, args):
    """--show-profile：只打印命中的插件与方向文件路径。"""
    profile_dir, direction_file, warns = resolve_profile(
        workspace, args.domain, args.direction)
    print("插件目录：%s" % (profile_dir or "（未找到）"))
    print("方向文件：%s" % (direction_file or "（未找到）"))
    print("共用词典：%s" % (os.path.join(profile_dir, "lexicon.md")
                       if profile_dir else "（未找到）"))
    for w in warns:
        print("提示：%s" % w)
    return 0 if profile_dir and direction_file else 1


def _run_gap(workspace, args):
    """--gap：JD↔简历差距清单（母版召回 / 真实缺口二分）。"""
    if not args.resume:
        print("错误：--gap 需要配合 --resume <版本>")
        return 1
    result, errs = gap_analysis(workspace, args.card, args.resume,
                                args.domain, args.direction)
    for e in errs:
        print("提示：%s" % e)
    if result is None:
        return 1
    print("JD：%s" % result["jd"])
    print("简历：%s" % result["resume"])
    print("词典：%s" % result["lexicon"])
    print("")
    print("## 已覆盖（%d）" % result["counts"]["matched"])
    for item in result["matchedDetail"]:
        print("  - %s（%s）" % (item["term"], item["level"]))
    print("")
    print("## 可召回（%d）—— 母版里有，这一版没用上" % result["counts"]["injectable"])
    for item in result["injectableDetail"]:
        print("  - %s（%s）" % (item["term"], item["level"]))
    print("")
    print("## 真实缺口（%d）—— 简历与母版都没有，需评估是否补经历" % result["counts"]["missing"])
    for item in result["missingDetail"]:
        print("  - %s（%s）" % (item["term"], item["level"]))
    return 0


def _validate_card(fields):
    """维度与总分校验；返回 (values, total, errors)。"""
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
    return values, total, errors


def _print_verdict(values, total):
    """输出结论：评分明细表 + 档位与下一步。"""
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


def main():
    parser = _build_parser()
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)

    if not args.card and not args.show_profile:
        parser.error("需要提供解析卡路径，或使用 --show-profile")

    if args.show_profile:
        return _run_show_profile(workspace, args)

    path = args.card
    if not os.path.isfile(path):
        print("错误：找不到解析卡 `%s`" % path)
        return 1

    if args.gap:
        return _run_gap(workspace, args)

    with io.open(path, "r", encoding="utf-8") as f:
        text = f.read()

    fields = parse_score_section(text)
    if not fields:
        print("错误：解析卡中找不到 `## 评分` 小节，或其下没有 `key: value` 行")
        return 1

    values, total, errors = _validate_card(fields)
    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n请修正解析卡的 `## 评分` 小节后重新运行。")
        return 1

    _print_verdict(values, total)
    return 0


if __name__ == "__main__":
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py jd ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
