# -*- coding: utf-8 -*-
"""从 template/ 初始化一个个人工作区。

用法：
    python tools/init_workspace.py                       # 初始化到 personal/
    python tools/init_workspace.py --target my_workspace # 指定目录名
    python tools/init_workspace.py --domain hvac-cooling # 同时装入领域插件
    python tools/init_workspace.py --demo                # 空模板 + 满数据 demo

行为：
    1. 复制 template/workspace/ 的六个模块到目标目录
    2. 复制 template/AGENTS.example.md 为目标目录的 AGENTS.md（待填写）
    3. 若指定 --domain，把对应插件复制为目标目录的 config/
    4. 若指定 --demo，再把 template/demo/ 的占位数据铺上去（覆盖空骨架）

--demo 的意义：开箱就能看到填满数据的界面（8 条投递 / 3 场面试 / 2 位联系人 /
1 个 Offer / 2 张解析卡 / 1 份简历），用于评估、截图与教学。数据全部是占位
（示例科技、云帆智算、13800000000、sample@example.com），不含任何真实信息。
demo 数据的「方向」字段用的是 software-backend 插件的 direction id，因此
--demo 未显式指定 --domain 时会默认装入该插件。

已存在的目标目录不会被覆盖，除非加 --force。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import io
import os
import shutil
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "template")
PROFILES = os.path.join(TEMPLATE, "profiles")
DEMO = os.path.join(TEMPLATE, "demo")

# --demo 的数据按 software-backend 插件的 direction id 写的，未显式指定
# --domain 时默认用它，否则「方向」列会通不过 tracker check
DEMO_DEFAULT_DOMAIN = "software-backend"
MODULES = ["00_事实库", "01_岗位池", "02_简历工坊",
           "03_面试准备", "04_知识库", "05_投递追踪"]

# 初始化后提示用户关注的模板文件
EXAMPLE_FILES = [
    "00_事实库/_模板_事实卡.md",
    "01_岗位池/_模板_解析卡.md",
    "02_简历工坊/pdf/_模板_resume.html",
    "03_面试准备/自我介绍/_模板_自我介绍.md",
    "03_面试准备/行为面/_模板_行为故事.md",
    "05_投递追踪/_示例_tracker.csv",
]


def list_domains():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(d for d in os.listdir(PROFILES)
                  if os.path.isdir(os.path.join(PROFILES, d)))


def copy_tree_file(src, dst):
    """复制单个文件，已存在则跳过。"""
    if not os.path.isfile(dst):
        shutil.copy2(src, dst)


def copy_tree(src, dst, overwrite=False):
    """Python 3.8 兼容的目录复制（dirs_exist_ok 是 3.8+，此处自行实现）。

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


def install_domain(target, domain):
    """把领域插件复制为 <target>/config/。返回退出码。"""
    domain_src = os.path.join(PROFILES, domain)
    if not os.path.isdir(domain_src):
        print("错误：找不到领域插件 `%s`" % domain)
        print("可用插件：%s" % "、".join(list_domains()))
        return 1
    copy_tree(domain_src, os.path.join(target, "config"))
    print("已装入领域插件：%s" % domain)
    return 0


def demo_counts():
    """按 demo 骨架里的实际数据统计，而不是把数字写死在提示里。

    写死的话，往 template/demo/ 加一条数据、提示就会开始撒谎——而「提示说的和实际
    不一致」正是这个仓库最忌讳的那类问题。所以这里数一遍。
    """
    def rows(rel):
        path = os.path.join(DEMO, rel)
        if not os.path.isfile(path):
            return 0
        with io.open(path, "r", encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        return max(0, len(lines) - 1)  # 减掉表头

    def dirs(rel, suffix=None):
        path = os.path.join(DEMO, rel)
        if not os.path.isdir(path):
            return 0
        items = os.listdir(path)
        if suffix:
            items = [i for i in items if i.endswith(suffix)]
        return len([i for i in items if os.path.isdir(os.path.join(path, i))
                    or os.path.isfile(os.path.join(path, i))])

    return {
        "tracker": rows("05_投递追踪/tracker.csv"),
        "interviews": rows("05_投递追踪/interviews.csv"),
        "contacts": rows("05_投递追踪/contacts.csv"),
        "offers": rows("05_投递追踪/offers.csv"),
        "jobs": dirs("01_岗位池"),
        "resumes": dirs("02_简历工坊/source", suffix=".json"),
    }


def install_demo(target, domain):
    """把 template/demo/ 的占位数据铺到目标工作区。

    全新初始化时这些文件都是**新建**的：模板里没有 tracker.csv（只有 `_示例_tracker.csv`），
    所以正常情况下一个都不会被覆盖。只有在已有工作区上重跑 `--demo --force` 时才会覆盖，
    那时把被覆盖的文件逐条报出来。
    """
    if not os.path.isdir(DEMO):
        print("错误：找不到 demo 数据骨架 %s" % DEMO)
        return 1
    if domain != DEMO_DEFAULT_DOMAIN:
        print("注意：demo 数据是配 %s 写的，当前装入的是 %s，" % (DEMO_DEFAULT_DOMAIN, domain))
        print("      「方向」列可能与插件不符（可改 tracker.csv 或换插件）。")
        print("      注：tracker check 不校验方向，校验它的是 tracker add 与 list --direction。")
    replaced = copy_tree(DEMO, target, overwrite=True)
    counts = demo_counts()
    print("已装入 demo 数据（全部为占位信息，可放心截图）")
    print("  已装入：%d 条投递 / %d 场面试 / %d 位联系人 / %d 个 Offer / %d 张解析卡 / %d 份简历"
          % (counts["tracker"], counts["interviews"], counts["contacts"],
             counts["offers"], counts["jobs"], counts["resumes"]))
    if replaced:
        print("")
        print("注意：以下 %d 个文件本来已存在，已被 demo 数据覆盖：" % len(replaced))
        for path in replaced:
            print("  - %s" % os.path.relpath(path, ROOT))
        print("若那是你的真实数据，请立刻从备份/快照恢复（设置页可手动备份）。")
    return 0


def print_next_steps(target_name, demo=False):
    print("")
    print("工作区已就绪：%s" % target_name)
    if demo:
        print("")
        print("这是 demo 工作区：数据全是占位信息，可以直接上手体验或截图。")
        print("想换成自己的真实数据，删掉这个目录、不加 --demo 重新初始化即可。")
    else:
        print("")
        print("下一步：")
        print("  1. 填写 %s/AGENTS.md 的第三节硬门槛事实（必填，否则 JD 硬门槛判定会卡住）" % target_name)
        print("  2. 填写第五节自定义诚实红线")
        print("  3. 在 00_事实库/ 建事实卡——先做这步，后面所有环节都依赖它")
    print("")
    print("随工作区一起生成的模板（以 _模板_ 开头，复制后填写）：")
    for rel in EXAMPLE_FILES:
        print("  - %s/%s" % (target_name, rel))
    print("")
    print("各模块用途见 %s/README.md" % target_name)


def _display_path(path, base):
    """展示用路径：同盘给相对路径，跨盘退回绝对路径。

    `os.path.relpath` 跨盘会直接抛 `ValueError`——仓库在 D 盘、临时工作区在 C 盘
    时就会炸（本次实测：测试里的目标目录都在 tmp_path）。
    """
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _plan_tree(src, dst, overwrite=False):
    """只读遍历：算出复制时**会新建**与**会覆盖**哪些文件（**不落盘**）。

    判定规则与 `copy_tree` 保持一致（默认跳过已存在文件，overwrite=True 才覆盖，
    子目录会被创建）——否则「预览说会覆盖 3 个」和「实际覆盖了 5 个」就开始
    各说各话。真正的复制仍由 `copy_tree` 执行。
    """
    creates, replaces = [], []
    for item in sorted(os.listdir(src)):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            sub_creates, sub_replaces = _plan_tree(s, d, overwrite)
            creates.extend(sub_creates)
            replaces.extend(sub_replaces)
        elif os.path.isfile(d):
            if overwrite:
                replaces.append(d)
        else:
            creates.append(d)
    return creates, replaces


def plan_init(target, domain=None, demo=False):
    """算一遍初始化将做什么（**不落盘**）：返回 (errors, plan)。

    plan 里两份清单分别对应「新建」与「覆盖」——**覆盖清单才是重点**：demo 数据
    落在一个已经填了真实数据的工作区上就是数据丢失，用户必须在落盘**之前**看到它。
    """
    ws_src = os.path.join(TEMPLATE, "workspace")
    if not os.path.isdir(ws_src):
        return ["找不到模板骨架 %s" % ws_src], None

    creates, replaces = [], []
    for module in MODULES:
        src = os.path.join(ws_src, module)
        if os.path.isdir(src):
            sub_creates, sub_replaces = _plan_tree(src, os.path.join(target, module))
            creates.extend(sub_creates)
            replaces.extend(sub_replaces)

    readme_dst = os.path.join(target, "README.md")
    if (os.path.isfile(os.path.join(ws_src, "README.md"))
            and not os.path.isfile(readme_dst)):
        creates.append(readme_dst)

    agents_dst = os.path.join(target, "AGENTS.md")
    if (os.path.isfile(os.path.join(TEMPLATE, "AGENTS.example.md"))
            and not os.path.isfile(agents_dst)):
        creates.append(agents_dst)

    effective_domain = domain or (DEMO_DEFAULT_DOMAIN if demo else None)
    if effective_domain:
        domain_src = os.path.join(PROFILES, effective_domain)
        if not os.path.isdir(domain_src):
            return ["找不到领域插件 `%s`（可用：%s）"
                    % (effective_domain, "、".join(list_domains()))], None
        sub_creates, sub_replaces = _plan_tree(domain_src, os.path.join(target, "config"))
        creates.extend(sub_creates)
        replaces.extend(sub_replaces)

    if demo:
        if not os.path.isdir(DEMO):
            return ["找不到 demo 数据骨架 %s" % DEMO], None
        sub_creates, sub_replaces = _plan_tree(DEMO, target, overwrite=True)
        creates.extend(sub_creates)
        replaces.extend(sub_replaces)

    name = os.path.basename(target.rstrip("\\/")) or target
    summary = "初始化工作区 %s：新建 %d 个文件" % (name, len(creates))
    if replaces:
        summary += "，**覆盖 %d 个已存在的文件**" % len(replaces)

    diff = ["| 状态 | 文件 |", "|---|---|"]
    for path in replaces:
        diff.append("| **将覆盖** | %s |" % _display_path(path, ROOT))
    diff.append("| 将新建 | %d 个文件（首个：%s） |" % (
        len(creates), _display_path(creates[0], ROOT) if creates else "—"))

    return [], {
        "payload": {"target": os.path.abspath(target), "domain": effective_domain,
                    "demo": bool(demo)},
        "summary": summary,
        "diff": diff,
        "targets": [os.path.abspath(target)],
    }


def _run_init(target, domain, demo):
    """真正执行初始化（落盘），返回 (created, replaced) 两份文件清单。

    清单来自 `_plan_tree`——与预览同一份判定规则，所以「预览说会覆盖 N 个」
    与「实际覆盖了 N 个」不会各说各话。
    """
    created, replaced = [], []
    ws_src = os.path.join(TEMPLATE, "workspace")
    for module in MODULES:
        src = os.path.join(ws_src, module)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(target, module)
        creates, replaces = _plan_tree(src, dst)
        copy_tree(src, dst)
        created.extend(creates)
        replaced.extend(replaces)

    readme_src = os.path.join(ws_src, "README.md")
    readme_dst = os.path.join(target, "README.md")
    if os.path.isfile(readme_src) and not os.path.isfile(readme_dst):
        copy_tree_file(readme_src, readme_dst)
        created.append(readme_dst)

    agents_src = os.path.join(TEMPLATE, "AGENTS.example.md")
    agents_dst = os.path.join(target, "AGENTS.md")
    if os.path.isfile(agents_src) and not os.path.isfile(agents_dst):
        shutil.copy2(agents_src, agents_dst)
        created.append(agents_dst)

    if domain:
        domain_src = os.path.join(PROFILES, domain)
        if os.path.isdir(domain_src):
            dst = os.path.join(target, "config")
            creates, replaces = _plan_tree(domain_src, dst)
            copy_tree(domain_src, dst)
            created.extend(creates)
            replaced.extend(replaces)

    if demo and os.path.isdir(DEMO):
        creates, replaces = _plan_tree(DEMO, target, overwrite=True)
        copy_tree(DEMO, target, overwrite=True)
        created.extend(creates)
        replaced.extend(replaces)

    return created, replaced


def apply_approved_init(payload, workspace=None):
    """两段式的第二步：真正初始化工作区。

    落盘前重新检查一次目标目录：预览之后它可能被填了东西——那时候"将覆盖 N 个
    文件"的承诺已经不成立，拒绝比继续安全（ConflictError → 请重新预览）。
    """
    import tracker  # 冲突语义只有一处定义；init 与 tracker 无循环依赖

    target = payload.get("target")
    if not target or not os.path.isabs(target):
        raise tracker.ConflictError("令牌里的目标路径不可用——请重新预览。")
    if os.path.exists(target) and os.listdir(target):
        raise tracker.ConflictError(
            "目标目录 %s 在预览之后被填了内容——为免覆盖，已拒绝。请重新预览。"
            % os.path.basename(target.rstrip("\\/")))

    domain = payload.get("domain")
    demo = bool(payload.get("demo"))
    created, replaced = _run_init(target, domain, demo)
    return {"written": len(created),
            "summary": "已初始化 %s（新建 %d 个文件，覆盖 %d 个）"
                       % (os.path.basename(target.rstrip("\\/")) or target,
                          len(created), len(replaced))}


def main():
    parser = argparse.ArgumentParser(description="初始化个人工作区")
    parser.add_argument("--target", default="personal", help="目标目录名，相对仓库根")
    parser.add_argument("--domain", help="要装入的领域插件 ID，如 hvac-cooling")
    parser.add_argument("--demo", action="store_true",
                        help="额外铺上占位 demo 数据（8 投递 / 3 面试 / 2 联系人 / 1 Offer）")
    parser.add_argument("--force", action="store_true", help="目标已存在时仍继续")
    parser.add_argument("--preview", action="store_true",
                        help="只预览将新建 / 覆盖哪些文件（不落盘）；"
                             "确认后用 python tools/jobws.py apply <令牌> 执行")
    args = parser.parse_args()

    target = os.path.join(ROOT, args.target)

    if os.path.exists(target) and os.listdir(target) and not args.force:
        print("目标目录已存在且不为空：%s" % args.target)
        print("加 --force 覆盖，或换一个 --target 名称。")
        return 1

    if getattr(args, "preview", False):
        import approval
        errors, plan = plan_init(target, args.domain, args.demo)
        if errors:
            for problem in errors:
                print("错误：%s" % problem)
            return 1
        result = approval.preview("init", target, plan["payload"], plan["summary"],
                                  plan["diff"], plan["targets"])
        print("## 预览（未写入）\n")
        print(result["summary"])
        for line in plan["diff"]:
            print(line)
        print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
        print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
        return 0

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

    # 骨架总说明。模块内各自还有 README，这里复制的是工作区根的那份
    ws_readme = os.path.join(ws_src, "README.md")
    if os.path.isfile(ws_readme):
        copy_tree_file(ws_readme, os.path.join(target, "README.md"))
        print("已生成工作区说明 README.md")

    # 2. 档案模板 -> AGENTS.md
    agents_src = os.path.join(TEMPLATE, "AGENTS.example.md")
    agents_dst = os.path.join(target, "AGENTS.md")
    if os.path.isfile(agents_src) and not os.path.isfile(agents_dst):
        shutil.copy2(agents_src, agents_dst)
        print("已生成 AGENTS.md（待填写）")

    # 3. 领域插件。demo 数据的「方向」列依赖 software-backend，未指定时默认装它
    domain = args.domain
    if not domain and args.demo:
        domain = DEMO_DEFAULT_DOMAIN
        print("--demo 未指定 --domain，默认装入 %s" % domain)
    if domain:
        code = install_domain(target, domain)
        if code:
            return code
    else:
        print("未指定 --domain，稍后手动复制插件到 config/ 即可")
        print("可用插件：%s" % "、".join(list_domains()))

    # 4. demo 数据（覆盖模板里的同名空骨架）
    if args.demo:
        code = install_demo(target, domain or DEMO_DEFAULT_DOMAIN)
        if code:
            return code

    print_next_steps(args.target, args.demo)
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py init ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
