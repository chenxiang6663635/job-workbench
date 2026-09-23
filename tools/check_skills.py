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
  6. **正文不得引用仓库相对路径**（`tools/`、`web/`、`template/`、`skills/`、
     `tests/` 这些顶层目录）——技能会被 `install_skills` 分发到宿主的技能目录，
     那时的工作目录是**用户自己的工作区**、不在这个仓库里：正文里写
     `tools/jobws.py` 只会把宿主引到一条不存在的路径上。命令名就写 `jobws`，
     "它在仓库里的哪个位置"写进 frontmatter 的 `compatibility`（该字段不参与本
     检查——那里正是说明路径的地方）。
     （阶段 B 之前这条被**刻意**推迟：当时正文里有 21 处 `tools/` 引用，启用即
     CI 红、而红着不能合并。`jobws` 统一入口落地、引用全部改完后于 2026-09-14 启用。）
  7. `description` 不含半角冒号+空格（`: `）——严格 YAML 宿主（Codex 实测）会因
     「mapping values are not allowed in this context」拒绝**整个技能**；本仓库
     自己的解析器用 partition 切分、对冒号宽容，所以只有这条校验能拦住。
     **引号包裹亦不豁免**：单行解析器没有引号语义，支持一半比不支持更危险——
     描述文案统一不用半角冒号+空格（跨宿主审查第四轮把这条边界固定为测试）。
  8. **frontmatter 字段白名单**（批 10，对齐 Open Agent Skills 规范）——`licence`、
     `allowed_tools` 这类手滑不会让宿主报错，只会**静默失效**：元数据没生效而本地
     全绿。缩进行属于上一个字段的嵌套映射（`metadata:` 下的 `version`），不算顶层键。
  9. **`references/` 引用可达**（批 10）——渐进披露靠引用分流；路径写错时宿主不会
     报错，技能看起来还在、实际少了一半内容。
  10. **主文件行数上限**（批 10）——超过 `BODY_MAX_LINES` 就该把重参考资料拆到
      `references/`（第二级按需读取）。

用法（入口已统一，见 tools/jobws.py）：
    python tools/jobws.py skills check                 # 校验仓库 skills/
    python tools/jobws.py skills check --root <dir>    # 校验指定目录
退出码：0 全部合规，1 存在问题，2 目录不存在。
"""

from __future__ import print_function

import argparse
import os
import sys

# 规则层（批 10）自本模块拆出：常量与两条纯函数都在 tools/skill_rules.py
# （`check_skills.py` 是登记过水位的存量文件，只许变小）。这里**原样再导出**，
# 外部读到的名字与行为都不变；规则仍只此一处（本模块是唯一入口）。
from skill_rules import (  # noqa: E402
    ALLOWED_FIELDS, BODY_MAX_LINES, DESC_MAX, NAME_RE, REFERENCE_RE,
    REPO_PATH_PREFIXES, REQUIRED, body_problems, frontmatter_problems,
    reference_file_problems, version_problems,
)

# 改名前的旧目录名。分发脚本清理残留时**只认这五个**，而不是
# 「凡不在源码里的目录都删」——后者会把用户自己装的第三方技能一并删掉。
LEGACY_NAMES = {"apply", "jd", "resume", "track", "recruit-coach"}


def _parse_frontmatter(text):
    """解析 --- 包裹的 frontmatter，返回 (字段字典, 错误信息, 结束行号)。

    只认 `key: value` 单行形式，不引第三方 YAML 依赖：本仓库的 SKILL.md
    结构就这么简单，引入解析器反而多一个要维护的东西。

    结束行号（0 基）是给正文扫描用的：`tools/` 这类仓库路径在 frontmatter 里是
    **合法**的（`compatibility` 正是说明"命令在仓库里长什么样"的地方），只有正文
    才禁——所以必须知道正文从哪一行开始。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "缺少 frontmatter（文件首行必须是 ---）", None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, "frontmatter 未闭合（找不到结束的 ---）", None

    fields = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, None, end


def _inspect_one(entry, path):
    """检查单个技能目录，返回 {"dir", "name", "problems"}。"""
    item = {"dir": entry, "name": None, "problems": []}
    skill_md = os.path.join(path, "SKILL.md")
    if not os.path.isfile(skill_md):
        item["problems"].append("缺少 SKILL.md")
        return item

    # utf-8-sig：Windows 上记事本 / PowerShell 重定向产出的文件带 BOM，
    #   而 str.strip() 不剥离 \ufeff，会让首行判不出 `---` 而误报。
    # errors="replace"：宁可把坏字节换成占位符继续校验，也不要让校验器
    #   （以及依赖它的分发脚本）以 traceback 崩掉。
    try:
        with open(skill_md, encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        item["problems"].append("读取失败：%s" % exc)
        return item
    fields, error, frontmatter_end = _parse_frontmatter(text)
    if error:
        item["problems"].append(error)
        return item

    # 规则层在 tools/skill_rules.py（批 10 拆出）：这里只做「读文件 → 交给规则 →
    # 组装结果」。规则分两组——frontmatter 字段级、正文级，各自返回问题清单。
    item["name"] = fields.get("name")
    item["problems"].extend(frontmatter_problems(text, frontmatter_end, fields, entry))
    item["problems"].extend(body_problems(text, frontmatter_end, path))
    # references/ 下的文件随技能一起分发，规则同样适用（独立审查 MAJOR-4）
    item["problems"].extend(reference_file_problems(path))
    return item


def _flag_duplicates(results):
    """重名检查：同名会在宿主侧静默覆盖，必须在这里拦住，且**两个都标记**——
    只报后一个的话，读者会以为前一个是对的。"""
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
        if os.path.isdir(path):
            results.append(_inspect_one(entry, path))
    _flag_duplicates(results)
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
    # 插件资产（批 8）：commands/ 与 agents/ 也过一遍——宿主按目录约定扫描它们，
    # 写坏了没人拦，本校验是唯一防线。
    # 函数内 import：check_plugin_assets 反向引用本模块的 frontmatter 解析器，
    # 模块级互相 import 会成环。
    from check_plugin_assets import inspect_plugin_assets

    asset_findings = inspect_plugin_assets(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if asset_findings:
        print("")
        print("插件资产不合规（%d 处）：" % len(asset_findings))
        for label, problems in asset_findings:
            print("  [%s]" % label)
            for problem in problems:
                print("    - %s" % problem)
    # 版本号一致性：技能 metadata.version 与插件壳 version 都随应用版本走
    # （真值源 web/electron/package.json）。不查的话，发布时只 bump 应用版本就
    # 会留下静默失真的旧值（独立审查 MAJOR-1）。
    version_issues = version_problems(os.path.dirname(os.path.abspath(root)), root)
    if version_issues:
        print("")
        print("版本号不一致（%d 处）：" % len(version_issues))
        for problem in version_issues:
            print("  - %s" % problem)
        print("")
        print("真值源只有一个：web/electron/package.json；技能与插件壳的 version 一起改。")
    if asset_findings or version_issues or any(item["problems"] for item in results):
        print("")
        print("修复后再分发：不合规的技能会被宿主跳过，重名的会被静默覆盖。")
        return 1
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py skills check ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
