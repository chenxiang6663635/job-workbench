# -*- coding: utf-8 -*-
"""校验 JD 解析卡的评分小节是否自洽，并按阈值输出结论档位。

本脚本不打分——评分由 AI 读 JD 原文与 CODEBUDDY.md 后填进解析卡。
脚本只做三件事：校验各维度分子不超过分母、校验四项之和等于总分、套阈值出档位。
这样设计是为了让评分标准可改在 Markdown 里，改完可以对历史 JD 批量重算。

用法：
    python tools/jd_score.py <解析卡路径>
    python tools/jd_score.py 01_岗位池/某某公司_某岗位/解析卡.md

退出码：0 成功，1 校验失败或文件错误。
输出到 stdout 的是 Markdown 片段，供命令直接回填解析卡的「结论」小节。
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = os.path.join(ROOT, "template", "profiles")
DEFAULT_WORKSPACE = os.path.join(ROOT, "personal")

# 维度名 -> 满分。顺序即解析卡中的书写顺序
DIMENSIONS = [
    ("技术匹配", 30),
    ("经历匹配", 25),
    ("方向契合", 30),
    ("培养与稳定性", 15),
]

# (下界, 上界, 档位, 动作)
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
    for low, high, level, action in THRESHOLDS:
        if low <= total <= high:
            return level, action
    return THRESHOLDS[-1][2], THRESHOLDS[-1][3]


# 证据标签（exact/fuzzy/semantic 的判定方式）。叠加在 Primary/Secondary/Weak
# 能力分层之上，二者正交：能力分层控制得分，证据标签说明这条匹配是怎么判出来的。
EVIDENCE_TAGS = {"精确": "精确", "模糊": "模糊", "语义": "语义"}

# 硬门槛三态结论映射：含"通过"→通过；含"不通过/未通过"→不通过；其余→待确认
GATE_PASS_WORDS = ("通过",)
GATE_FAIL_WORDS = ("不通过", "未通过")


def parse_hard_gates(text):
    """提取解析卡 `## 硬门槛` 小节的结论、逐条依据与字段。

    解析卡是渐进填写的，任一子块缺失时返回空结构而非抛错。
    返回：
        {
          "items": [{"key", "value"}],   # 硬门槛字段（学历/专业/届数/英语/城市）
          "conclusion": "通过"|"不通过"|"待确认"|None,
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
    """把门槛结论文本映射为三态：通过 / 不通过 / 待确认。"""
    if not value:
        return None
    for w in GATE_FAIL_WORDS:
        if w in value:
            return "不通过"
    for w in GATE_PASS_WORDS:
        if w in value:
            return "通过"
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


def resolve_profile(workspace, domain=None, direction=None):
    """定位领域插件与方向文件。

    查找顺序：工作区 config/（用户可能有自己的副本） -> template/profiles/<domain>/
    返回 (插件目录, 方向文件路径, 警告列表)。
    """
    warnings = []

    # 确定 domain
    if not domain:
        ws_domain = os.path.join(workspace, "config", "profile.md")
        if os.path.isfile(ws_domain):
            candidates = [os.path.basename(os.path.dirname(workspace))]
        else:
            candidates = sorted(d for d in os.listdir(PROFILES)
                                if os.path.isdir(os.path.join(PROFILES, d))) \
                if os.path.isdir(PROFILES) else []
        if not candidates:
            warnings.append("未找到任何领域插件，评分缺少词典依据")
            return None, None, warnings
        domain = candidates[0]
        warnings.append("未指定 --domain，回退使用第一个插件 `%s`" % domain)

    # 插件目录：工作区优先，其次 template
    ws_profile = os.path.join(workspace, "config")
    profile_dir = ws_profile if os.path.isfile(
        os.path.join(ws_profile, "profile.md")) else os.path.join(PROFILES, domain)

    if not os.path.isdir(profile_dir):
        warnings.append("找不到领域插件 `%s`（已查找 %s 与 %s）"
                        % (domain, ws_profile, os.path.join(PROFILES, domain)))
        return None, None, warnings

    # 方向文件
    dir_dir = os.path.join(profile_dir, "directions")
    if direction:
        path = os.path.join(dir_dir, "%s.md" % direction)
        if os.path.isfile(path):
            return profile_dir, path, warnings
        warnings.append("方向 `%s` 不存在于插件 `%s`" % (direction, domain))

    if os.path.isdir(dir_dir):
        available = sorted(f for f in os.listdir(dir_dir) if f.endswith(".md"))
        if available:
            fallback = available[0][:-3]
            if direction:
                warnings.append("回退使用方向 `%s`，结论仅供参考" % fallback)
            return profile_dir, os.path.join(dir_dir, available[0]), warnings

    warnings.append("插件 `%s` 下没有找到任何方向配置" % domain)
    return profile_dir, None, warnings


def main():
    parser = argparse.ArgumentParser(description="校验 JD 解析卡评分并输出结论档位")
    # --show-profile 只查插件路径，不需要解析卡，故设为可选
    parser.add_argument("card", nargs="?", help="解析卡路径")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    parser.add_argument("--domain", help="领域插件 ID，如 hvac-cooling")
    parser.add_argument("--direction", help="方向 ID，如 datacenter / hvac")
    parser.add_argument("--show-profile", action="store_true",
                        help="打印命中的插件与方向文件路径后退出")
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)

    if not args.card and not args.show_profile:
        parser.error("需要提供解析卡路径，或使用 --show-profile")

    if args.show_profile:
        profile_dir, direction_file, warns = resolve_profile(
            workspace, args.domain, args.direction)
        print("插件目录：%s" % (profile_dir or "（未找到）"))
        print("方向文件：%s" % (direction_file or "（未找到）"))
        print("共用词典：%s" % (os.path.join(profile_dir, "lexicon.md")
                           if profile_dir else "（未找到）"))
        for w in warns:
            print("提示：%s" % w)
        return 0 if profile_dir and direction_file else 1

    path = args.card
    if not os.path.isfile(path):
        print("错误：找不到解析卡 `%s`" % path)
        return 1

    with io.open(path, "r", encoding="utf-8") as f:
        text = f.read()

    fields = parse_score_section(text)

    if not fields:
        print("错误：解析卡中找不到 `## 评分` 小节，或其下没有 `key: value` 行")
        return 1

    errors = []
    values = {}
    for name, maximum in DIMENSIONS:
        raw = fields.get(name, "")
        num, errs = parse_dimension(raw, name, maximum)
        errors.extend(errs)
        if num is not None and not errs:
            values[name] = num

    # 总分校验
    total_raw = fields.get("总分", "")
    total = None
    if not total_raw:
        errors.append("`总分` 未填写")
    else:
        m = re.match(r"^\d+(?:\.\d+)?$", total_raw)
        if not m:
            errors.append("`总分: %s` 格式错误，应为纯数字" % total_raw)
        else:
            total = float(total_raw)
            if total > TOTAL_MAX:
                errors.append("总分 %g 超过满分 %d" % (total, TOTAL_MAX))

    # 加总一致性：只在四个维度都成功解析时才校验
    if len(values) == len(DIMENSIONS) and total is not None:
        calc = sum(values.values())
        if abs(calc - total) > 1e-6:
            errors.append(
                "加总不一致：四项之和为 %g，但总分为 %g（差 %g）"
                % (calc, total, calc - total)
            )

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n请修正解析卡的 `## 评分` 小节后重新运行。")
        return 1

    # 输出结论
    level, action = verdict(total)

    print("## 评分明细\n")
    print("| 维度 | 得分 |")
    print("|---|---:|")
    for name, maximum in DIMENSIONS:
        print("| %s | %g / %d |" % (name, values[name], maximum))
    print("| **总分** | **%g / %d** |" % (total, TOTAL_MAX))
    print("")
    print("## 结论\n")
    print("- **档位**：%s" % level)
    print("- **下一步**：%s" % action)

    return 0


if __name__ == "__main__":
    sys.exit(main())
