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
只认精确段名：`[26.09.15.1]` 与 `[26.09.15.2]` 是两回事。

用法（入口已统一，见 tools/jobws.py）：
    python tools/jobws.py release version                    # 打印"今日若发布"的时间戳号
    python tools/jobws.py release check --tag v26.09.15.1    # 校验 tag 与版本一致 + 段存在
    python tools/jobws.py release check --notes-out out.md   # 抽段落盘（CI 用）
退出码：0 通过；1 检查未过（版本不一致 / CHANGELOG 段缺失）；2 文件缺失或读取失败。
"""

from __future__ import print_function

import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_JSON = os.path.join(ROOT, "web", "electron", "package.json")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")

# 时间戳版本号（2026-09-15 体系切换）：
# - 发布号（tag / CHANGELOG 段名 / 界面显示）= YY.MM.DD.N（如 26.09.15.1）；
# - 机器版本（package.json / latest.yml / 产物文件名）= YY.M.D（如 26.9.15）。
# 机器版本为什么不带 N：实测 electron-builder 会把 build metadata（`+N`）在
# 产物文件名与 latest.yml 两处剥离（26.9.15+1 → 26.9.15），且 electron-updater
# 对非 semver 直接抛 ERR_UPDATER_INVALID_VERSION（AppUpdater.js:212-217）。
_TS_FULL = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})\.(\d+)$")
_TS_MACHINE = re.compile(r"^(\d{2})\.(\d{1,2})\.(\d{1,2})$")


def read_version():
    """版本号唯一来源：web/electron/package.json（CONTRIBUTING 的规定）。

    任何换不到**非空字符串版本号**的形态（JSON 坏、键缺失、值不是字符串）统一
    抛 ValueError——入口层映射为退出码 2。旧实现 `["version"]` 直取：键缺失抛
    KeyError、值为 null 在别处炸成 TypeError，都不在契约的异常面里（跨宿主审查
    MAJOR，2026-09-14）。
    """
    with io.open(PACKAGE_JSON, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise ValueError("package.json 的 version 缺失或不是字符串")
    return version.strip()


def version_tuple(raw):
    """解析时间戳版本号为 (yy, mm, dd, n)；机器形态的 n 为 None。非本体系返回 None。

    拒绝 prerelease（`26.9.15-1`）与 build metadata（`26.9.15+1`）：前者会让
    electron-builder 生成非 latest 通道文件，后者会被工具链剥离（见常量区注释）。
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    match = _TS_FULL.match(text)
    if match:
        return tuple(int(part) for part in match.groups())
    match = _TS_MACHINE.match(text)
    if match:
        yy, mm, dd = match.groups()
        return (int(yy), int(mm), int(dd), None)
    return None


def next_version(today, existing_tags):
    """按发布当日生成 `YY.MM.DD.N`；同日已有 tag 时 N 递增（读既有 tag 序列，不落状态文件）。"""
    ymd = (today.year % 100, today.month, today.day)
    used = []
    for tag in existing_tags or []:
        parsed = version_tuple(tag[1:] if tag.startswith("v") else tag)
        if parsed and parsed[:3] == ymd and parsed[3] is not None:
            used.append(parsed[3])
    number = max(used) + 1 if used else 1
    return "%02d.%02d.%02d.%d" % (ymd[0], ymd[1], ymd[2], number)


def version_matches_tag(tag, package_version):
    """闸1 判定：**日期三段一致**。N 不参与——机器版本（YY.M.D）表达不了 N
    （build metadata 会被 electron-builder 剥离）；同日多版在机器层不可区分是
    已知取舍，N 只用于 tag / CHANGELOG / 界面命名。"""
    tag_parsed = version_tuple(tag[1:] if tag.startswith("v") else tag)
    pkg_parsed = version_tuple(package_version)
    return (
        tag_parsed is not None
        and pkg_parsed is not None
        and tag_parsed[:3] == pkg_parsed[:3]
    )


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
    """返回 (ok, 信息行清单, 说明文本或 None)。

    CHANGELOG 不存在或读取失败（权限 / 占用 / 坏编码）时抛 OSError——由入口层
    映射为退出码 2（契约：文件缺失或读取失败 → 2）。

    时间戳体系（2026-09-15）：tag 与机器版本的比对走 version_matches_tag
    （日期三段，N 不参与）；CHANGELOG 段名是**发布号**（如 26.09.15.1），
    有 tag 时用 tag 的号作段名，无 tag（纯本地按机器版本预检）才退回机器形态。
    """
    lines = []
    ok = True
    if tag:
        if version_matches_tag(tag, version):
            lines.append("tag 与版本一致：%s ↔ %s（机器版本）" % (tag, version))
        else:
            ok = False
            lines.append("tag 与 package.json 版本不一致：tag=%s，package.json=%s。"
                         "先 bump 版本号再打 tag（比对规则见 version_matches_tag）。"
                         % (tag, version))

    path = changelog_path or CHANGELOG
    if not os.path.isfile(path):
        raise FileNotFoundError("找不到 CHANGELOG：%s" % path)
    with io.open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()

    section_name = tag[1:] if tag and tag.startswith("v") else version
    notes = find_section(text, section_name)
    if notes is None:
        ok = False
        lines.append("CHANGELOG.md 里没有 [%s] 段。把它从 [Unreleased] 落成 [%s] "
                     "再打 tag。" % (section_name, section_name))
    else:
        lines.append("CHANGELOG 段存在：## [%s]（%d 行将作为 Release 说明）"
                     % (section_name, notes.count("\n") + 1))
    return ok, lines, notes


def print_next_version():
    """打印「若今天发布」的时间戳号（只读；写入 package.json 由人工 bump + check 把关）。

    N 的递增来源 = 仓库既有 tag 序列（`git tag --list v*`），不落状态文件；
    读 tag 失败（不在仓库 / git 不可用）时按「无同日 tag」处理并给出警告。
    """
    parser = argparse.ArgumentParser(
        prog="jobws release version",
        description="打印「若今天发布」的时间戳号（YY.MM.DD.N）与当前 package.json 版本。")
    parser.parse_args()  # 只认 -h/--help；多余参数按用法错误退出（2）

    tags = []
    try:
        out = subprocess.check_output(
            ["git", "tag", "--list", "v*"], cwd=ROOT, text=True)
        tags = [line.strip() for line in out.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError) as exc:
        print("警告：读取 git tag 失败（%s）——按无同日 tag 处理" % exc)
    today = datetime.date.today()
    print("今日版本号：%s" % next_version(today, tags))
    print("当前 package.json 版本：%s" % read_version())
    return 0


def main():
    parser = argparse.ArgumentParser(description="发布预检、当日号生成与 Release 说明抽取")
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

    try:
        ok, lines, notes = check(version, tag=args.tag)
    except (OSError, UnicodeDecodeError) as exc:
        print("错误：读取 CHANGELOG 失败：%s" % exc)
        return 2
    for line in lines:
        print(line)
    if not ok:
        return 1

    if args.notes_out:
        try:
            with io.open(args.notes_out, "w", encoding="utf-8") as handle:
                handle.write(notes + "\n")
        except OSError as exc:
            print("错误：写出 %s 失败：%s" % (args.notes_out, exc))
            return 2
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
