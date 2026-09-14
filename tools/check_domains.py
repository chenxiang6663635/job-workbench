# -*- coding: utf-8 -*-
"""领域插件合规校验的**唯一**实现。

为什么是唯一实现：与 check_skills 同一条纪律——校验口径只写一处，CI、本地
自查、文档里的「契约」都指向它；分叉掉的那一半正好就是没拦住的那一半。

校验项（每项都对应一个真实发生过、或高度可能的后果）：
  1. 目录 ID 合规（小写字母/数字/连字符）——ID 会被 `init --domain` 与
     `resolve_profile` 当查找键；含大写时 Windows 上碰巧能用、CI（Linux）上
     「找不到插件」，而开发机永远看不到这个错。
  2. 必备结构齐全：`profile.md` / `lexicon.md` / `failure_keywords.txt` /
     `directions/`（至少一个方向）——init 把它们整树复制进工作区 `config/`，
     缺任何一件都是**静默降级**（评分没有词表、复盘没有聚类表，都不报错）。
  3. `lexicon.md` 可被 `jd_score.parse_lexicon` 解析且三层（Primary /
     Secondary / Weak）都有词条——**复用评分侧解析器**：这里解析得出来，
     评分现场就不会「词典为空」。
  4. `failure_keywords.txt` 每行是 `类别=词1,词2`（注释与空行除外）——
     格式错的行会被复盘侧静默忽略，等于这条归因口径不存在。
  5. `profile.md` 的 `| 插件 ID |` 与目录名一致——照 check_skills 的
     name==目录名：身份两处不一致时，贡献者以为装的是 A、运行的是 B。
  6. `directions/` 下至少一个非空 .md——空方向文件会让方向锚点缺位。

用法（入口已统一，见 tools/jobws.py）：
    python tools/jobws.py lint domains                 # 校验仓库 template/profiles/
    python tools/jobws.py lint domains --root <dir>    # 校验指定目录
退出码：0 全部合规，1 存在问题，2 目录不存在。
"""

from __future__ import print_function

import argparse
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import jd_score  # noqa: E402  # 复用词典解析器（唯一实现）；jd_score 只用标准库

DOMAIN_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REQUIRED_FILES = ["profile.md", "lexicon.md", "failure_keywords.txt"]


def _read(path):
    """utf-8-sig + replace 的同款理由见 check_skills：BOM 与坏字节都不该让校验器崩。"""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _check_lexicon(path):
    """返回问题清单（空 = OK）。复用 jd_score 的解析器：这里解析得出来，现场就解析得出来。"""
    entries = jd_score.parse_lexicon(path)
    if not entries:
        return ["lexicon.md 解析不出任何词条——评分会因「词典为空」拒绝出结论"]
    problems = []
    levels = set(level for _term, level in entries)
    for name in jd_score.LEXICON_LEVELS:
        if name not in levels:
            problems.append(
                "lexicon.md 缺少 `%s` 层的词条——评分词典要求三层都有（缺层不报错，"
                "只是该层的词永远匹配不到）" % name)
    return problems


def _check_failure_keywords(path):
    problems = []
    for number, line in enumerate(_read(path).splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            problems.append("failure_keywords.txt 第 %d 行不是「类别=词1,词2」：%s"
                            % (number, stripped))
            continue
        category, _, words = stripped.partition("=")
        if not category.strip() or not words.strip():
            problems.append("failure_keywords.txt 第 %d 行 `=` 两侧都要有内容：%s"
                            % (number, stripped))
            continue
        # 消费端（report 的聚类）按逗号分词后会丢弃空词——`类别=,,,` 在校验层
        # 看着"有内容"、到复盘侧却是空类别（跨宿主审查 MINOR，2026-09-14）。
        if not any(part.strip() for part in words.split(",")):
            problems.append("failure_keywords.txt 第 %d 行没有任何有效关键词（只有逗号）：%s"
                            % (number, stripped))
    return problems


def inspect_domains(profiles_root):
    """扫描 profiles_root 下每个领域插件，返回每项的问题清单。

    返回项形如 {"dir": str, "problems": [str]}，problems 为空即合规。
    """
    results = []
    if not os.path.isdir(profiles_root):
        return results

    for entry in sorted(os.listdir(profiles_root)):
        path = os.path.join(profiles_root, entry)
        if not os.path.isdir(path):
            continue

        item = {"dir": entry, "problems": []}
        problems = item["problems"]

        if not DOMAIN_ID_RE.match(entry):
            problems.append(
                "目录 ID 不合规（要求小写字母/数字/连字符，如 hvac-cooling）——"
                "ID 会被 init --domain 与 resolve_profile 当查找键；含大写时 "
                "Windows 上能用、Linux/CI 上会报「找不到插件」")

        for name in REQUIRED_FILES:
            if not os.path.isfile(os.path.join(path, name)):
                problems.append("缺少 %s（init 会把它装进工作区 config/）" % name)

        directions = os.path.join(path, "directions")
        if not os.path.isdir(directions):
            problems.append("缺少 directions/ 目录（至少一个方向文件）")
        else:
            md_files = [name for name in sorted(os.listdir(directions))
                        if name.endswith(".md")
                        and os.path.isfile(os.path.join(directions, name))]
            if not md_files:
                problems.append("directions/ 下没有 .md 方向文件")
            for name in md_files:
                if not _read(os.path.join(directions, name)).strip():
                    problems.append("directions/%s 是空文件——方向锚点缺位" % name)

        lexicon = os.path.join(path, "lexicon.md")
        if os.path.isfile(lexicon):
            problems.extend(_check_lexicon(lexicon))

        keywords = os.path.join(path, "failure_keywords.txt")
        if os.path.isfile(keywords):
            problems.extend(_check_failure_keywords(keywords))

        profile = os.path.join(path, "profile.md")
        if os.path.isfile(profile):
            match = re.search(r"\|\s*插件 ID\s*\|\s*`?([^`|\s]+)`?\s*\|", _read(profile))
            if not match:
                problems.append("profile.md 缺 `| 插件 ID | <id> |` 行（身份表）")
            elif match.group(1) != entry:
                problems.append(
                    "profile.md 的插件 ID（%s）与目录名（%s）不一致——身份要求两者相同"
                    % (match.group(1), entry))

        results.append(item)

    return results


def describe(results):
    """把结果渲染成人能读的文本（CI 日志与本地自查共用）。"""
    lines = []
    total = len(results)
    bad = [r for r in results if r["problems"]]
    lines.append("已检查 %d 个领域插件，%d 个不合规。" % (total, len(bad)))
    for item in results:
        if not item["problems"]:
            continue
        lines.append("")
        lines.append("  [%s]" % item["dir"])
        for problem in item["problems"]:
            lines.append("    - %s" % problem)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="校验领域插件是否合规")
    parser.add_argument("--root", default=None,
                        help="插件目录，默认仓库 template/profiles/")
    args = parser.parse_args()

    root = args.root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "template", "profiles")
    if not os.path.isdir(root):
        print("错误：找不到领域插件目录 %s" % root)
        return 2

    results = inspect_domains(root)
    print(describe(results))
    if any(item["problems"] for item in results):
        print("")
        print("贡献契约见 docs/domain-contract.md；修复后再提交。")
        return 1
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py（同 check_skills 的处理）
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py lint domains ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
