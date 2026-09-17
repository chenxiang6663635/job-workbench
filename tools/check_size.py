# -*- coding: utf-8 -*-
"""规模预算检查——把 CONTRIBUTING「代码卫生」第 1 条从软条款变成有量具的闸门。

为什么要有它（2026-09-16 全仓库审计）：条款早就写了「单文件 ≤300 / 单函数 ≤80」，
但**没有任何一处会去量**——实测 21 个 py + 14 个 ts 超 300 行、16 个函数超 80 行，
全靠 PR 自审自觉。本脚本就是那把尺子。

两档阈值（与 CONTRIBUTING 一致）：
- **逻辑型**（业务代码）：文件 ≤300 行、函数 ≤80 行；
- **数据/声明型**（i18n 语言包、常量表、测试与 fixtures）：≤1500 行——
  声明式代码行数多但复杂度低，与业务逻辑同阈值只会逼人把常量表拆碎。

存量用 `size_allowlist.txt` 登记（`路径 = 行数  # 理由`），并守两条：
- **自洁**：清单里的文件一旦不再超标就报错要求删除——与 i18n 豁免清单同款教训
  （留着等于给将来的同名文件预授权）；
- **只许变小**：登记值兼作水位线，已豁免的文件可以缩短，不许继续变长。

于是它**不逼着任何人一次性重写 tracker.py（2515 行），但止住继续膨胀**。

用法：
    python tools/check_size.py                   # 全量扫（CI / 本地随手跑）
    python tools/check_size.py --staged          # 只扫 git 暂存文件（增量守门）
    python tools/check_size.py --print-allowlist # 打印当前超标项的清单草稿
"""

from __future__ import print_function

import argparse
import ast
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST = os.path.join(ROOT, "tools", "size_allowlist.txt")

LIMIT_LOGIC_FILE = 300
LIMIT_LOGIC_FN = 80
LIMIT_DATA_FILE = 1500

SCAN_DIRS = ("tools", "web/backend", "web/frontend/src", "tests")
SKIP_DIRS = {"__pycache__", "node_modules", "dist", "build", "release", ".venv"}
SOURCE_SUFFIX = (".py", ".ts", ".tsx")

# 数据/声明型：行数多但复杂度低，与业务代码同阈值没有意义
DATA_MARKERS = ("locales/", "conftest", "fixture", "allowlist")


def classify(rel_path):
    """判定规模预算分类：logic（业务） / data（数据·声明）。

    不扫的目录（node_modules / dist / __pycache__ 等）在遍历阶段就跳过了，
    不进这里——所以只有这两种取值，没有第三类。

    测试整体按 data 计：它由大量平铺用例构成，行数与复杂度不成正比。
    """
    rel = rel_path.replace("\\", "/")
    if rel.startswith("tests/") or any(m in rel for m in DATA_MARKERS):
        return "data"
    return "logic"


def limit_for(kind):
    return LIMIT_DATA_FILE if kind == "data" else LIMIT_LOGIC_FILE


def count_lines(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def python_functions(path):
    """[(长度, 起始行, 函数名)]；非 Python 或解析失败返回空。

    TS/TSX 的函数边界（箭头函数、嵌套 JSX）难以静态界定，误报会逼人把组件拆成
    没人想看的样子——因此**函数长度只管 Python**，TS 侧只守文件行数。
    """
    if not path.endswith(".py"):
        return []
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
    except (SyntaxError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(((node.end_lineno or node.lineno) - node.lineno + 1,
                        node.lineno, node.name))
    return out


def load_allowlist():
    """{相对路径: (登记行数, 理由)}——与 i18n 豁免清单同款格式（可带 # 理由）。"""
    items = {}
    if not os.path.isfile(ALLOWLIST):
        return items
    with io.open(ALLOWLIST, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            body = line.split("#", 1)[0].strip()
            if "=" not in body:
                continue
            path, value = body.split("=", 1)
            try:
                items[path.strip().replace("\\", "/")] = (int(value.strip()), line)
            except ValueError:
                continue
    return items


def iter_source_files():
    for rel in SCAN_DIRS:
        base = os.path.join(ROOT, rel)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if name.endswith(SOURCE_SUFFIX):
                    full = os.path.join(dirpath, name)
                    yield os.path.relpath(full, ROOT).replace("\\", "/"), full


def staged_files():
    """暂存文件列表；不在 git 仓库里（或 git 不可用）时返回空——降级为「没什么可扫」。

    刻意不用 `check=True`：那会在非仓库目录里抛未捕获异常，而本脚本常被当作
    独立工具调用（此时「没有暂存文件」比「崩掉」更接近事实）。
    """
    proc = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return []
    return [p.replace("\\", "/") for p in proc.stdout.split("\0") if p]


def scan(staged=False):
    """返回违规描述列表（空 = 通过）。

    staged=True 时只扫 git 暂存文件——增量守门的入口。
    """
    allow = load_allowlist()
    if staged:
        wanted = set(staged_files())
        targets = [(rel, full) for rel, full in iter_source_files() if rel in wanted]
    else:
        targets = list(iter_source_files())

    problems = []
    seen = set()
    for rel, full in targets:
        seen.add(rel)
        kind = classify(rel)
        lines = count_lines(full)
        limit = limit_for(kind)

        # 函数长度先算：登记项的豁免要覆盖「文件行数 + 其中的长函数」两项，
        # 否则像 dashboard.py（文件没超标、但 dashboard() 有 114 行）这种
        # 半超标的存量永远过不了关，闸门第一天就没人理了
        over_fns = [] if kind == "data" else [
            f for f in python_functions(full) if f[0] > LIMIT_LOGIC_FN]

        if rel in allow:
            recorded, _ = allow[rel]
            if lines <= limit and not over_fns:
                problems.append("%s：文件 %d 行、也无超长函数——清单调不下去了，"
                                "请删掉这一行（自洁：留着等于给将来预授权）"
                                % (rel, lines))
            elif lines > recorded:
                problems.append("%s：%d 行 > 登记水位 %d 行——存量豁免只许变小、"
                                "不许继续膨胀（超 %d 行需拆分）"
                                % (rel, lines, recorded, limit))
            continue

        if lines > limit:
            problems.append("%s：%d 行 > %d（%s 型）——超出规模预算，"
                            "按职责拆分或登记进 size_allowlist.txt（写清理由）"
                            % (rel, lines, limit, kind))
        for length, lineno, name in over_fns:
            problems.append("%s:%d %s()：%d 行 > %d——拆成「编排函数 + helper」"
                            % (rel, lineno, name, length, LIMIT_LOGIC_FN))

    # 清单自洁：**只在全量模式做**——增量模式本来就只看暂存那几个文件，
    # 不能据此判定其它条目失效（那会一提交就误报一片）
    if not staged:
        for rel in sorted(allow):
            if rel not in seen:
                problems.append("size_allowlist.txt 里的 %s 已不在扫描范围——"
                                "删掉这一行" % rel)
    return problems


def print_allowlist():
    """打印待登记项的清单草稿（人工补理由后粘进 size_allowlist.txt）。

    「文件没超标、但有超长函数」的也要打出来——这类半超标最容易被漏登记，
    而它同样会拦住检查（dashboard.py 就是这么发现的）。
    """
    for rel, full in iter_source_files():
        kind = classify(rel)
        lines = count_lines(full)
        over = [] if kind == "data" else [
            f for f in python_functions(full) if f[0] > LIMIT_LOGIC_FN]
        if lines <= limit_for(kind) and not over:
            continue
        note = ""
        if over:
            note = "（%s）" % "、".join(
                "%s() %d 行" % (name, length) for length, _ln, name in over)
        print("%s = %d  # TODO：写清为什么这一项暂时豁免%s" % (rel, lines, note))


def main(argv=None):
    """走 argparse：`jobws lint size --help` 与其它检查器同形（CLI 面的硬要求）。"""
    parser = argparse.ArgumentParser(
        prog="check_size",
        description="规模预算检查：逻辑型 文件 ≤300 / 函数 ≤80；数据·声明型 ≤1500")
    parser.add_argument("--staged", action="store_true",
                        help="只扫 git 暂存文件（增量守门）")
    parser.add_argument("--print-allowlist", action="store_true",
                        help="打印当前超标项的清单草稿")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.print_allowlist:
        print_allowlist()
        return 0

    problems = scan(staged=args.staged)
    if not problems:
        print("size: OK（规模预算内）")
        return 0
    print("size: FAIL（%d 项超规模预算）" % len(problems))
    for item in problems:
        print("  - %s" % item)
    print("\n阈值：逻辑型 文件 ≤%d 行 / 函数 ≤%d 行；数据·声明型 文件 ≤%d 行"
          % (LIMIT_LOGIC_FILE, LIMIT_LOGIC_FN, LIMIT_DATA_FILE))
    return 1


if __name__ == "__main__":
    sys.exit(main())
