# -*- coding: utf-8 -*-
"""JD↔简历差距分析（2026-10-16 #307 从 `jd_score` 拆出）。

搬移范围 = `gap_analysis` 全链：`resolve_profile`（输入定位）· `parse_lexicon`
（词典解析）· 母版汇总 / 简历文本 / JD 读取三个 helper + 比对本体。
为什么拆（而不是往 jd_score 里加判据）：`jd_score.py` 是登记过的水位文件
（558 行，只许变小），而本批要给差距分析补**输入锚点归属预检**——它此前是
领域层三族裸露之一（JD / 简历 / 词典 / 母版 / 事实库全部经 `_read_text` 直读，
无归属、无界）。**连 `resolve_profile` 一起搬**的理由：双向 import 总有一边会
拿到未初始化完成的对方（先导 jd_gap 时 `jd_score` 末尾的 re-export 会炸在
ImportError）；ROOT/PROFILES 跟着它走（同函数求值，幂等），`jd_score` 单向
re-export 三个公开名——调用方（CLI / MCP / Web / 测试）零改动。

预检口径（用户裁决）：分析类只读入口——预检不过**不抛**，整体跳过并记进
既有 `(None, errors)` 协议。宁可明确「差距分析已跳过 + 理由」，不给一个悄悄
读过外部文件的结论。只覆盖**工作区相对锚点**：template 插件目录（应用根下）
是程序自带只读资源，不是用户数据面；工作区分支由 `config/lexicon.md` 锚点
覆盖——config 经链接指向外部时判据照样展开它的真实目标。
"""

import io
import json
import os

from jobws_core import pathres
from jobws_core.workspace_read import is_in_workspace

ROOT = pathres.resolve_root()          # 随 resolve_profile 搬来：同函数求值，幂等
PROFILES = os.path.join(ROOT, "template", "profiles")


def resolve_profile(workspace, domain=None, direction=None):
    """定位领域插件与方向文件。

    查找顺序：工作区 config/（用户可能有自己的副本） -> template/profiles/<domain>/
    返回 (插件目录, 方向文件路径, 警告列表)。未指定 `--domain` 时**不再猜**：没有
    档案则显式失败——此前按字母序取第一个模板插件拿错词典不报错（2026-10-08 审计）。
    """
    warnings = []

    ws_profile = os.path.join(workspace, "config")
    if os.path.isfile(os.path.join(ws_profile, "profile.md")):
        profile_dir = ws_profile
        label = "工作区档案"      # 消息用标签：不再拿工作区父目录名冒充插件名
    elif domain:
        profile_dir = os.path.join(PROFILES, domain)
        label = domain
        if not os.path.isdir(profile_dir):
            warnings.append("找不到领域插件 `%s`（已查找 %s 与 %s）"
                            % (domain, ws_profile, profile_dir))
            return None, None, warnings
    else:
        warnings.append("无法确定领域插件：工作区没有 %s，且未指定 --domain。"
                        "请先 `jobws init --domain <插件>`（或把插件文件复制到 "
                        "config/），或显式传 --domain <插件>。"
                        % os.path.join(ws_profile, "profile.md"))
        return None, None, warnings

    # 方向文件
    dir_dir = os.path.join(profile_dir, "directions")
    if direction:
        path = os.path.join(dir_dir, "%s.md" % direction)
        if os.path.isfile(path):
            return profile_dir, path, warnings
        warnings.append("方向 `%s` 不存在于插件 `%s`" % (direction, label))

    if os.path.isdir(dir_dir):
        available = sorted(f for f in os.listdir(dir_dir) if f.endswith(".md"))
        if available:
            fallback = available[0][:-3]
            if direction:
                warnings.append("回退使用方向 `%s`，结论仅供参考" % fallback)
            return profile_dir, os.path.join(dir_dir, available[0]), warnings

    warnings.append("插件 `%s` 下没有找到任何方向配置" % label)
    return profile_dir, None, warnings


# ---------------------------------------------------------------------------
# JD↔简历差距清单：把「补关键词」拆成两类，这是服务诚实红线的关键——
#   injectable：母版里有、这一版没用上 —— 从既有事实召回，不构成编造
#   missing   ：JD 有而简历与母版都没有 —— 真实缺口，只能靠补经历
# ---------------------------------------------------------------------------

LEXICON_LEVELS = ["Primary", "Secondary", "Weak"]   # 词典三级标题（顺序即优先级）

# 母版来源：简历主版 + 事实库。它们是"你真实拥有的事实全集"，
# 出现在母版里的词才算可召回。
MASTER_FILES = ["简历_主版_v1.0.md"]
FACT_DIR = "00_事实库"
RESUME_DIR = "02_简历工坊"
SOURCE_DIR = "source"
JD_FILENAME = "JD原文.md"


def parse_lexicon(path):
    """解析词典，返回 [(词条, 分层)]：`## Primary（3 分/项）` 之下的每行是用
    顿号分隔的词条。领域术语来自数据文件，本函数不内含任何领域词。"""
    if not path or not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8") as f:
        text = f.read()

    out = []
    level = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            head = stripped.lstrip("#").strip()
            level = None
            for name in LEXICON_LEVELS:
                if head.startswith(name):
                    level = name
                    break
            continue
        if not level or stripped.startswith("#") or stripped.startswith(">"):
            continue
        for term in stripped.split("、"):
            term = term.strip()
            if term:
                out.append((term, level))
    return out


def _escape_message(label, path):
    # 输入锚点越界的可读说明（收集式；由 gap_analysis 的 errors 协议透出）
    return ("%s越出工作区：%s——差距分析已跳过；请把数据放回工作区内，"
            "或移除该符号链接 / junction 后重试。" % (label, path))


def _read_text(path):
    if not os.path.isfile(path):
        return ""
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _input_anchor_errors(workspace, card_path, resume_version):
    """全部输入的归属预检：返回可读错误列表（空 = 全部锚点在工作区内）。

    锚点是「将要读的文件」而非读到的内容——判据**不要求文件存在**（缺输入的
    既有错误口径在 `gap_analysis` 里照旧报）。词典锚点只在与 `resolve_profile`
    同一条件下列（有 config/profile.md 才走工作区分支）：没有它时不误报，有它
    而链接指向外部时判据照样展开真实目标。方向目录也在列（listdir 泄漏口径同 #300）。
    """
    anchors = [
        ("JD 原文", os.path.join(os.path.dirname(os.path.abspath(card_path)),
                                JD_FILENAME)),
        ("简历 JSON", os.path.join(workspace, RESUME_DIR, SOURCE_DIR,
                                  "resume_%s.json" % resume_version)),
    ]
    if os.path.isfile(os.path.join(workspace, "config", "profile.md")):
        anchors.append(("词典", os.path.join(workspace, "config", "lexicon.md")))
        anchors.append(("方向目录",  # 同闸（审查 m2）：listdir 泄漏口径同 #300 岗位池根
                        os.path.join(workspace, "config", "directions")))
    anchors += [("母版", os.path.join(workspace, RESUME_DIR, name))
                for name in MASTER_FILES]
    fact_dir = os.path.join(workspace, FACT_DIR)
    if os.path.isdir(fact_dir):
        anchors.append(("事实库", fact_dir))
    return [_escape_message(label, path) for label, path in anchors
            if not is_in_workspace(workspace, path)]


def _collect_master_text(workspace):
    """汇总母版文本：简历主版 + 事实库全部 md。返回 (文本, 错误列表)。

    这是"你真实拥有的事实全集"——出现在母版里的词，召回它才不构成编造。
    归属再判（#307）：`00_事实库` 根的归属已在入口预检；目录里**单个文件**
    被掉包成区外链接时 `os.walk` 照样列出它（walk 只对子目录链接收手）。
    越界文件不进母版文本、错误上抛——拿半拉母版算可召回，正是「看起来丢
    数据」的形态。
    """
    parts = []
    errors = []
    for name in MASTER_FILES:
        path = os.path.join(workspace, RESUME_DIR, name)
        if not is_in_workspace(workspace, path):
            errors.append(_escape_message("母版", path))
            continue
        parts.append(_read_text(path))

    fact_dir = os.path.join(workspace, FACT_DIR)
    if os.path.isdir(fact_dir):
        for root, dirs, files in os.walk(fact_dir):
            dirs[:] = [d for d in dirs if not d.startswith("__")]
            for name in sorted(files):
                if name.startswith("."):
                    continue
                if not name.lower().endswith((".md", ".txt")):
                    continue
                path = os.path.join(root, name)
                if not is_in_workspace(workspace, path):
                    errors.append(_escape_message("事实库文件", path))
                    continue
                parts.append(_read_text(path))
    return "\n".join(parts), errors


def _resume_text(workspace, version):
    """简历 JSON → 纯文本（用于关键词比对）。"""
    path = os.path.join(workspace, RESUME_DIR, SOURCE_DIR,
                        "resume_%s.json" % version)
    if not os.path.isfile(path):
        return None
    raw = _read_text(path)
    try:
        data = json.loads(raw)
    except ValueError:
        return None

    parts = []

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(data)
    return "\n".join(parts)


def _contains(haystack, needle):
    """子串匹配。英文统一小写比较（EnergyPlus vs energyplus）。"""
    if not needle:
        return False
    h = haystack.lower()
    n = needle.lower()
    return n in h


def gap_analysis(workspace, card_path, resume_version, domain=None, direction=None):
    """JD↔简历差距分析。返回 (结果字典, 错误列表)：matched / injectable /
    missing 三组与来源说明；输入锚点归属预检在最前（#307）——任一输入经符号
    链接指向工作区外时整体跳过并说明理由（不抛，也不「读一半算一半」）。"""
    escaped = _input_anchor_errors(workspace, card_path, resume_version)
    if escaped:
        return None, escaped

    errors = []

    jd_path = os.path.join(os.path.dirname(os.path.abspath(card_path)), JD_FILENAME)
    jd_text = _read_text(jd_path)
    if not jd_text:
        errors.append("找不到 JD 原文（应与解析卡同目录）：%s" % JD_FILENAME)

    resume = _resume_text(workspace, resume_version)
    if resume is None:
        errors.append("找不到简历数据或 JSON 解析失败：source/resume_%s.json"
                      % resume_version)

    profile_dir, _direction_file, warns = resolve_profile(workspace, domain, direction)
    lexicon = parse_lexicon(os.path.join(profile_dir, "lexicon.md")) if profile_dir else []
    if not lexicon:
        errors.append("词典为空或未找到，差距分析缺少词条依据")

    if errors:
        return None, errors + warns

    master, master_errors = _collect_master_text(workspace)
    if master_errors:
        return None, master_errors + warns

    matched, injectable, missing = [], [], []
    seen = set()
    for term, level in lexicon:
        if term in seen:
            continue
        if not _contains(jd_text, term):
            continue          # JD 没提这个词，不参与比对
        seen.add(term)
        if _contains(resume, term):
            matched.append({"term": term, "level": level})
        elif _contains(master, term):
            injectable.append({"term": term, "level": level})
        else:
            missing.append({"term": term, "level": level})

    return {
        "jd": os.path.relpath(jd_path, workspace).replace("\\", "/"),
        "resume": "source/resume_%s.json" % resume_version,
        "lexicon": os.path.relpath(os.path.join(profile_dir, "lexicon.md"),
                                   workspace).replace("\\", "/") if profile_dir else None,
        "matched": matched,
        "injectable": [item["term"] for item in injectable],
        "missing": [item["term"] for item in missing],
        "matchedDetail": matched,
        "injectableDetail": injectable,
        "missingDetail": missing,
        "counts": {
            "matched": len(matched),
            "injectable": len(injectable),
            "missing": len(missing),
        },
    }, warns
