# -*- coding: utf-8 -*-
"""四端检查器的两块外围：技能镜像比对与说明页渲染。

（由 check_four_ends.py 拆出；2026-09-17 批 4.7 的规模预算闸门要求。
两者都只读不写：渲染产物由 check_four_ends 的 `--write` 落地。）
"""

import hashlib
import os
import re

from four_ends_probe import read

# 资产清单：**从 install_skills.ASSETS 派生**而不是手抄——两份清单迟早漂移
# （2026-09-17 独立审查指认）。只取项目级目标；用户级 `~/.agents/skills` 在仓库根
# 之外，检查器不跨出仓库根去读，属已知边界。
# 批 10 起比对范围从「只有 skills」扩到 skills / commands / agents 三类：
# 镜像的成熟做法是「单一真值源 + 生成 + CI 一致性校验」，我们保留拷贝（Windows 软链
# 需开发者模式，不可依赖），靠这条校验兜住副本过期。
try:
    import install_skills as _install_skills
    ASSET_TARGETS = _install_skills.ASSETS
except ImportError:  # 独立调用本模块（不在仓库内）时的兜底：只含技能
    ASSET_TARGETS = [
        ("skills", "skills", [
            ("codebuddy", "项目级 .codebuddy/skills/", "project", ".codebuddy/skills"),
            ("claude", "项目级 .claude/skills/", "project", ".claude/skills"),
            ("agents", "项目级 .agents/skills/", "project", ".agents/skills"),
            ("codex", "项目级 .codex/skills/", "project", ".codex/skills"),
        ]),
    ]


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:16]


def _asset_files(path):
    """目录下所有文件的 (相对路径, 内容 sha256 前 16 位)。

    跟随符号链接：`--link` 分发出来的目标项是指向真源的符号链接，不跟随的话整棵子树
    在比对里「凭空消失」，会把正确的分发报成缺件。但**不能无条件跟随**——指向祖先的
    目录链接会让遍历无限递归挂死，故按 realpath 去重（每个真实目录只走一次）。
    """
    out, seen = [], set()
    stack = [path]
    while stack:
        current = stack.pop()
        real = os.path.realpath(current)
        if real in seen:
            continue
        seen.add(real)
        for name in sorted(os.listdir(current)):
            full = os.path.join(current, name)
            if os.path.isdir(full):
                stack.append(full)
            elif os.path.isfile(full):
                rel = os.path.relpath(full, path).replace(os.sep, "/")
                out.append((rel, _digest(full)))
    return out


def _source_files(source):
    """真源目录的指纹表：目录项递归（技能目录 / 子代理目录），单文件项逐个。"""
    out = {}
    for name in sorted(os.listdir(source)):
        entry = os.path.join(source, name)
        if os.path.isdir(entry):
            for rel, digest in _asset_files(entry):
                out["%s/%s" % (name, rel)] = digest
        elif os.path.isfile(entry):
            out[name] = _digest(entry)
    return out


def asset_mirrors(root):
    """三类资产的镜像比对：真源 ↔ 项目级落点；目标不存在＝未分发，跳过。

    返回 (issues, checked)：checked 是**实际比对过**的「资产 → 目标」标签，便于输出说明。
    """
    issues, checked = [], []
    for asset, source_rel, targets in ASSET_TARGETS:
        source = os.path.join(root, source_rel)
        if not os.path.isdir(source):
            # 真源缺失只有在「已有镜像落点」时才算问题：镜像还在而真源没了，
            # 那份副本必然过期。没有任何落点（局部目录、还没分发的宿主）不算。
            if any(os.path.isdir(os.path.join(root, rel))
                   for _k, _l, kind, rel in targets if kind == "project"):
                issues.append("找不到 %s/ 真源目录（镜像还在，副本必然过期）" % source_rel)
            continue

        source_files = _source_files(source)
        for _key, label, kind, rel in targets:
            if kind != "project":
                continue
            target = os.path.join(root, rel)
            if not os.path.isdir(target):
                continue
            checked.append("%s → %s" % (asset, label))
            mirror_files = _source_files(target)
            for key in sorted(set(source_files) - set(mirror_files)):
                issues.append("%s 缺少 %s（真源有、镜像没有）—— 重新分发：jobws skills install"
                              % (label, key))
            # 「多出」只在技能上判：skills/ 下每个目录都是我们的资产（名字带 jwb- 前缀），
            # 多出来的必然是残留或手工副本。而 `.claude/commands`、`.claude/agents`
            # 也是用户放自己文件的地方——那里的额外文件未必与我们有关，报出来就是
            # 误报（本机为主、CI 看不到 .claude/，最容易让开发者对这张网失去信任）。
            if asset == "skills":
                for key in sorted(set(mirror_files) - set(source_files)):
                    issues.append("%s 多出 %s（真源没有）—— 镜像过期或手工加的副本"
                                  % (label, key))
            for key in sorted(set(source_files) & set(mirror_files)):
                if source_files[key] != mirror_files[key]:
                    issues.append("%s 的 %s 与真源内容不一致 —— 重新分发：jobws skills install"
                                  % (label, key))
    return issues, checked


def glob_field_present(root, pattern, field):
    """在 `commands/*.md`、`skills/*/SKILL.md` 这类模式匹配到的文件里找字段名。

    支持两层（`dir/*/file` 与 `dir/*.ext`），只做**存在性**判断——值合不合法由
    各端自己的校验器管，这里只回答"矩阵登记的字段在不在文件里"。
    """
    parts = pattern.split("/")
    matcher = re.compile(r"^\s*%s\s*:" % re.escape(field), re.M)

    if len(parts) == 2 and not parts[1].startswith("*"):
        candidates = [os.path.join(root, parts[0], parts[1])]
    elif len(parts) == 2:  # dir/*.ext
        base = os.path.join(root, parts[0])
        if not os.path.isdir(base):
            return False
        suffix = parts[1][1:]
        candidates = [os.path.join(base, n) for n in sorted(os.listdir(base))
                      if n.endswith(suffix)]
    elif len(parts) == 3:  # dir/*/file
        base = os.path.join(root, parts[0])
        if not os.path.isdir(base):
            return False
        candidates = [os.path.join(base, n, parts[2]) for n in sorted(os.listdir(base))
                      if os.path.isdir(os.path.join(base, n))]
    else:
        return False

    for full in candidates:
        if os.path.isfile(full) and matcher.search(read(full)):
            return True
    return False


def render_doc(matrix):
    """把矩阵渲染成人读 Markdown（**唯一渲染实现**，`--write` 与校验共用）。"""
    lines = [
        "# 四端能力对照（自动生成，不要手改）",
        "",
        "> 真源是 `tools/four_ends_matrix.json`；本文件由 "
        "`python tools/jobws.py lint four-ends --write` 生成，",
        "> 并由同一个检查器校验是否同步。",
        "",
        "四端：**命令行**（`tools/jobws.py`）/ **AI 宿主**（MCP 服务）/ "
        "**编辑器插件**（`commands/` 与 `agents/`）/ **桌面端**（后端接口与界面）。",
        "",
        "写入类能力的机制是「预览 → 确认 → 落盘」：命令行与 AI 宿主凭令牌，界面靠弹窗确认——"
        "机制不同、语义相同。各端的具体形态并不完全相同：CLI 的 track 类需显式 `--preview`，"
        "题库类命令（bank）默认即出预览，联系人 / Offer 直接落盘——逐项见下方矩阵、措辞真源见"
        "矩阵源的 `_meta.write_rule`。",
        "",
        # 基数（FC-1）：此前口头与文档里出现过与真值不符的条数，根因是**手写**。
        # 改成随真值现算：能力 / 例外 / 错误码的条数永远是这一版矩阵自己的数字。
        "**基数（随本文件自动生成）**：登记能力 **%d** 条、各端不提供的例外 **%d** 条、"
        "错误标识 **%d** 条、宿主专属字段 **%d** 条。"
        % (len(matrix.get("capabilities", [])), len(matrix.get("exceptions", [])),
           len(matrix.get("error_map", [])), len(matrix.get("host_fields", []))),
        "",
        "## 能力矩阵",
        "",
        "| 阶段 | 能力 | 命令行 | AI 宿主（MCP） | 插件 | 桌面端 |",
        "|---|---|---|---|---|---|",
    ]
    for cap in matrix.get("capabilities", []):
        lines.append("| %s | `%s` | %s | %s | %s | %s |" % (
            cap.get("stage") or "", cap.get("id") or "",
            _cell(cap.get("cli")), _cell(cap.get("mcp")),
            _cell(cap.get("plugin")), _cell(cap.get("gui"))))
    lines += ["", "## 各端不提供的能力（含原因）", ""]
    for item in matrix.get("exceptions", []):
        lines.append("- **%s** · `%s`：%s" % (item.get("end"), item.get("item"),
                                            item.get("reason")))
    lines += ["", "## 错误标识对照", "",
              "| 错误标识 | 后端错误码 | 界面文案键 | 命令行退出码 |", "|---|---|---|---|"]
    for row in matrix.get("error_map", []):
        lines.append("| `%s` | `%s` | `%s` | %s |" % (
            row.get("id"), row.get("api_code"), row.get("i18n_key"),
            row.get("cli_exit", "-")))
    lines += ["", "## 宿主专属字段", "",
              "| 文件 | 字段 | 生效宿主 | 说明 |", "|---|---|---|---|"]
    for row in matrix.get("host_fields", []):
        lines.append("| `%s` | `%s` | %s | %s |" % (
            row.get("file_glob"), row.get("field"), row.get("host"), row.get("note")))
    lines.append("")
    return "\n".join(lines)


def _cell(value):
    return "`%s`" % value if value else "—"
