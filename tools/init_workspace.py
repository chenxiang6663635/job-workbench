# -*- coding: utf-8 -*-
"""从 template/ 初始化一个个人工作区。

用法：
    python tools/init_workspace.py                       # 初始化到 personal/
    python tools/init_workspace.py --target my_workspace # 指定目录名
    python tools/init_workspace.py --domain hvac-cooling # 同时装入领域插件

行为：
    1. 复制 template/workspace/ 的六个模块到目标目录
    2. 复制 template/AGENTS.example.md 为目标目录的 AGENTS.md（待填写）
    3. 若指定 --domain，把对应插件复制为目标目录的 config/

已存在的目标目录不会被覆盖，除非加 --force。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import os
import shutil
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "template")
PROFILES = os.path.join(TEMPLATE, "profiles")
MODULES = ["00_事实库", "01_岗位池", "02_简历工坊",
           "03_面试准备", "04_知识库", "05_投递追踪"]


def list_domains():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(d for d in os.listdir(PROFILES)
                  if os.path.isdir(os.path.join(PROFILES, d)))


def copy_tree(src, dst):
    """Python 3.8 兼容的目录复制（dirs_exist_ok 是 3.8+，此处自行实现）。"""
    if not os.path.isdir(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d)
        elif not os.path.isfile(d):
            shutil.copy2(s, d)


def main():
    parser = argparse.ArgumentParser(description="初始化个人工作区")
    parser.add_argument("--target", default="personal", help="目标目录名，相对仓库根")
    parser.add_argument("--domain", help="要装入的领域插件 ID，如 hvac-cooling")
    parser.add_argument("--force", action="store_true", help="目标已存在时仍继续")
    args = parser.parse_args()

    target = os.path.join(ROOT, args.target)

    if os.path.exists(target) and os.listdir(target) and not args.force:
        print("目标目录已存在且不为空：%s" % args.target)
        print("加 --force 覆盖，或换一个 --target 名称。")
        return 1

    ws_src = os.path.join(TEMPLATE, "workspace")
    if not os.path.isdir(ws_src):
        print("错误：找不到模板骨架 %s" % ws_src)
        return 1

    # 1. 复制六个模块
    for module in MODULES:
        src = os.path.join(ws_src, module)
        if os.path.isdir(src):
            copy_tree(src, os.path.join(target, module))
    print("已创建六个模块目录")

    # 2. 档案模板 -> AGENTS.md
    agents_src = os.path.join(TEMPLATE, "AGENTS.example.md")
    agents_dst = os.path.join(target, "AGENTS.md")
    if os.path.isfile(agents_src) and not os.path.isfile(agents_dst):
        shutil.copy2(agents_src, agents_dst)
        print("已生成 AGENTS.md（待填写）")

    # 3. 领域插件
    if args.domain:
        domain_src = os.path.join(PROFILES, args.domain)
        if not os.path.isdir(domain_src):
            print("错误：找不到领域插件 `%s`" % args.domain)
            print("可用插件：%s" % "、".join(list_domains()))
            return 1
        copy_tree(domain_src, os.path.join(target, "config"))
        print("已装入领域插件：%s" % args.domain)
    else:
        print("未指定 --domain，稍后手动复制插件到 config/ 即可")
        print("可用插件：%s" % "、".join(list_domains()))

    print("")
    print("工作区已就绪：%s" % args.target)
    print("")
    print("下一步：")
    print("  1. 填写 %s/AGENTS.md 的第三节硬门槛事实（必填，否则 JD 硬门槛判定会卡住）" % args.target)
    print("  2. 填写第五节自定义诚实红线")
    print("  3. 在 00_事实库/ 建立你的项目事实卡")
    return 0


if __name__ == "__main__":
    sys.exit(main())
