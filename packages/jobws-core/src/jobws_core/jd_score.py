# -*- coding: utf-8 -*-
"""校验 JD 解析卡的评分小节是否自洽，并按阈值输出结论档位。

本脚本不打分——评分由 AI 读 JD 原文与 CODEBUDDY.md 后填进解析卡。
脚本只做三件事：校验各维度分子不超过分母、校验四项之和等于总分、套阈值出档位。
这样设计是为了让评分标准可改在 Markdown 里，改完可以对历史 JD 批量重算。

用法（命令行在 tools/_cli_jd_score.py；唯一入口）：
    python tools/jobws.py jd <解析卡路径>
    python tools/jobws.py jd 01_岗位池/某某公司_某岗位/解析卡.md

退出码：0 成功，1 校验失败或文件错误（由命令层归一化）。
输出到 stdout 的是 Markdown 片段，供命令直接回填解析卡的「结论」小节。
"""

from __future__ import print_function

import os
import re
import sys

from jobws_core import pathres


ROOT = pathres.resolve_root()
PROFILES = os.path.join(ROOT, "template", "profiles")
# B4 整改 A：不再有 DEFAULT_WORKSPACE 副本——默认工作区一律经 pathres.default_workspace()。

# 维度名 -> 满分。顺序即解析卡中的书写顺序
DIMENSIONS = [
    ("技术匹配", 30),
    ("经历匹配", 25),
    ("方向契合", 30),
    ("培养与稳定性", 15),
]

# (下界, 上界, 档位, 动作)。**判定只认下界**（降序取第一行 low <= total，上界只作
# 展示）：左闭右开 75+ / [60,75) / … / <30——分子允许小数，闭区间会留缝（见 verdict）。
THRESHOLDS = [
    (75, 100, "强烈建议投", "立即执行 /apply 生成投递包"),
    (60, 74, "建议投", "执行 /apply 生成投递包"),
    (45, 59, "斟酌", "先看关键缺口能否在一周内补齐，再决定是否投递"),
    (30, 44, "大概率跳过", "除非有内推或岗位调整等额外信息，否则不投"),
    (0, 29, "不投", "终止，不生成任何材料"),
]

TOTAL_MAX = sum(m for _, m in DIMENSIONS)

FIELD_RE = re.compile(r"^\s*(?P<key>[^:：]+)\s*[:：]\s*(?P<value>.*?)\s*$")


def parse_score_section(text):
    """提取 ## 评分 小节中的 key: value 行，返回 dict。"""
    lines = text.splitlines()
    in_section = False
    result = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            # 遇到下一个二级标题即退出评分小节
            if in_section:
                break
            if stripped.replace(" ", "").startswith("##评分"):
                in_section = True
            continue
        if not in_section:
            continue

        m = FIELD_RE.match(line)
        if m:
            result[m.group("key").strip()] = m.group("value").strip()

    return result


def parse_dimension(raw, name, maximum):
    """解析 `24/30` 形式的取值，返回 (分子, 错误列表)。"""
    errors = []
    if not raw:
        return None, ["`%s` 未填写" % name]

    m = re.match(r"^(?P<num>\d+(?:\.\d+)?)\s*/\s*(?P<den>\d+)$", raw)
    if not m:
        return None, ["`%s: %s` 格式错误，应为 `分子/%d` 形式，如 `24/%d`" % (name, raw, maximum, maximum)]

    num = float(m.group("num"))
    den = int(m.group("den"))

    if den != maximum:
        errors.append("`%s` 分母应为 %d，实际为 %d" % (name, maximum, den))
    if num > maximum:
        errors.append("`%s` 分子 %g 超过满分 %d" % (name, num, maximum))
    if num < 0:
        errors.append("`%s` 分子不能为负" % name)

    return num, errors


def verdict(total):
    """总分 → (档位, 动作)。按**下界**判定——实数被唯一确定，不留缝（小数 74.5 曾
    被闭区间兜底成「不投」，2026-10-08 审计头号项）；负分显式归末档。
    """
    for low, _high, level, action in THRESHOLDS:
        if total >= low:
            return level, action
    return THRESHOLDS[-1][2], THRESHOLDS[-1][3]


# 证据标签（exact/fuzzy/semantic 的判定方式）。叠加在 Primary/Secondary/Weak
# 能力分层之上，二者正交：能力分层控制得分，证据标签说明这条匹配是怎么判出来的。
EVIDENCE_TAGS = {"精确": "精确", "模糊": "模糊", "语义": "语义"}

# 硬门槛结论映射：含"不通过/未通过"→不通过；含"通过"→通过；
# 含"待补档案/待填"→待补档案（档案缺事实 ≠ 岗位不合格，评分放宽批新增）；
# 其余→待确认。词序即优先级：fail 先判（"不通过"含"通过"）。
GATE_PASS_WORDS = ("通过",)
GATE_FAIL_WORDS = ("不通过", "未通过")
GATE_PENDING_WORDS = ("待补档案", "待填")


def parse_hard_gates(text):
    """提取解析卡 `## 硬门槛` 小节的结论、逐条依据与字段。

    解析卡是渐进填写的，任一子块缺失时返回空结构而非抛错。
    返回：
        {
          "items": [{"key", "value"}],   # 硬门槛字段（学历/专业/届数/英语/城市）
          "conclusion": "通过"|"不通过"|"待补档案"|"待确认"|None,
          "reason": str|None,            # 不通过原因
          "details": [str],              # ### 逐条依据 下的列表项
        }
    """
    result = {"items": [], "conclusion": None, "reason": None, "details": []}

    # 二级标题判定：## 后跟空白（排除 ### 三级标题）。
    # 只取 ## 硬门槛 到下一个 ## 二级标题之间；### 逐条依据 属子块，保留在 gate_lines 内。
    h2_re = re.compile(r"^##\s")
    lines = text.splitlines()
    in_gate = False
    gate_lines = []
    for line in lines:
        stripped = line.strip()
        if h2_re.match(stripped):
            if in_gate:
                break
            if stripped.replace(" ", "").startswith("##硬门槛"):
                in_gate = True
            continue
        if in_gate:
            gate_lines.append(line)

    if not gate_lines:
        return result

    field_re = re.compile(r"^\s*(?P<key>[^:：]+)\s*[:：]\s*(?P<value>.*?)\s*$")
    in_details = False
    for line in gate_lines:
        stripped = line.strip()
        if stripped.startswith("###"):
            # 进入逐条依据子块
            in_details = "逐条依据" in stripped
            continue
        if in_details:
            # 逐条依据下的列表项
            m = re.match(r"^[-*]\s+(.*)$", stripped)
            if m:
                result["details"].append(m.group(1).strip())
            continue
        if stripped.startswith("##"):
            break
        m = field_re.match(line)
        if not m:
            continue
        key = m.group("key").strip()
        value = m.group("value").strip()
        if key == "门槛结论":
            result["conclusion"] = _classify_gate(value)
        elif key == "不通过原因":
            result["reason"] = value or None
        else:
            result["items"].append({"key": key, "value": value})

    return result


def _classify_gate(value):
    """门槛结论 → 四态：通过 / 不通过 / 待补档案 / 待确认（词序即优先级）。"""
    if not value:
        return None
    for words, label in ((GATE_FAIL_WORDS, "不通过"), (GATE_PASS_WORDS, "通过"),
                         (GATE_PENDING_WORDS, "待补档案")):
        if any(w in value for w in words):
            return label
    return "待确认"


def parse_dimension_detail(text, dimension_names):
    """提取解析卡各维度的 `### <维度名> 得分` 分项明细。

    每个维度下可能有：命中 Primary/Secondary/Weak 列表、逐条职责比对、计算说明。
    逐条命中项若带【精确/模糊/语义】标签则解析出来，缺标签时为 None（兼容旧卡片）。

    返回：
        {
          "<维度名>": {
              "hits": [
                  {
                    "level": "Primary"|"Secondary"|"Weak"|None,   # 能力分层
                    "label": str|None,                             # 词条名
                    "evidence": "精确"|"模糊"|"语义"|None,          # 证据标签
                    "note": str|None,                              # 命中说明（冒号后）
                  }, ...
              ],
              "raw": [str],   # 维度下未结构化的原文行（计算/职责比对等）
          }, ...
        }
    """
    result = {}
    lines = text.splitlines()

    # 定位各维度标题行（### 技术匹配 22/30 等），与维度名做前缀匹配
    dim_start = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("###"):
            continue
        for name in dimension_names:
            if stripped.startswith("###" + name) or stripped.startswith("### " + name):
                dim_start[name] = i
                break

    # 没有找到任何维度明细则返回空
    if not dim_start:
        return result

    dim_order = [n for n in dimension_names if n in dim_start]
    h2_re = re.compile(r"^##\s")
    for idx, name in enumerate(dim_order):
        start = dim_start[name]
        # 维度结束 = 下一个维度标题 或 下一个 ## 二级标题 或 文件尾
        end = len(lines)
        for j in range(start + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("###") and any(
                stripped.startswith("###" + n) or stripped.startswith("### " + n)
                for n in dimension_names
            ):
                end = j
                break
            if h2_re.match(stripped):
                end = j
                break
        result[name] = _parse_dim_block(lines[start + 1:end])

    return result


def _parse_dim_block(block_lines):
    """解析单个维度的明细块，返回 {hits, raw}。

    命中行兼容两种格式（`**` 加粗可选）：
      新格式（带证据标签）：- **暖通（3）【精确】**：说明
      旧格式（无标签）：     - 暖通、制冷（3）  或  - 控制 / 群控（3）——说明
    note 分隔符兼容 `：` 与 `——`。
    """
    hits = []
    raw = []
    current_level = None  # 命中列表当前属于哪个能力分层

    # 命中行：- 词条（分数）【证据】 说明；加粗可选；分数可选；说明可选
    # label 贪婪匹配到（分数）前的词条（可含 / 、 空格，排除 [*【（）】：——]）
    hit_re = re.compile(
        r"^\s*[-*]\s+"
        r"(?P<bold>\*\*)?"
        r"(?P<label>[^*【（）】：——]+)"
        r"(?:（(?P<score>[0-9.]+)\s*分?/?\s*项?）)?"
        r"(?:【(?P<evidence>精确|模糊|语义)】)?"
        r"(?P=bold)?"
        r"(?:[:：]|\s*——)?\s*(?P<note>.*?)\s*$"
    )
    evidence_re = re.compile(r"【(?P<ev>精确|模糊|语义)】")

    for line in block_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 命中 Primary/Secondary/Weak（3分/项）这样的分组行
        level_match = re.match(
            r"^命中\s*(?P<level>Primary|Secondary|Weak)", stripped)
        if level_match:
            current_level = level_match.group("level")
            continue

        m = hit_re.match(stripped)
        if m and current_level:
            # 仅在 Primary/Secondary/Weak 分组内才当作词典命中；否则归入 raw
            label = m.group("label").strip()
            evidence = m.group("evidence")
            if evidence is None:
                em = evidence_re.search(stripped)
                if em:
                    evidence = em.group("ev")
            hits.append({
                "level": current_level,
                "label": label,
                "evidence": evidence,
                "note": (m.group("note") or "").strip() or None,
            })
            continue

        # 非命中结构的行（计算、职责比对、判定、回查、无分组词条）归入 raw
        raw.append(stripped)

    return {"hits": hits, "raw": raw}


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py jd ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)


# --- 差距分析段（#307 拆往 `jd_gap`）---------------------------------------------
#
# `resolve_profile`（输入定位）/ `parse_lexicon`（词典解析）/ `gap_analysis`（比对
# 本体）连同 helper 与常量，2026-10-16 #307 整体搬进 `jd_gap`：本文件顶着 558 行
# 登记水位（只许变小），而差距分析的输入此前是三族裸露之一（JD / 简历 / 词典 /
# 母版 / 事实库全部直读，无归属无界），预检代码没处放。
#
# **单向 re-export**（不是双向依赖）：`jd_gap` 不 import 本文件，这里 import 它
# 不成环。公开名的既有 import 与 monkeypatch 面（`jd_score.gap_analysis` /
# `jd_score.LEXICON_LEVELS`——`tools/check_domains.py` 在用）零改动——CLI / MCP /
# Web / 测试都从本模块拿名字。
from .jd_gap import (gap_analysis, parse_lexicon, resolve_profile,  # noqa: E402,F401
                     LEXICON_LEVELS)
