# -*- coding: utf-8 -*-
"""四端检查器的两块外围：技能镜像比对与说明页渲染。

（由 check_four_ends.py 拆出；2026-09-17 批 4.7 的规模预算闸门要求。
两者都只读不写：渲染产物由 check_four_ends 的 `--write` 落地。）
"""

import hashlib
import os
import re

from four_ends_probe import read

# 技能镜像目标：**从 install_skills.TARGETS 派生**而不是手抄——两份清单迟早漂移
# （2026-09-17 独立审查指认）。只取项目级目标；用户级 `~/.agents/skills` 在仓库根
# 之外，检查器不跨出仓库根去读，属已知边界。
# 扩镜像（批 10 计划扩到 commands/agents）时复用本文件的比对核心，
# 但"目标缺失＝未分发、跳过"这条宽容语义要**单独决策**——整目录被删不报错
# 对 skills（按需挂载）合理，对 commands/agents 未必。
try:
    import install_skills as _install_skills
    SKILL_TARGETS = [(rel, label) for (_tid, label, kind, rel)
                     in _install_skills.TARGETS if kind == "project"]
except ImportError:  # 独立调用本模块（不在仓库内）时的兜底
    SKILL_TARGETS = [
        (".codebuddy/skills", "项目级 .codebuddy"),
        (".claude/skills", "项目级 .claude"),
        (".agents/skills", "项目级 .agents"),
        (".codex/skills", "项目级 .codex"),
    ]


def _skill_files(skill_dir):
    """技能目录下所有文件的 (相对路径, 内容 sha256 前 16 位)。"""
    out = []
    for dirpath, _dirnames, filenames in os.walk(skill_dir):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, skill_dir).replace(os.sep, "/")
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()[:16]
            out.append((rel, digest))
    return out


def skill_mirrors(root):
    """技能镜像比对：真源 skills/ ↔ 各目标；目标不存在＝未分发，跳过。

    返回 (issues, checked)：checked 是**实际比对过**的目标名，便于输出说明。
    """
    issues, checked = [], []
    source = os.path.join(root, "skills")
    if not os.path.isdir(source):
        return ["找不到 skills/ 真源目录"], checked

    source_files = {}
    for name in sorted(os.listdir(source)):
        skill_dir = os.path.join(source, name)
        if os.path.isdir(skill_dir):
            for rel, digest in _skill_files(skill_dir):
                source_files["%s/%s" % (name, rel)] = digest

    for rel_target, label in SKILL_TARGETS:
        target = os.path.join(root, rel_target)
        if not os.path.isdir(target):
            continue
        checked.append(label)
        mirror_files = {}
        for name in sorted(os.listdir(target)):
            skill_dir = os.path.join(target, name)
            if os.path.isdir(skill_dir):
                for rel, digest in _skill_files(skill_dir):
                    mirror_files["%s/%s" % (name, rel)] = digest
        for key in sorted(set(source_files) - set(mirror_files)):
            issues.append("%s 缺少 %s（真源有、镜像没有）—— 重新分发：jobws skills install"
                          % (label, key))
        for key in sorted(set(mirror_files) - set(source_files)):
            issues.append("%s 多出 %s（真源没有）—— 镜像过期或手工加的副本" % (label, key))
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
