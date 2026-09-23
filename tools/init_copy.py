# -*- coding: utf-8 -*-
"""init_workspace 的复制机制（2026-09-23 审计修复批自 init_workspace.py 拆出：
那边是水位文件，覆盖保护的新逻辑进来就必须给老内容找新家）。

只做「怎么复制」，不含任何输出与 CLI 参数：判定规则（默认跳过已存在文件、
overwrite=True 才覆盖）由调用方与 `_plan_tree` 共享——预览说覆盖 N 个、
实际就覆盖 N 个，不各说各话。
"""

import os
import shutil


def copy_tree_file(src, dst):
    """复制单个文件，已存在则跳过。"""
    if not os.path.isfile(dst):
        shutil.copy2(src, dst)


def copy_tree(src, dst, overwrite=False):
    """按 overwrite 语义复制目录树。

    不用 `shutil.copytree`：它给不出「覆盖了哪些文件」这份清单，而调用方必须把
    覆盖这件事说出口。

    overwrite=False（默认）用于模板骨架：已存在的文件不动，避免覆盖用户内容。
    overwrite=True 用于 demo 数据：它要覆盖模板里的同名空骨架（如 tracker.csv）。

    返回被覆盖的文件绝对路径列表——调用方必须把这件事说出口：--demo 落到
    一个已经填了真实数据的工作区上就是数据丢失，静默覆盖不能接受。
    """
    if not os.path.isdir(dst):
        os.makedirs(dst)
    replaced = []
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            replaced.extend(copy_tree(s, d, overwrite))
        elif os.path.isfile(d):
            if overwrite:
                shutil.copy2(s, d)
                replaced.append(d)
        else:
            shutil.copy2(s, d)
    return replaced


def plan_tree(src, dst, overwrite=False):
    """只读遍历：算出复制时**会新建**与**会覆盖**哪些文件（**不落盘**）。

    判定规则与 `copy_tree` 保持一致（默认跳过已存在文件，overwrite=True 才覆盖）
    ——否则「预览说会覆盖 3 个」和「实际覆盖了 5 个」就开始各说各话。真正的复制
    仍由 `copy_tree` 执行。

    只数**文件**：`copy_tree` 会顺带把空目录建出来（如 `applications/`），但目录
    不会覆盖任何东西，也不在「新建 N 个文件」的口径里（独立审查 MINOR-3）。
    """
    creates, replaces = [], []
    for item in sorted(os.listdir(src)):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            sub_creates, sub_replaces = plan_tree(s, d, overwrite)
            creates.extend(sub_creates)
            replaces.extend(sub_replaces)
        elif os.path.isfile(d):
            if overwrite:
                replaces.append(d)
        else:
            creates.append(d)
    return creates, replaces
