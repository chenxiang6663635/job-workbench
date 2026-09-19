# -*- coding: utf-8 -*-
"""旧名 import 统计器——给「删除 shim」这件事一个**只许下降**的进度条。

背景（2026-09-17 批 6）：领域层开始包化（`packages/jobws-core`，import 名
`jobws_core`），旧路径 `tools/filelock.py` / `tools/workspace_io.py` 改为转发
shim + `DeprecationWarning`，目的是让**存量调用点零改动**。但「零改动」不能
无限期维持——否则 shim 会变成永久的第二套入口，包化等于没做。

所以仿照 `check_size.py` 与 `check_i18n_hardcode.py` 的清单形态：把当前实测的
旧名 import 点数**登记为上限**，此后**只许下降**——谁新增一处旧名 import，这里
就报错；全部改完（降到 0）的下一版即可删 shim。

为什么用 `ast` 而不是正则：注释与文档字符串里大量出现 `import filelock`
（正是 shim 自己在解释迁移），正则会把它们当成调用点，实测数永远降不下来。

用法：
    python tools/jobws.py lint legacy-imports              # 校验（0 合规 / 1 超标）
    python tools/jobws.py lint legacy-imports --print-allowlist   # 打印当前实测（更新清单用）
"""

from __future__ import print_function

import argparse
import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST = os.path.join(ROOT, "tools", "legacy_imports_allowlist.txt")

# 要盯的旧名（第二批继续往这里加：PR-B 会补 jd_score / report / question_bank
# 与 url_infer / status_parse / tls_policy）
LEGACY_NAMES = ("filelock", "workspace_io", "pathres", "tracker", "approval")

# `packages` 必须进来：包内若写旧名 import，包外这层闸门就看不见了——而那正是
# 「搬进去就静默放行」的形态。`check_size.py` 早已把 packages 列进 SCAN_DIRS，
# 这里对齐（2026-09-19 批 6 第二批）。
SCAN_DIRS = ("tools", "web/backend", "mcp", "tests", "scripts", "packages")
SKIP_DIRS = {"__pycache__", "node_modules", "dist", "build", ".venv"}

# shim 自身不算调用点：它们就是被观测对象的别名文件
SKIP_FILES = {
    os.path.join("tools", "filelock.py"),
    os.path.join("tools", "workspace_io.py"),
    os.path.join("web", "backend", "pathres.py"),
}


def _iter_python_files():
    for rel_dir in SCAN_DIRS:
        base = os.path.join(ROOT, rel_dir)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                if rel in SKIP_FILES:
                    continue
                yield rel, full


def count_legacy_imports():
    """统计每个旧名被 import 的次数（按 ast 节点计，一处一行算一次）。"""
    counts = dict((name, 0) for name in LEGACY_NAMES)
    details = dict((name, []) for name in LEGACY_NAMES)
    for rel, full in _iter_python_files():
        try:
            with io.open(full, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=full)
        except (SyntaxError, ValueError) as exc:
            # 解析不了就跳过并说明——不许静默（CONTRIBUTING「至少记日志」）
            print("跳过（无法解析）：%s（%s）" % (rel, exc), file=sys.stderr)
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:  # 相对导入不是旧名
                    names = [node.module.split(".")[0]]
            for name in names:
                if name in counts:
                    counts[name] += 1
                    details[name].append("%s:%d" % (rel, node.lineno))
    return counts, details


def load_allowlist():
    """读清单：`旧名 = 上限  # 理由`。返回 (dict, 报错列表)。"""
    limits = {}
    errors = []
    if not os.path.isfile(ALLOWLIST):
        return limits, ["找不到清单 %s" % os.path.relpath(ALLOWLIST, ROOT)]
    with io.open(ALLOWLIST, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if "=" not in text:
                errors.append("第 %d 行没有 `=`：%s" % (lineno, text))
                continue
            name, value = text.split("=", 1)
            name = name.strip()
            value = value.split("#")[0].strip()
            try:
                limits[name] = int(value)
            except ValueError:
                errors.append("第 %d 行的上限不是整数：%s" % (lineno, text))
    return limits, errors


def main():
    parser = argparse.ArgumentParser(
        prog="check_legacy_imports",
        description="旧名 import 统计（只许下降）")
    parser.add_argument("--print-allowlist", action="store_true",
                        help="打印当前实测的清单草稿（用于更新上限）")
    args = parser.parse_args()

    counts, details = count_legacy_imports()

    if args.print_allowlist:
        print("# 旧名 import 点的**存量上限**：只许下降，不许上升。")
        print("# 更新方式：先改代码降低实测数，再把上限改成新值（不要直接调高上限放过新增）。")
        for name in sorted(counts):
            print("%s = %d" % (name, counts[name]))
        return 0

    limits, errors = load_allowlist()
    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1

    problems = []
    for name in sorted(counts):
        if name not in limits:
            # 自洁：清单里登记过、现在一个都没有了 → 该删那一行（可以删 shim 了）
            continue
        if counts[name] > limits[name]:
            problems.append(
                "旧名 `%s` 的 import 点从 %d 涨到了 %d——新增调用请用 "
                "jobws_core：%s" % (name, limits[name], counts[name],
                                    "、".join(details[name][:5])))
    for name in sorted(limits):
        if name not in counts:
            problems.append("清单里的 `%s` 已不在观测范围（改名或已删）"
                            "——删掉这一行" % name)
        elif counts[name] == 0:
            problems.append("旧名 `%s` 已无调用点——可以删 shim 了，并删掉清单这一行" % name)

    if problems:
        print("旧名 import 检查未通过：")
        for item in problems:
            print("  - %s" % item)
        return 1

    print("旧名 import 检查通过（存量上限内：%s）"
          % "、".join("%s=%d" % (n, counts[n]) for n in sorted(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
