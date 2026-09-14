# -*- coding: utf-8 -*-
r"""界面 token 一致性扫描器的**唯一**实现（CI 与 pytest 共用）。

为什么需要它：issue #17 的旧调色板清理完成后，「有没有人又把旧类名写回来」这件事
没有任何编译器能拦——Tailwind 对未知类名不报错（那条样式只是静默失效），tsc 与
eslint 也看不见类名字符串。2026-09-13 复核 #17 时九个模式全为 0，本脚本把那次的
一次性复核变成可重复执行的闸。

判定口径（四类，全部**精确匹配 + 词边界**，不做启发式猜测）：

  1. `legacy`  旧 token 名：`ink` / `good` / `warn` / `bad` 作颜色名，或 `text-accent`。
     这些键在 2026-09-11 的旧色板清理后已从 `tailwind.config.js` 移除——命中即
     「写了但没有样式的死类」。注意 `warn(?![\w-])` 不会命中新 token `text-warning`。
  2. `palette` 原生调色板刻度：`text-slate-400`、`bg-red-500` 这类绕过语义 token
     的 Tailwind 默认色（深色改版后语义色统一走 primary/success/warning/border 等）。
  3. `alpha`   white/black 的透明度写法：`ring-white/5`、`bg-black/60` 这类「去
     token 化」。**唯一的合法形态是没有透明度的 bare `bg-white` / `from-white`**：
     A4 预览纸张与 PDF iframe 的底色是「纸张是白的」这个物理隐喻，不是主题色
     （2026-09-13 逐处核过：A4Preview.tsx / Library.tsx 的 iframe、三处渐变文字的
     起点），故不在本规则范围内；反过来，带透明度的 white/black 一定是「本可以
     用 token 却被写死」的那种。
  4. `hex`    十六进制 / 函数式颜色任意值：`bg-[#0a0e17]`、`text-[rgb(…)]`——
     token 层最该拦的一种（2026-09-13 全仓库为 0）。
  另加一条 **`select-patch`**：`src/index.css` 里重新出现原生 `<select>` / `<option>`
  样式补丁即报（历史上那两条补丁是因为 Radix 之前用了原生 select，迁移后已删；
  写回来通常意味着有人绕过了 `components/ui/select`）。

刻意不做的事：不统计 `max-h-[32rem]` 这类**尺寸**任意值（当时全仓库 79 处，属视觉
刻度问题，由设计审计处理，混进来只会把这条检查变成噪音）；不按「像不像颜色」猜，
只认上面的确定性模式——检查一旦烦人就会被绕过。

允许清单：`tools/ui_tokens_allowlist.txt`，格式（一行一个文件，**片段级**）：

    components/Foo.tsx = ring-white/5|bg-black/60      # 理由必写

与 `i18n_hardcode_allowlist.txt` 同一种「现状存档」：片段翻掉/文件删掉必须同步删，
否则报「片段已不再出现 / 文件已无命中」。**不设整文件豁免**——整文件放行是
「新违规悄悄通过」的入口（i18n 侧已被实证教训过）。

用法：
    python tools/check_ui_tokens.py              # 检查，命中即退出码 1
    python tools/check_ui_tokens.py --list       # 列出全部命中（含已豁免）
    python tools/check_ui_tokens.py --root <dir> # 指定仓库根
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

SRC_REL = os.path.join("web", "frontend", "src")
SKIP_DIR_NAMES = ("node_modules", "dist")
ALLOWLIST_REL = os.path.join("tools", "ui_tokens_allowlist.txt")

_PREFIX = (r"(?<![\w-])(?:text|bg|border|ring|divide|from|to|via|fill|stroke|shadow"
           r"|outline|decoration|placeholder|caret)")

# 1) 旧 token 名（已从配置里移除的键）。`(?:/\d+)?` 让报出的片段带完整透明度
#    后缀（`bg-good/10` 报整串而不是截到 `bg-good`），负向预查仍挡住 text-warning
LEGACY = re.compile(_PREFIX + r"-(?:ink|good|warn|bad|accent)(?:/\d+)?(?![\w-])")

# 2) 原生调色板刻度
RAW_PALETTE = re.compile(
    _PREFIX
    + r"-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald"
      r"|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:/\d+)?(?![\w-])")

# 3) white/black 的透明度写法（bare 的不在此列，见模块 docstring 第 3 条）。
#    两种透明度都要认：`/5` 与任意值 `/[0.05]`——独立审查指出后者曾被漏判，
#    而「带透明度的 white/black 一定是本可以用 token 却被写死」对两者同样成立
WHITE_BLACK_ALPHA = re.compile(_PREFIX + r"-(?:white|black)/(?:\d+|\[[^\]]*\])(?![\w-])")

# 4) 十六进制 / 函数式颜色任意值
HEX_COLOR = re.compile(r"[\w:.-]+-\[(?:#|rgb|rgba|hsl|hsla)[^\]]*\](?![\w-])")

# 5) index.css 里的原生 select 补丁（选择器里出现 select / option）
SELECT_PATCH = re.compile(r"(?<![\w-])(?:select|option)(?![\w-])")

RULES = (
    ("legacy", LEGACY),
    ("palette", RAW_PALETTE),
    ("alpha", WHITE_BLACK_ALPHA),
    ("hex", HEX_COLOR),
)

def _strip_comments(text):
    """去掉注释但保留字符串字面量，且**保持行号不变**。

    两个都要成立：
    - 类名写在字符串里（`className="text-ink"`），所以不能像 i18n 扫描器那样只扫
      「字符串之外」的文本——那样会把全部命中漏掉；
    - 注释里提到旧类名（比如「旧写法 text-slate-400 已迁走」）不是违规，报了就是
      误报，而误报会让这条检查被人绕过（本仓库的既有教训）。

    `//` 在字符串内不算注释（`"https://x"`），块注释整体替换为空白字符、其中的
    换行原样保留，因此后续报出的行号仍与文件一致。
    """
    out = []
    i, n = 0, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.extend("\n" if c == "\n" else " " for c in text[i:end])
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def scan_text(text, is_css=False):
    """返回 [(行号, 命中片段, 规则名)]。

    CSS 文件只查 select 补丁：另四类规则针对 utility class，落在 CSS 里没有意义。
    """
    stripped = _strip_comments(text)
    hits = []
    if is_css:
        for lineno, line in enumerate(stripped.splitlines(), 1):
            m = SELECT_PATCH.search(line)
            if m:
                hits.append((lineno, m.group(0), "select-patch"))
        return hits
    for lineno, line in enumerate(stripped.splitlines(), 1):
        for name, pattern in RULES:
            for m in pattern.finditer(line):
                hits.append((lineno, m.group(0), name))
    return hits


def load_allowlist(root):
    """读允许清单，返回 ({文件: 片段集合}, 错误列表)。格式见模块 docstring。"""
    path = os.path.join(root, ALLOWLIST_REL)
    table = {}
    errors = []
    if not os.path.isfile(path):
        return table, errors
    with io.open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            rel, sep, frags = line.partition("=")
            if not sep:
                errors.append("清单第 %d 行缺少 `=`（格式：路径 = 片段1|片段2）" % lineno)
                continue
            table[rel.strip().replace("/", os.sep)] = set(
                x.strip() for x in frags.split("|") if x.strip())
    return table, errors


def check(root):
    """返回 (未豁免命中, 已豁免命中, 清单错误)。"""
    src = os.path.join(root, SRC_REL)
    if not os.path.isdir(src):
        return [], [], ["源码目录不存在：%s" % src]

    table, errors = load_allowlist(root)
    seen = {}
    unallowed, ok_hits = [], []

    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx", ".css")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, src)
            with io.open(full, "r", encoding="utf-8") as f:
                hits = scan_text(f.read(), is_css=name.endswith(".css"))
            if not hits:
                continue
            allow = table.get(rel, set())
            for ln, snip, kind in hits:
                seen.setdefault(rel, set()).add(snip)
                if snip in allow:
                    ok_hits.append((rel, ln, snip, kind))
                else:
                    unallowed.append((rel, ln, snip, kind))

    # 清单问题：僵尸文件 / 已不再出现的片段，都意味着下一处真命中会悄悄获得豁免
    for rel, frags in sorted(table.items()):
        actual = seen.get(rel, set())
        if not actual:
            errors.append("清单里的文件已无命中或不存在：%s" % rel.replace(os.sep, "/"))
            continue
        for frag in sorted(frags - actual):
            errors.append("清单里的片段已不再出现（可能已修掉，请删掉）：%s  →  %s"
                          % (rel.replace(os.sep, "/"), frag))
    return unallowed, ok_hits, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查前端源码里的旧调色板 / 去 token 化写法")
    parser.add_argument("--root", default=None, help="仓库根目录（默认按本文件位置推断）")
    parser.add_argument("--list", action="store_true", help="列出全部命中（含已豁免）")
    args = parser.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    unallowed, ok_hits, errors = check(root)

    if args.list:
        for rel, ln, snip, kind in ok_hits:
            print("  豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        for rel, ln, snip, kind in unallowed:
            print("未豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        print("\n合计：已豁免 %d，未豁免 %d" % (len(ok_hits), len(unallowed)))
        return 0

    for rel, ln, snip, kind in unallowed:
        print("token 违规  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
    for err in errors:
        print("清单问题  %s" % err)

    if unallowed or errors:
        print("\n界面只用语义 token（tailwind.config.js + index.css 的定义处是唯一真源）；"
              "确需保留的，登记进 %s（`路径 = 片段`）并写明理由。"
              % ALLOWLIST_REL.replace(os.sep, "/"))
        return 1
    print("token 检查通过（已豁免 %d 处）" % len(ok_hits))
    return 0


if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py lint ui-tokens ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
