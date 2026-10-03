#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""i18n 键健康门禁（issue #212）：死键检测 + 中英键集合对称。

为什么要有它（2026-10-02 实测）：`zh-CN.ts` 1509 行已越过 `check_size.py` 的
data 型上限 1500——新增文案键被迫挤占既有键（一个键承载两个语义）。行数不是
locale 的正确约束（声明式内容、随功能线性增长），**「有没有人用」才是**：本
检查器接管防膨胀职责，`check_size.py` 相应把 `i18n/locales/` 排除出扫描。

检测口径（每条都有实测依据，2026-10-02 校准）：
- **死键**：locale 定义、但引用语料里找不到引用的键；
- **引用语料跨端**（实测教训）：`mailProvider.*` 系列并非在前端被字面量引用，
  而是作为 **provider 元数据**里的字段值给出（后端 Python 侧）——只扫前端会
  把 13 个活键误判成死键。语料 = 前端 src/ + 前端 tests/ + 后端 Python
  （packages / tools / web/backend / mcp / scripts）;
- **模板键放过**（与 check_i18n_hardcode.py「带 ${} 的键跳过而非误报」同源）：
  ``t(`settings.reminderDays_${v}`)`` 之类静态不可判定——凡键落在某个模板
  前缀之下即放过，宁可漏报、不误报；
- **复数基名归并**：`x_one` / `x_other` 归到 `x`（i18next 复数机制，与
  check_i18n_hardcode.py 的 `_plural_bases` 同款）；
- **中英对称**：`zh-CN.ts` 与 `en.ts` 的键集合互差必须为空（逐**原键**比，
  不做复数归并——`x_one` 只在一侧出现本身就是漂移）。

用法：
    python tools/check_i18n_keys.py                 # 全量检查（CI / pre-commit）
    python tools/check_i18n_keys.py --root <dir>    # 指定仓库根（单测用）
    python tools/check_i18n_keys.py --list-dead     # 只列死键（人工清理用）
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOCALES_REL = os.path.join("web", "frontend", "src", "i18n", "locales")
SOURCE_LOCALE = "zh-CN.ts"
TARGET_LOCALE = "en.ts"

FRONTEND_RELS = (os.path.join("web", "frontend", "src"),
                 os.path.join("web", "frontend", "tests"))
PYTHON_RELS = ("packages", "tools", os.path.join("web", "backend"), "mcp", "scripts")

SKIP_DIRS = {"__pycache__", "node_modules", "dist", "build", "release", ".venv",
             "test-results", ".build", ".git"}

# locale 里的键行：`  "a.b": "文案",`（扁平字面量对象，与 hardcode 检查器同款）
KEY_LINE = re.compile(r'^\s*"([^"]+)":')
# 模板键前缀：`settings.reminderDays_${v}` / `drill.mode.${m}` —— 取到 ${ 之前
TEMPLATE_PREFIX = re.compile(r"`([A-Za-z0-9_.]+?)(?:[._])?\$\{")
# 拼接键前缀：`"settings.reminderDays_" + v` / `"drill.mode." + m`
CONCAT_PREFIX = re.compile(r"""['"]([A-Za-z0-9_.]+?)[._]['"]\s*\+""")

PLURAL_SUFFIXES = ("_one", "_other", "_few", "_many", "_zero", "_two")


def extract_keys(path):
    """locale 文件 → 原键列表（保序、含重复保护交给调用方 set）。"""
    keys = []
    with io.open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = KEY_LINE.match(line)
            if match:
                keys.append(match.group(1))
    return keys


def base_of(key):
    """复数基名归并：`x_one` → `x`；非复数键原样。"""
    for suffix in PLURAL_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def _read_text(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def build_corpus(root):
    """引用语料：前端 src/ + 前端 tests/ + 后端 Python——**排除 locale 自身**
    （否则每个键都能在 locale 文件里"命中"自己，检查器永远绿）。"""
    locales_abs = os.path.join(root, LOCALES_REL)
    parts = []

    for rel in FRONTEND_RELS:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if os.path.abspath(dirpath) == os.path.abspath(locales_abs):
                continue
            for name in sorted(filenames):
                if name.endswith((".ts", ".tsx")):
                    parts.append(_read_text(os.path.join(dirpath, name)))

    for rel in PYTHON_RELS:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if name.endswith(".py"):
                    parts.append(_read_text(os.path.join(dirpath, name)))

    return "\n".join(parts)


def extract_prefixes(corpus):
    """语料里出现过的模板键前缀 / 拼接键前缀（去重）。"""
    prefixes = set()
    for match in TEMPLATE_PREFIX.finditer(corpus):
        prefixes.add(match.group(1))
    for match in CONCAT_PREFIX.finditer(corpus):
        prefixes.add(match.group(1))
    return prefixes


def is_referenced(base, corpus, prefixes):
    """base（已归并复数）是否被引用：字面量命中，或落在某个模板前缀之下。"""
    if ('"%s"' % base) in corpus or ("'%s'" % base) in corpus or ("`%s`" % base) in corpus:
        return True
    for prefix in prefixes:
        if base == prefix or base.startswith(prefix + ".") or base.startswith(prefix + "_"):
            return True
    return False


def find_violations(root):
    """返回 (死键列表[原键], zh 独有, en 独有)；locale 缺失时抛 OSError 由调用方处理。"""
    locales = os.path.join(root, LOCALES_REL)
    source_path = os.path.join(locales, SOURCE_LOCALE)
    target_path = os.path.join(locales, TARGET_LOCALE)

    source_keys = extract_keys(source_path)
    target_keys = extract_keys(target_path)
    source_set, target_set = set(source_keys), set(target_keys)

    corpus = build_corpus(root)
    prefixes = extract_prefixes(corpus)

    dead = []
    for key in source_keys:
        if not is_referenced(base_of(key), corpus, prefixes):
            dead.append(key)

    return (sorted(set(dead)),
            sorted(source_set - target_set),
            sorted(target_set - source_set))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_i18n_keys",
        description="i18n 键健康：死键检测 + 中英键集合对称（防膨胀职责从行数闸移交至此）")
    parser.add_argument("--root", default=ROOT, help="仓库根（默认自动定位）")
    parser.add_argument("--list-dead", action="store_true",
                        help="只按行列出死键（人工清理用，退出码恒 0）")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        dead, zh_only, en_only = find_violations(args.root)
    except OSError as exc:
        print("i18n-keys: FAIL——读不到 locale 文件：%s" % exc)
        return 1

    if args.list_dead:
        for key in dead:
            print(key)
        return 0

    problems = []
    if dead:
        problems.append("死键 %d 个（locale 定义、引用语料里找不到引用）：" % len(dead))
        for key in dead[:40]:
            problems.append("  - %s" % key)
        if len(dead) > 40:
            problems.append("  …（共 %d 个，用 --list-dead 看全）" % len(dead))
    if zh_only:
        problems.append("中英不对称——zh-CN 有、en 无的键 %d 个：%s%s"
                        % (len(zh_only), ", ".join(zh_only[:20]),
                           "" if len(zh_only) <= 20 else " …"))
    if en_only:
        problems.append("中英不对称——en 有、zh-CN 无的键 %d 个：%s%s"
                        % (len(en_only), ", ".join(en_only[:20]),
                           "" if len(en_only) <= 20 else " …"))

    if not problems:
        print("i18n-keys: OK（死键 0、中英对称）")
        return 0
    print("i18n-keys: FAIL（%d 类问题）" % len(problems))
    for item in problems:
        print(item)
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
