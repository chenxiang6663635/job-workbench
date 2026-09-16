# -*- coding: utf-8 -*-
"""主题门禁：多主题最容易「某套主题某处看不清」——把三条规则写成脚本 + CI，人眼只做截图。

规则（与批 4 施工单一致，口径唯一实现，CI 与本地同跑）：

1. **parity（完整性）**：每套主题的变量键集合必须等于**本模块的 EXPECTED_KEYS**
   清单（45 键）——抓「新主题加了变量、旧主题忘了加」这类漂移；**多键同样报错**
   （新增 token 时必须显式同步：本清单 / theme.ts 的 THEME_VAR_KEYS / 主题文件）。
   注意：`index.css` 的 `:root` 只提供**默认暗主题的数值**，不是键集合的来源。
1b. **值格式**：除渐变 / 阴影类键外，每个主题键必须是 HSL 三元组（`H S% L%`）——
   键在但值坏（如写成 `#fff`）会让对比度检查静默跳过、整份主题反而全绿（独立审查）。
2. **对比度**：正文组合 ≥4.5:1、大字与图形组合 ≥3:1——
   bg/fg、card/fg、popover/fg、muted/fg、secondary/fg、primary/primary-fg、
   状态色对背景（success/warning ≥3、destructive ≥4.5）、chart-1..8 对卡片 ≥3。
3. **明度阶梯（仅暗主题）**：相邻 elevation 表面（elev-0..3-surface）相对亮度比 ≥1.12——
   暗色层次的主通道是表面明度，步进过小时卡片会「看起来都在同一高度」；
   亮色主题表面恒定、只变阴影（三件套的非对称规则），不查此项。

退出码：0 全部通过；1 有任意问题（与既有检查器一致）。用法：jobws lint themes。

加新主题后：把 src/themes/<id>.css 放好，本脚本自动扫目录；新主题变量缺失会在
parity 里点名。值的手改请跑一次本检查（对比度不许口头保证）。
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "web", "frontend", "src", "themes")
BASE_CSS = os.path.join(ROOT, "web", "frontend", "src", "index.css")

# 主题变量基准清单（45 键；与主题文件生成脚本同构）。
EXPECTED_KEYS = [
    "background", "foreground", "card", "card-foreground", "popover",
    "popover-foreground", "primary", "primary-foreground", "secondary",
    "secondary-foreground", "muted", "muted-foreground", "destructive",
    "destructive-foreground", "success", "warning", "border", "border-strong",
    "input", "ring", "highlight", "scrim", "glow-primary",
] + ["elevation-%d-surface" % i for i in range(4)] \
  + ["elevation-%d-border" % i for i in (1, 2, 3)] \
  + ["elevation-%d-shadow" % i for i in (1, 2, 3)] \
  + ["shadow-card", "shadow-elevated", "card-gradient", "hero-glow"] \
  + ["chart-%d" % i for i in range(1, 9)]

# (前景键, 背景键, 最低对比度) —— 正文 4.5:1、大字与图形 3:1
CONTRAST_CHECKS = [
    ("foreground", "background", 4.5),
    ("card-foreground", "card", 4.5),
    ("popover-foreground", "popover", 4.5),
    ("muted-foreground", "muted", 4.5),
    ("secondary-foreground", "secondary", 4.5),
    ("primary-foreground", "primary", 3.0),
    # 状态色在**卡片上**也常当文字用（徽章 / 提示条 / 警告行）——对卡 4.5；
    # 对页面底按图形门限 3.0（独立审查：rose-pine-dawn 的 success 曾 3.10 贴边）
    ("success", "background", 3.0),
    ("success", "card", 4.5),
    ("warning", "background", 3.0),
    ("warning", "card", 4.5),
    ("destructive", "background", 4.5),
    ("destructive", "card", 4.5),
]
CHART_MIN = 3.0
DARK_STEP_MIN = 1.12

# 非 HSL 三元组格式的主题键（渐变 / 阴影为自定义格式），值格式检查跳过
_NON_TRIPLE_KEYS = set(
    ["card-gradient", "hero-glow", "shadow-card", "shadow-elevated"]
    + ["elevation-%d-shadow" % i for i in (1, 2, 3)]
)

_VAR_RE = re.compile(r"--([a-zA-Z0-9-]+)\s*:\s*([^;]+);")
_HSL_RE = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$")


def parse_vars(text):
    """提取 CSS 文本里的 --key: value;（带最后一次赋值者胜出）。"""
    out = {}
    for key, value in _VAR_RE.findall(text):
        out[key] = value.strip()
    return out


def parse_hsl(value):
    """解析 `H S% L%` 三元组 → (h, s, l)；非三元组（如 var(...) 别名）返回 None。"""
    match = _HSL_RE.match(value)
    if not match:
        return None
    return tuple(float(x) for x in match.groups())


def hsl_to_rgb(h, s, l):
    h, s, l = h / 360.0, s / 100.0, l / 100.0
    if s == 0:
        return (l, l, l)
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def channel(t):
        t = t % 1.0
        if t < 1 / 6.0:
            return p + (q - p) * 6 * t
        if t < 1 / 2.0:
            return q
        if t < 2 / 3.0:
            return p + (q - p) * (2 / 3.0 - t) * 6
        return p

    return (channel(h + 1 / 3.0), channel(h), channel(h - 1 / 3.0))


def rel_luminance(rgb):
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(vars_, fg_key, bg_key):
    fg = parse_hsl(vars_.get(fg_key, ""))
    bg = parse_hsl(vars_.get(bg_key, ""))
    if fg is None or bg is None:
        return None
    l1 = rel_luminance(hsl_to_rgb(*fg))
    l2 = rel_luminance(hsl_to_rgb(*bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def audit_theme(name, variables, base_keys=None):
    """对一套主题跑三条规则，返回问题列表。"""
    problems = []
    present = set(variables.keys()) & set(EXPECTED_KEYS)
    if base_keys is not None:
        missing = sorted(base_keys - set(variables.keys()))
        if missing:
            problems.append("parity：缺变量 %s" % "、".join(missing))
    # 多键也算 parity 问题：新增 token 必须显式同步三处副本
    extra = sorted(
        key for key in set(variables.keys()) - set(EXPECTED_KEYS)
        if key != "radius" and not key.startswith(("duration-", "ease-", "font-"))
    )
    if extra:
        problems.append("parity：多出不认识的变量 %s" % "、".join(extra))
    # 值格式（独立审查 MAJOR）：键在、值坏曾让全部对比度检查静默跳过
    bad_values = [
        key for key in sorted(present)
        if key not in _NON_TRIPLE_KEYS and parse_hsl(variables[key]) is None
    ]
    if bad_values:
        problems.append("值格式：%s 不是 HSL 三元组（H S%% L%%）" % "、".join(bad_values))
    for fg_key, bg_key, minimum in CONTRAST_CHECKS:
        ratio = contrast(variables, fg_key, bg_key)
        if ratio is None:
            continue  # 键已缺：parity 会报，不重复刷屏
        if ratio < minimum:
            problems.append("对比度：%s 对 %s 为 %.2f:1（要求 ≥%.1f）"
                            % (fg_key, bg_key, ratio, minimum))
    for i in range(1, 9):
        ratio = contrast(variables, "chart-%d" % i, "card")
        if ratio is not None and ratio < CHART_MIN:
            problems.append("对比度：chart-%d 对 card 为 %.2f:1（要求 ≥%.1f）"
                            % (i, ratio, CHART_MIN))
    bg = parse_hsl(variables.get("background", ""))
    if bg is not None and rel_luminance(hsl_to_rgb(*bg)) < 0.5:
        surfaces = []
        for i in range(4):
            value = parse_hsl(variables.get("elevation-%d-surface" % i, ""))
            if value is not None:
                surfaces.append((i, rel_luminance(hsl_to_rgb(*value))))
        for (a_i, a_l), (b_i, b_l) in zip(surfaces, surfaces[1:]):
            hi, lo = max(a_l, b_l), min(a_l, b_l)
            ratio = (hi + 0.05) / (lo + 0.05)
            if ratio < DARK_STEP_MIN:
                problems.append("明度阶梯：elev-%d → elev-%d 表面比 %.3f（要求 ≥%.2f）"
                                % (a_i, b_i, ratio, DARK_STEP_MIN))
    return problems


def load_themes():
    """返回 [(名称, 变量 dict)]：先基准（index.css :root），再每套主题文件。"""
    themes = []
    with io.open(BASE_CSS, "r", encoding="utf-8") as handle:
        root_vars = parse_vars(handle.read())
    themes.append(("dark (:root)", root_vars))
    if os.path.isdir(THEMES_DIR):
        for name in sorted(os.listdir(THEMES_DIR)):
            if not name.endswith(".css"):
                continue
            path = os.path.join(THEMES_DIR, name)
            with io.open(path, "r", encoding="utf-8") as handle:
                themes.append((name[:-4], parse_vars(handle.read())))
    return themes


def check():
    themes = load_themes()
    if len(themes) < 2:
        print("找不到主题文件（%s）" % THEMES_DIR)
        return 1
    base_keys = set(EXPECTED_KEYS)
    failed = 0
    for name, variables in themes:
        problems = audit_theme(name, variables, base_keys)
        if problems:
            failed += 1
            print("[%s]" % name)
            for problem in problems:
                print("  - %s" % problem)
        else:
            print("[%s] 通过" % name)
    print("")
    if failed:
        print("共 %d/%d 套主题有问题——按上文调整色值或补齐变量后重跑。" % (failed, len(themes)))
        return 1
    print("全部 %d 套主题通过（parity / 对比度 / 明度阶梯）。" % len(themes))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="主题门禁：parity（变量齐全）、对比度（正文 4.5:1 / 大字与图形 3:1）、"
                    "暗色明度阶梯（相邻表面 ≥1.12）。无参数，跑即全检（CI 与本地同一命令）。")
    parser.parse_args(argv)  # 仅为 -h/--help 提供入口（与既有检查器一致）
    return check()


if __name__ == "__main__":
    sys.exit(main())
