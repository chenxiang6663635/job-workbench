# -*- coding: utf-8 -*-
"""批量修复目录重组后 Markdown 中的路径引用断链。

背景：本仓库 77 份 Markdown 中的路径引用全部是纯文本形式（多数被反引号包裹），
几乎不存在 Markdown 链接语法 ](...) 。因此本脚本做的是路径文本替换，而非链接重写。

用法：
    python tools/fix_links.py                 # 演练模式，只报告将要修改的内容
    python tools/fix_links.py --apply         # 实际写入
    python tools/fix_links.py --apply --verbose

设计要点：
1. 按最长前缀匹配。02_作战手册 分裂成三个目标目录，因此必须匹配到二级子目录粒度，
   不能整体替换。
2. 除 03_模拟复盘 外，各被引用子目录在重组中相对深度不变（只是父目录改名），
   故替换后无需调整 ../ 层数。
3. 03_模拟复盘 由顶层下沉到 03_面试准备/模拟复盘/，深度 +1，其文件内的
   "../" 前缀需补一层，由 DEPTH_COMPENSATE 单独处理。
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (旧前缀, 新前缀)。键一律不带尾部斜杠，这样既能匹配 `01_事实库/xxx.md`，
# 也能匹配裸目录引用 `01_事实库`。匹配时按长度降序，确保
# 02_作战手册/知识词典 优先于 02_作战手册。
PATH_MAP = [
    ("02_作战手册/README_作战手册导航.md", "03_面试准备/README_面试准备导航.md"),
    ("02_作战手册/知识词典", "04_知识库"),
    ("02_作战手册/自我介绍", "03_面试准备/自我介绍"),
    ("02_作战手册/项目表达", "03_面试准备/项目表达"),
    ("02_作战手册/核心题库", "03_面试准备/核心题库"),
    ("02_作战手册/行为面", "03_面试准备/行为面"),
    ("02_作战手册/技术面", "03_面试准备/技术面"),
    ("02_作战手册/简历", "02_简历工坊"),
    ("01_事实库", "00_事实库"),
    ("03_模拟复盘", "03_面试准备/模拟复盘"),
]
PATH_MAP.sort(key=lambda pair: len(pair[0]), reverse=True)

# 相对仓库根的路径 -> 需要补的 "../" 层数（因该文件所在目录深度增加）
DEPTH_COMPENSATE = {
    "03_面试准备/模拟复盘/mock_综合模拟面_v0.1.md": 1,
}

# 匹配 ../ 或 ./ 开头、或 0x_ 开头的路径片段，遇到空白、中文标点、引号、反引号、右括号为止
PATH_RE = re.compile(
    r"(?:\.\./|\./)*"          # 可选的相对前缀
    r"(?:0[0-9]_[^，。；、）)\]\"'`\s]+)"  # 以 0x_ 开头的目录名
)

# docs/ 下的设计文档描述的是「旧路径 -> 新路径」映射关系，改写会破坏其语义，故排除
SKIP_DIRS = {".git", "tools", "__pycache__", ".codebuddy", "docs"}

# 归档说明的作用是列出旧目录名并解释「不做改写」的理由，改写会自相矛盾
SKIP_FILES = {"99_归档/README.md"}


def is_markdown(rel_path):
    return rel_path.lower().endswith(".md")


def iter_markdown_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, ROOT).replace("\\", "/")
            if is_markdown(rel):
                yield rel, abs_path


def rewrite(text, rel_path):
    """返回 (新文本, 命中列表)。

    深度补偿只作用于**本次实际替换的引用**，不对文件内所有 ../ 前缀无条件加层——
    否则重复运行脚本会不断叠加 ../ ，破坏幂等性。
    """
    hits = []
    levels = DEPTH_COMPENSATE.get(rel_path, 0)

    def _sub(m):
        original = m.group(0)
        prefix_match = re.match(r"((?:\.\./|\./)*)", original)
        prefix = prefix_match.group(1)
        body = original[len(prefix):]

        for old, new in PATH_MAP:
            # body == old 处理裸目录引用；startswith(old + "/") 处理目录下级路径
            if body == old or body.startswith(old + "/"):
                new_body = new + body[len(old):]
                new_prefix = prefix + "../" * levels
                result = new_prefix + new_body
                hits.append((original, result))
                return result
        return original

    new_text = PATH_RE.sub(_sub, text)
    return new_text, hits


def main():
    parser = argparse.ArgumentParser(description="修复目录重组后的路径引用断链")
    parser.add_argument("--apply", action="store_true", help="实际写入，缺省为演练模式")
    parser.add_argument("--verbose", action="store_true", help="打印每一处替换")
    args = parser.parse_args()

    total_files = 0
    total_hits = 0
    changed = []

    for rel, abs_path in iter_markdown_files():
        if rel in SKIP_FILES:
            continue

        with io.open(abs_path, "r", encoding="utf-8") as f:
            original_text = f.read()

        new_text, hits = rewrite(original_text, rel)

        if not hits:
            continue

        total_files += 1
        total_hits += len(hits)
        changed.append(rel)

        print("[%s] %d 处" % (rel, len(hits)))
        if args.verbose:
            for old, new in hits:
                print("    %s  ->  %s" % (old, new))

        if args.apply and new_text != original_text:
            with io.open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)

    print("")
    print("汇总：%d 个文件，%d 处替换" % (total_files, total_hits))
    if not args.apply:
        print("（演练模式，未写入。加 --apply 实际执行）")
    else:
        print("已写入 %d 个文件" % len(changed))

    return 0


if __name__ == "__main__":
    sys.exit(main())
