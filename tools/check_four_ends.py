# -*- coding: utf-8 -*-
"""四端一致性检查器（**唯一实现**，别处不要再写一套）。

`tools/four_ends_matrix.json` 是契约真值，本模块负责让契约与实现互相咬合：

1. **正向**：矩阵登记的每一项，必须在对应端真实存在（MCP 工具 / CLI 命令 /
   GUI 路由 / 插件命令）。
2. **反向**：四端真实存在的能力必须被矩阵引用，或落在显式的例外清单里——
   谁新增了能力忘了登记，这里就会报。
3. **命名与配对规则**（可机械判定的那几条）：MCP 写工具必须 `preview_*`；
   插件命令必须在声明文件里登记。
4. **错误码对照**：每个错误标识的 api_code 必须出现在后端错误定义里，
   i18n_key 必须**中英双语都在**。
5. **说明页同步**：`docs/four-ends.md` 由 `--write` 生成，平时只校验——
   手写文档必然漂移，生成 + 校验是唯一能长期维持的方式。
6. **技能镜像**：`skills/`（真源）与各宿主镜像的目录名与内容哈希一致
   （某个镜像目录不存在＝该宿主没分发过，属正常状态，不报错）。

取值逻辑在 `four_ends_probe`（四端探针），渲染与镜像在 `four_ends_extras`——
本模块只做契约比对与编排。三处都**只读、零依赖、不启服务**（CI 安全）。

用法：
    python tools/jobws.py lint four-ends            # 校验（0 合规 / 1 有问题 / 2 找不到目标）
    python tools/jobws.py lint four-ends --write    # 重新生成 docs/four-ends.md
"""

import argparse
import io
import json
import os
import re
import sys

from four_ends_extras import asset_mirrors, glob_field_present, render_doc
from four_ends_probe import (api_codes, cli_capabilities, gui_routes,
                             i18n_keys, mcp_tools, plugin_assets, read)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MATRIX_REL = os.path.join("tools", "four_ends_matrix.json")
DOC_REL = os.path.join("docs", "four-ends.md")

_ENDS = ("cli", "mcp", "plugin", "gui")
# MCP 写工具命名规则：preview_<动作>_<资源>
_WRITE_TOOL_RE = re.compile(r"^preview_[a-z]+_[a-z_]+$")


def load_matrix(root):
    """读契约真值。返回 (matrix, errors)。"""
    path = os.path.join(root, MATRIX_REL)
    if not os.path.isfile(path):
        return None, ["找不到契约文件 %s" % MATRIX_REL]
    try:
        return json.loads(read(path)), []
    except ValueError as exc:
        return None, ["%s 不是合法 JSON：%s" % (MATRIX_REL, exc)]


def _check_capabilities(caps, actual, gui_list):
    """正向：矩阵登记的每一项必须在对应端存在；顺带验两条命名规则。"""
    issues = []
    cli = actual["cli"]
    mcp = actual["mcp"]
    plugin = actual["plugin"]
    mcp_set = set(mcp or [])
    gui_set = set(gui_list or [])

    for cap in caps:
        cid = cap.get("id") or "<无 id>"
        note = cap.get("note") or ""
        if cap.get("cli") and cli:
            words = cap["cli"].split()
            group = words[0]
            if group not in cli["groups"]:
                issues.append("能力 %s：CLI 命令 `%s` 不在命令表里（可用：%s）"
                              % (cid, cap["cli"], " / ".join(cli["groups"])))
            elif len(words) > 1 and group in cli["subs"]:
                # 子命令表只覆盖 skills / release / lint 三组（track / bank 的
                # 子命令在各自模块内部定义，探针读不到）——能验的先验上，
                # 拼错的组名至少不会一路绿灯进说明页。
                available = cli["subs"].get(group, [])
                if available and words[1] not in available:
                    issues.append("能力 %s：CLI 子命令 `%s` 不在 %s 的子命令表里（可用：%s）"
                                  % (cid, cap["cli"], group, " / ".join(available)))
        if cap.get("mcp"):
            if mcp is not None and cap["mcp"] not in mcp_set:
                issues.append("能力 %s：MCP 工具 `%s` 未注册（server.py 里没有）"
                              % (cid, cap["mcp"]))
            if "预览" in note and not _WRITE_TOOL_RE.match(cap["mcp"]):
                issues.append("能力 %s：写入类 MCP 工具名 `%s` 不符合 preview_<动作>_<资源>"
                              % (cid, cap["mcp"]))
        if cap.get("plugin"):
            if (cap["plugin"] not in plugin["commands"]
                    and cap["plugin"] not in plugin["agents"]):
                issues.append("能力 %s：插件命令/子代理 `%s` 不存在（现有命令：%s；子代理：%s）"
                              % (cid, cap["plugin"], " / ".join(plugin["commands"]),
                                 " / ".join(plugin["agents"])))
        if cap.get("gui") and not _gui_has(cap["gui"], gui_set):
            issues.append("能力 %s：GUI 路由 `%s` 在 routers/ 里找不到" % (cid, cap["gui"]))
    return issues


def _gui_has(spec, gui_set):
    """GUI 能力写法是 "METHOD /path"；路径里可能有 {id}，用前缀匹配。"""
    parts = spec.split(" ", 1)
    if len(parts) != 2:
        return False
    method, path = parts[0].upper(), parts[1]
    return any(got_method == method and (got_path == path or got_path.startswith(path))
               for got_method, got_path in gui_set)


def _check_registration(actual, caps, exceptions):
    """反向：MCP 工具与插件命令都必须有归属，且声明文件要登记全部命令。"""
    issues = []
    used_mcp = {cap["mcp"] for cap in caps if cap.get("mcp")}
    used_plugin = {cap["plugin"] for cap in caps if cap.get("plugin")}
    exc_mcp = {i.get("item") for i in exceptions if i.get("end") == "mcp"}
    exc_plugin = {i.get("item") for i in exceptions if i.get("end") == "plugin"}

    for name in actual["mcp"] or []:
        if name not in used_mcp and name not in exc_mcp:
            issues.append("MCP 工具 `%s` 未在矩阵里登记（也不在例外清单）—— "
                          "新增能力要同步 tools/four_ends_matrix.json" % name)
    plugin = actual["plugin"]
    for name in plugin["commands"]:
        if name not in used_plugin and name not in exc_plugin:
            issues.append("插件命令 `%s` 未在矩阵里登记（也不在例外清单）" % name)
    for name in plugin["declared_commands"]:
        if name not in ["%s.md" % item for item in plugin["commands"]]:
            issues.append("plugin.json 声明的命令 %s 不存在于 commands/ 目录" % name)
    for name in plugin["commands"]:
        if "%s.md" % name not in plugin["declared_commands"]:
            issues.append("commands/%s.md 未在 plugin.json 的 commands 里登记" % name)
    # 子代理走与命令完全相同的两道（2026-09-23 二轮审计）：探针早就把 agents 读出来了，
    # 却只用于正向判断——于是 `agents/` 里放个子代理、或不登记进矩阵，检查照样全绿
    # （现成实例：维护者自用的 cross-end-audit 一直零登记）。
    for name in plugin["agents"]:
        if name not in used_plugin and name not in exc_plugin:
            issues.append("插件子代理 `%s` 未在矩阵里登记（也不在例外清单）" % name)
    for name in plugin["declared_agents"]:
        if name not in ["%s.md" % item for item in plugin["agents"]]:
            issues.append("plugin.json 声明的子代理 %s 不存在于 agents/ 目录" % name)
    for name in plugin["agents"]:
        if "%s.md" % name not in plugin["declared_agents"]:
            issues.append("agents/%s.md 未在 plugin.json 的 agents 里登记" % name)
    return issues


def _check_exceptions(caps, exceptions):
    """例外清单本身要成立：端名合法、指向真实能力、有原因。"""
    issues = []
    cap_ids = {cap.get("id") for cap in caps}
    for item in exceptions:
        if item.get("end") not in _ENDS:
            issues.append("例外清单 end 取值非法：%r（应为 %s）"
                          % (item.get("end"), " / ".join(_ENDS)))
        if item.get("item") not in cap_ids:
            issues.append("例外清单引用的能力 %r 不在 capabilities 里" % item.get("item"))
        if not (item.get("reason") or "").strip():
            issues.append("例外清单 %s/%s 缺少原因说明"
                          % (item.get("end"), item.get("item")))
    return issues


def _check_error_map(rows, codes, keys):
    """错误码对照：api_code 必须真实存在，文案键必须中英双语都在。"""
    issues = []
    for row in rows:
        rid = row.get("id") or "<无 id>"
        if row.get("api_code") and row["api_code"] not in codes:
            issues.append("错误码对照 %s：api_code `%s` 在后端错误定义里找不到"
                          % (rid, row["api_code"]))
        key = row.get("i18n_key")
        if key:
            if key not in keys.get("zh", set()):
                issues.append("错误码对照 %s：%s 缺中文文案" % (rid, key))
            if key not in keys.get("en", set()):
                issues.append("错误码对照 %s：%s 缺英文文案" % (rid, key))
    return issues


def _check_host_fields(rows, root):
    """宿主专属字段：字段名必须在对应文件里真的出现过（宽松存在性检查）。"""
    issues = []
    for row in rows:
        pattern = row.get("file_glob") or ""
        field = row.get("field") or ""
        if not pattern or not field:
            issues.append("宿主专属字段条目缺少 file_glob 或 field：%r" % row)
        elif not glob_field_present(root, pattern, field):
            issues.append("宿主专属字段：%s 里没找到 %s（矩阵登记与实际不符）"
                          % (pattern, field))
    return issues


def _check_doc_sync(matrix, root, doc_text):
    """说明页必须与矩阵同步（手写必然漂移，生成 + 校验是唯一能维持的方式）。"""
    doc_path = os.path.join(root, DOC_REL)
    if not os.path.isfile(doc_path):
        return ["缺少 %s —— 用 `jobws lint four-ends --write` 生成" % DOC_REL]
    if read(doc_path) != doc_text:
        return ["%s 与矩阵不同步 —— 用 `jobws lint four-ends --write` 重新生成" % DOC_REL]
    return []


def check(root):
    """跑全部检查。返回 (issues, doc_text)。"""
    matrix, errors = load_matrix(root)
    if errors:
        return errors, ""
    caps = matrix.get("capabilities", [])
    exceptions = matrix.get("exceptions", [])

    issues = []
    cli, e = cli_capabilities(root)
    issues.extend(e)
    mcp, e = mcp_tools(root)
    issues.extend(e)
    gui, e = gui_routes(root)
    issues.extend(e)
    plugin = plugin_assets(root)
    actual = {"cli": cli, "mcp": mcp, "gui": gui, "plugin": plugin}

    issues.extend(_check_capabilities(caps, actual, gui or []))
    issues.extend(_check_registration(actual, caps, exceptions))
    issues.extend(_check_exceptions(caps, exceptions))
    issues.extend(_check_error_map(matrix.get("error_map", []),
                                   api_codes(root), i18n_keys(root)))
    issues.extend(_check_host_fields(matrix.get("host_fields", []), root))
    mirror_issues, _checked = asset_mirrors(root)
    issues.extend(mirror_issues)

    doc_text = render_doc(matrix)
    issues.extend(_check_doc_sync(matrix, root, doc_text))
    return issues, doc_text


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws lint four-ends",
        description="四端一致性：矩阵、实现、说明页与技能镜像是否互相对得上")
    parser.add_argument("--root", default=_ROOT, help="仓库根（默认取本文件所在仓库）")
    parser.add_argument("--write", action="store_true",
                        help="按矩阵重新生成 docs/four-ends.md（其余只校验）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("找不到目录：%s" % root)
        return 2

    issues, doc_text = check(root)
    if args.write and doc_text:
        target = os.path.join(root, DOC_REL)
        directory = os.path.dirname(target)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(doc_text)
        print("已写入 %s" % DOC_REL)
        issues, _ = check(root)   # 写完再校验一遍，把剩下的问题一并报出来

    if issues:
        print("四端一致性检查未通过（%d 项）：" % len(issues))
        for item in issues:
            print("  - %s" % item)
        return 1
    print("四端一致性：OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
