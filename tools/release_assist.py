# -*- coding: utf-8 -*-
"""发版辅助的**唯一**实现：发布前本地预检 + Release 说明抽取。

为什么要有它：CHANGELOG 段与 tag/版本的一致性此前**只在 release.yml 里**核对
（打 tag 之后、windows runner 构建完才轮到），抽段逻辑还是 workflow 里的一段
内联 pwsh——本地无从预演，等于把两条最容易犯的错（忘写 CHANGELOG 段 / tag
与 package.json 版本不一致）留到「tag 已经推上去了」才发现。本模块把这两件
事收敛成一条命令，本地与 CI 同源：

- 本地（打 tag **前**）：`jobws release check --tag v0.3.0` —— 红着就别打 tag。
- CI（release.yml 的抽段步骤）：`jobws release check --version <ver>
  --notes-out release-notes.md` —— 与本地同一实现，不再维护第二份 pwsh。

抽取规则（与 release.yml 旧实现逐字对齐）：取 `## [<ver>]` 段头到下一个
`## [` 之前的全部行（含段头），去掉尾部空行；没有该段则失败并提示先落章。
只认精确版本号：`[0.3.0]` 与 `[0.3.0-beta]` 是两回事。

用法（入口已统一，见 tools/jobws.py）：
    python tools/jobws.py release check                      # 按 package.json 版本查
    python tools/jobws.py release check --tag v0.3.0         # 校验 tag 一致 + 段存在
    python tools/jobws.py release check --notes-out out.md   # 抽段落盘（CI 用）
退出码：0 通过；1 检查未过（版本不一致 / CHANGELOG 段缺失）；2 文件缺失或读取失败。
"""

from __future__ import print_function

import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_JSON = os.path.join(ROOT, "web", "electron", "package.json")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")


def read_version():
    """版本号唯一来源：web/electron/package.json（CONTRIBUTING 的规定）。"""
    with io.open(PACKAGE_JSON, "r", encoding="utf-8") as handle:
        return json.load(handle)["version"]


def find_section(changelog_text, version):
    """抽出 `## [<version>]` 段（含段头、去尾部空行）；没有返回 None。"""
    lines = changelog_text.splitlines()
    head = re.compile(r"^## \[" + re.escape(version) + r"\]")
    next_head = re.compile(r"^## \[")
    start = None
    for index, line in enumerate(lines):
        if head.match(line):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if next_head.match(lines[index]):
            end = index
            break
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


def check(version, tag=None, changelog_path=None):
    """返回 (ok, 信息行清单, 说明文本或 None)。"""
    lines = []
    ok = True
    if tag:
        if tag == "v" + version:
            lines.append("tag 与 package.json 版本一致：%s" % tag)
        else:
            ok = False
            lines.append("tag 与 package.json 版本不一致：tag=%s，package.json=%s。"
                         "先 bump 版本号再打 tag。" % (tag, version))

    path = changelog_path or CHANGELOG
    if not os.path.isfile(path):
        lines.append("找不到 CHANGELOG：%s" % path)
        return False, lines, None
    with io.open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()

    notes = find_section(text, version)
    if notes is None:
        ok = False
        lines.append("CHANGELOG.md 里没有 [%s] 段。把它从 [Unreleased] 落成 [%s] "
                     "再打 tag。" % (version, version))
    else:
        lines.append("CHANGELOG 段存在：## [%s]（%d 行将作为 Release 说明）"
                     % (version, notes.count("\n") + 1))
    return ok, lines, notes


def main():
    parser = argparse.ArgumentParser(description="发布预检与 Release 说明抽取")
    parser.add_argument("--version", default=None,
                        help="版本号（默认读 web/electron/package.json）")
    parser.add_argument("--tag", default=None,
                        help="tag 名（给了就校验与版本一致），如 v0.3.0")
    parser.add_argument("--notes-out", default=None,
                        help="把 Release 说明写到该文件（CI 用）")
    args = parser.parse_args()

    if not os.path.isfile(PACKAGE_JSON):
        print("错误：找不到 %s（版本号唯一来源）" % PACKAGE_JSON)
        return 2
    if not os.path.isfile(CHANGELOG):
        print("错误：找不到 %s" % CHANGELOG)
        return 2
    try:
        real = read_version()
    except (OSError, ValueError) as exc:
        print("错误：读取 %s 失败：%s" % (PACKAGE_JSON, exc))
        return 2

    # --version 只是「显式声明」的通道（CI 从 package.json 读出后原样传回），
    # 不得与仓库当前版本不一致——否则预检可被一个手滑的参数绕过；预检的信任
    # 基础就是「始终核对真实版本」（跨宿主审查 MAJOR，2026-09-14）。
    if args.version and args.version != real:
        print("版本参数（%s）与 web/electron/package.json（%s）不一致——"
              "预检对象必须是仓库当前版本；bump 后再跑。" % (args.version, real))
        return 1
    version = real
    print("版本：%s（web/electron/package.json）" % version)

    ok, lines, notes = check(version, tag=args.tag)
    for line in lines:
        print(line)
    if not ok:
        return 1

    if args.notes_out:
        with io.open(args.notes_out, "w", encoding="utf-8") as handle:
            handle.write(notes + "\n")
        print("Release 说明已写出：%s" % args.notes_out)
    else:
        print("")
        print("--- Release 说明预览（发布后将原样成为 Release 说明） ---")
        print(notes)
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py（同 check_skills 的处理）
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py release check ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
