# -*- coding: utf-8 -*-
"""技能合规与重名校验的**唯一**实现。

为什么必须是唯一实现：校验规则若写在两处（CI 一份、分发脚本一份），迟早分叉，
而分叉掉的那一半正好就是没拦住的那一半——本仓库已经在提交信息治理上吃过这个亏
（本地钩子与 CI 各写一份正则）。故 CI、分发脚本、本地自查一律调这里。

校验项（每项都对应一个**真实发生过的或高度可能**的事故）：
  1. frontmatter 存在且闭合——没有它，宿主读不到 name/description。
  2. `name` 必填且**等于父目录名**——技能身份 = 目录名 = frontmatter name，
     两者不一致时，宿主按哪个挂载不可预期。
  3. `description` 必填且长度合规——宿主靠它判断要不要激活这个技能；
     空描述等于永不触发，过长则稀释触发信号。
  4. **全局 name 唯一**——同名会被宿主**静默覆盖**（不报错），这是本批次
     最该拦住的一条：apply / jd / resume / track / recruit-coach 全是高概率
     通用名，装到用户级目录时等于拿通用词跟别人抢位置。
  5. `compatibility` 必填——环境声明，让宿主能判断能否挂载。

刻意**未实现**的一条：正文不得引用仓库相对路径（如 `tools/xxx.py`）。
它应该在阶段 B（抽出 `jobws` 统一入口、技能正文改调 jobws）之后再启用——
现在技能正文里确实有 21 处 `tools/` 引用，启用即 CI 红，而红着又不能合并。
等到阶段 B 把引用换成 `jobws` 后，在这里补上这条规则即可（见 CHANGELOG 0.2.0）。

用法：
    python tools/check_skills.py                 # 校验仓库 skills/
    python tools/check_skills.py --root <dir>    # 校验指定目录
退出码：0 全部合规，1 存在问题，2 目录不存在。
"""

from __future__ import print_function

import argparse
import os
import re
import sys

DESC_MAX = 300
REQUIRED = ["name", "description", "compatibility"]

# 本仓库技能的命名空间。用户级 ~/.agents/skills/ 是与别人共用的同一个目录，
# 通用名（apply / resume / track …）撞车概率高，而撞车的结果是**静默覆盖**。
# 注意：下面的「name 唯一」只能保证仓库内不重名，兑现不了「不撞车」——
# 真正兑现它的是这条前缀规则。独立审查指出原实现漏了它，故补上。
NAME_RE = re.compile(r"^jwb-[a-z0-9]+(-[a-z0-9]+)*$")

# 改名前的旧目录名。分发脚本清理残留时**只认这五个**，而不是
# 「凡不在源码里的目录都删」——后者会把用户自己装的第三方技能一并删掉。
LEGACY_NAMES = {"apply", "jd", "resume", "track", "recruit-coach"}


def _parse_frontmatter(text):
    """解析 --- 包裹的 frontmatter，返回 (字段字典, 错误信息)。

    只认 `key: value` 单行形式，不引第三方 YAML 依赖：本仓库的 SKILL.md
    结构就这么简单，引入解析器反而多一个要维护的东西。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "缺少 frontmatter（文件首行必须是 ---）"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, "frontmatter 未闭合（找不到结束的 ---）"

    fields = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, None


def inspect_skills(skills_root):
    """扫描 skills_root 下每个技能目录，返回每个技能的问题清单。

    返回项形如 {"dir": str, "name": str | None, "problems": [str]}，
    problems 为空即合规。
    """
    results = []
    if not os.path.isdir(skills_root):
        return results

    for entry in sorted(os.listdir(skills_root)):
        path = os.path.join(skills_root, entry)
        if not os.path.isdir(path):
            continue

        item = {"dir": entry, "name": None, "problems": []}
        skill_md = os.path.join(path, "SKILL.md")
        if not os.path.isfile(skill_md):
            item["problems"].append("缺少 SKILL.md")
            results.append(item)
            continue

        # utf-8-sig：Windows 上记事本 / PowerShell 重定向产出的文件带 BOM，
        #   而 str.strip() 不剥离 \ufeff，会让首行判不出 `---` 而误报。
        # errors="replace"：宁可把坏字节换成占位符继续校验，也不要让校验器
        #   （以及依赖它的分发脚本）以 traceback 崩掉。
        try:
            with open(skill_md, encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            item["problems"].append("读取失败：%s" % exc)
            results.append(item)
            continue
        fields, error = _parse_frontmatter(text)
        if error:
            item["problems"].append(error)
            results.append(item)
            continue

        name = fields.get("name")
        item["name"] = name
        if not name:
            item["problems"].append("frontmatter 缺 name")
        else:
            if name != entry:
                item["problems"].append(
                    "name 与目录名不一致：name=%s，目录=%s（技能身份要求两者相同）"
                    % (name, entry))
            if not NAME_RE.match(name):
                item["problems"].append(
                    "name 必须带 jwb- 前缀（当前：%s）——通用名装到用户级目录时会"
                    "与别人已装的同名技能冲突，宿主**静默覆盖**" % name)

        for key in REQUIRED:
            if key != "name" and not fields.get(key):
                item["problems"].append("frontmatter 缺 %s" % key)

        desc = fields.get("description")
        if desc in ("|", ">"):
            # 本解析器只认单行值；块标量会被读成 "|" 从而绕过长度校验
            item["problems"].append(
                "frontmatter 不支持块标量写法（description: %s），请改成单行" % desc)
        elif desc and len(desc) > DESC_MAX:
            item["problems"].append(
                "description 过长（%d 字符，上限 %d）" % (len(desc), DESC_MAX))

        results.append(item)

    # 重名检查：同名会在宿主侧静默覆盖，必须在这里拦住，且**两个都标记**——
    # 只报后一个的话，读者会以为前一个是对的。
    seen = {}
    for item in results:
        name = item.get("name")
        if not name:
            continue
        seen.setdefault(name, []).append(item["dir"])
    for name, dirs in seen.items():
        if len(dirs) > 1:
            for item in results:
                if item["name"] == name:
                    item["problems"].append(
                        "技能名重复：`%s` 同时被 %s 使用——宿主会**静默覆盖**其中一个"
                        % (name, "、".join(dirs)))

    return results


def describe(results):
    """把结果渲染成人能读的文本（CI 日志与分发脚本共用）。"""
    lines = []
    total = len(results)
    bad = [r for r in results if r["problems"]]
    lines.append("已检查 %d 个技能，%d 个不合规。" % (total, len(bad)))
    for item in results:
        if not item["problems"]:
            continue
        lines.append("")
        lines.append("  [%s]" % item["dir"])
        for problem in item["problems"]:
            lines.append("    - %s" % problem)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="校验 skills 是否合规")
    parser.add_argument("--root", default=None, help="技能目录，默认仓库 skills/")
    args = parser.parse_args()

    root = args.root
    if root is None:
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

    if not os.path.isdir(root):
        print("错误：找不到技能目录 %s" % root)
        return 2

    results = inspect_skills(root)
    print(describe(results))
    if any(item["problems"] for item in results):
        print("")
        print("修复后再分发：不合规的技能会被宿主跳过，重名的会被静默覆盖。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
