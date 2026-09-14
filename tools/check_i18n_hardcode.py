# -*- coding: utf-8 -*-
"""界面文案**双向**硬编码检查的**唯一**实现（CI 与 pytest 共用）。

两个方向：① 硬编码**中文**（防"英文界面里冒中文"）；② 硬编码**英文**（防"中文界面
里冒英文"，2026-09-13 补，见下方"第四类"）。两类共用同一份清单文件、两套互不通用的
豁免段（`en:` 段只对英文检查生效），僵尸纪律一致。

为什么需要它：i18n 抽完之后，「有没有人又写死一句中文」这件事没有编译器能拦。
新增的页面/组件一个字没翻译，lint 与 tsc 都是绿的——只有真的英文用户点进去
才会发现。这条检查就是那道闸。

判定口径（与 `plans/B12_全量i18n计划_2026-09-12.md` 的五条判定原则一致）：

  1. **UI 文案必须走 `t()`**——命中即拦。
  2. **代码注释不翻**（中文注释是项目文档惯例），所以注释整段不算命中。
  3. **领域数据不翻**：阶段/批次/轮次/方向等枚举值、CSV 列名、接口中文字段名
     ——它们与 `tools/tracker.py`、工作区文件是同一套字面量，翻了才对不上。
     这类命中**逐个文件登记**在 `tools/i18n_hardcode_allowlist.txt`（带理由）。
  4. **语言包豁免**：`i18n/locales/` 本来就是中文的家。
  5. **JSX 表达式里的中文不算命中**：`{it.公司}` 是取数，不是文案；只有
     字符串字面量与 JSX 裸文本才可能是"写死给用户看的字"。

刻意**不做**的事：不按「中文长度」或「是否含某关键词」猜文案与数据——那种
启发式会把 `"已挂"`（数据）与 `"重试"`（文案）判反，制造出要么漏、要么烦的
检查，而检查一旦烦人就会被绕过。

第二类检查：**复数 key 必须传 `count`**。i18next 只有拿到 `count` 才会在
`k_one` / `k_other` 之间选；不传时它去找字面量 key `k`（不存在）→ 界面直接显示
`dash.staleSubtitle` 这串 key 名。类型系统与 lint 都拦不住（复数基名也是合法的
TranslationKey），只有打开页面才看得见——2026-09-12 的冒烟就是这么抓到的。

第三类检查：**`t("…")` 里写到的 key 必须存在**。i18next 未做类型增强时
`t(key: string)` 接受任意字符串，拼错的 key 编译期不报，界面同样退化成显示
key 名。复数基名（`xxx_one`/`xxx_other` 对应的 `xxx`）算存在。

第四类检查：**硬编码英文**（`check_english`）。方向与前三类相反——前三类防的是
"英文界面里冒中文"，而中文检查只看 CJK，于是"中文界面里冒英文"成了它（以及
tsc / eslint / UI 冒烟）的结构性盲区。范围从紧：

  * 目录：`web/frontend/src/pages/**` 与 `web/electron/**`（组件树先不动——
    扩范围前要先把误报分类，否则检查会被绕过）；
  * 形状：JSX 裸文本（`>Text<`、`<Icon /> Text`、跨行）、四个文案属性
    （`title` / `aria-label` / `alt` / `placeholder`）、Electron 的
    `title` / `message` / `detail` 键；
  * 豁免：清单里的 `en:` 段（前缀**必须小写**），片段级 + 理由。

  **刻意不覆盖**（写在这里是为了不被当成"全都查了"）：表达式里的字符串字面量
  （`placeholder={x || "imap.qq.com"}`、`{cond && "Yes"}`）、白名单之外的属性、
  非 JSX 裸文本（如 `<option>INBOX</option>`）、跨行属性值、块注释里的写法。
  这些形态与"数据 vs 文案"的边界纠缠，机器判定会先制造噪音；缺口登记在 issue 里。

用法：
    python tools/check_i18n_hardcode.py              # 检查，未豁免命中即退出码 1
    python tools/check_i18n_hardcode.py --list       # 列出全部命中（含已豁免），供重新生成清单
    python tools/check_i18n_hardcode.py --print-allowlist  # 打印清单草稿（含 `en:` 段）
    python tools/check_i18n_hardcode.py --root <dir> # 指定仓库根
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

SRC_REL = os.path.join("web", "frontend", "src")
# Electron 主进程也归这个检查管：窗口标题 / 更新对话框 / 日志同样是界面文案。
# 键以 `electron\` 前缀进同一份清单，与前端两棵树不串味。
ELECTRON_REL = os.path.join("web", "electron")
ELECTRON_KEY_PREFIX = "electron"
SKIP_DIRS = (os.path.join("i18n", "locales"), os.path.join("i18n", "index.ts"),
             # 主进程的语言包（两棵源码树各自的语言包都是"译文的家"）
             os.path.join(ELECTRON_KEY_PREFIX, "i18n.js"))
SKIP_DIR_NAMES = ("node_modules", "release")  # release = 本地打包产物（含旧文案）；对两棵源码树都生效
ALLOWLIST_REL = os.path.join("tools", "i18n_hardcode_allowlist.txt")
CJK = re.compile(u"[\u4e00-\u9fff]")

# ---- 第二类：硬编码英文（中文界面下的英文残留）----
#
# 方向与中文那类**相反**：中文检查防的是"英文界面里冒中文"，它只看 CJK，于是
# "中文界面里冒英文"是它的结构性盲区（设置页卡片标题 Provider、Electron 的窗口
# 初始标题与两个更新对话框，2026-09-13 实测确认），tsc / eslint / UI 冒烟同样
# 看不见。范围从紧起步，理由见 CONTRIBUTING：
#   目录：web/frontend/src/pages/** 与 web/electron/**
#   形状：JSX 裸文本、少数文案属性（title / aria-label / alt / placeholder）、
#         Electron 的对话框文案键（title / message / detail）
#   豁免：同一份清单的 `en:` 段（片段级 + 理由）
# 刻意不做：不扫整棵组件树、不按"有大写字母"猜品牌名、不查注释——检查一旦吵起来
# 就会被绕过，宁可窄。
# 起步范围：前端只扫 pages/**（组件树先不动），Electron 扫整棵（它只有几个文件）。
# 主进程语言包 `web/electron/i18n.js` 由 SKIP_DIRS 按路径豁免——那里是字面量的家。
EN_SCOPE_RELS = (os.path.join("web", "frontend", "src", "pages"), ELECTRON_REL)
EN_ALLOWLIST_PREFIX = "en:"
# 至少 3 个连续字母才算"一句英文"：`a` / `OK` / `ID` 这类不算文案
EN_WORD = re.compile(r"[A-Za-z]{3,}")
# "像标签的开始"：`<div` / `</div` / `<>`。用来确认裸文本两侧的尖括号是 JSX，
# 而不是比较运算符（`len > min && len < max` 的形状与 `>Text<` 完全一样）。
TAG_LIKE = re.compile(r"<[A-Za-z/]")
# 同行 JSX 裸文本：`>Text<`
EN_JSX_INLINE = re.compile(r">\s*([A-Za-z][^<>{}]*[A-Za-z0-9'’.!?])\s*<")
# 行尾裸文本：`<Icon /> Provider`（`/>` 之后没跟着尖括号，文案就在这一行结尾）
EN_JSX_TAIL = re.compile(r"(?:/>|>)\s*([A-Za-z][^<>{}]*?)\s*$")
# 文案属性：只有写成字面量的才命中（`title={t("…")}` 不是命中）
EN_TEXT_ATTR = re.compile(r"""\b(title|aria-label|alt|placeholder)\s*=\s*"([^"]*)\"""")
# Electron 窗口/对话框的文案键（可另起一行，也可跟在 `{` / `,` 之后）
EN_COPY_KEY = re.compile(r"""(?:^|[{,]\s*)(title|message|detail)\s*:\s*"([^"]*)\"""")


def _strip_trailing_tag(text):
    """去掉行尾的 `</Tag>`，留下裸文本本体。"""
    return re.sub(r"</[A-Za-z][^>]*>\s*$", "", text).strip()


def _without_comments(line):
    """去掉行内注释，**保留字符串字面量**——属性值就在字符串里。

    为什么不复用 `_scan_line` 的 plain：它把字符串一并剥掉了，而文案属性要的正是
    字符串里的值。这里只去注释，并且认引号——`"https://x"` 里的 `//` 不是注释
    （与中文检查同一条教训）。单行块注释 `/* title="X" */` 也在这里被去掉：
    只看"行首是否在块注释中"是拦不住它的（进函数即闭合，标记又变回 False）。
    """
    out = []
    i, n = 0, len(line)
    quote = None
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(line[i + 1])
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
        if line.startswith("//", i):
            break
        if line.startswith("/*", i):
            end = line.find("*/", i + 2)
            if end < 0:
                break
            out.append(" " * (end + 2 - i))
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def find_hardcoded_english(text):
    """返回 [(行号, 片段, 种类)]，种类两种：

        jsx-text    JSX 裸文本里的英文（`<span>Provider</span>` / `/> Provider`）
        text-attr   文案属性或 Electron 文案键里的英文字面量

    两种都**可能是正当的数据**（文件名、品牌名、示例值），所以都可按片段豁免——
    与中文检查"裸文本永不放行"不同：那里裸文本必然是写给人看的中文，而这里
    `<code>config/failure_keywords.txt</code>` 这种确实该保持原样。代价是豁免
    必须写清理由，且只放行登记过的那一条片段。
    """
    hits = []
    lines = text.splitlines()
    in_block = False
    prev_plain = ""
    for lineno, line in enumerate(lines, 1):
        was_in_block = in_block
        _strings, plain, in_block = _scan_line(line, in_block)
        # 1) 同行裸文本：`>Text<`。要求这个 `>` 属于标签（前面出现过 `<Tag` /
        #    `</` / `<>`）——否则 `len > min && len < max` 这类比较会被成片误报
        #    （独立审查 m2：`pages/**` 现在还只有 .tsx，但 Electron 树是 .js）。
        for m in EN_JSX_INLINE.finditer(plain):
            if not TAG_LIKE.search(plain[:m.start()]):
                continue
            snippet = m.group(1).strip()
            if EN_WORD.search(snippet):
                hits.append((lineno, snippet, "jsx-text"))
        # 1b) 行尾裸文本：`<Icon /> Provider`（同样要求前面出现的是标签，而不是 `a > b`）
        for m in EN_JSX_TAIL.finditer(plain):
            if not TAG_LIKE.search(plain[:m.start()]):
                continue
            snippet = m.group(1).strip()
            if EN_WORD.search(snippet):
                hits.append((lineno, snippet, "jsx-text"))
        # 2) 跨行裸文本：上一行以 `>` 收尾、本行是纯文本（可带收尾标签）
        #    `=>` / `->` / `>=` 的收尾不是标签：链式调用与 JSX 事件处理器的
        #    续行都会被它们带进来（首次在仓库试跑时抓到的两处误报就是这么来的）
        prev_tail = prev_plain.rstrip()
        prev_closes_tag = (prev_tail.endswith(">")
                           and not prev_tail.endswith(("=>", "->", ">=", "<=")))
        stripped = _strip_trailing_tag(plain.strip())
        if (prev_closes_tag and stripped
                and not stripped.startswith(("<", "{", "}", ")"))
                and not re.search(r"[<>{}]", stripped) and EN_WORD.search(stripped)):
            hits.append((lineno, stripped, "jsx-text"))
        # 3) / 4) 字面量型文案。匹配在"去过注释"的文本上做：注释不翻是仓库口径，
        #    而块注释（含单行 `/* … */`）与行注释都得一起排除。
        if not was_in_block:
            code = _without_comments(line)
            for m in list(EN_TEXT_ATTR.finditer(code)) + list(EN_COPY_KEY.finditer(code)):
                value = m.group(2).strip()
                if EN_WORD.search(value):
                    hits.append((lineno, value, "text-attr"))
        prev_plain = plain
    return hits


def check_english(root):
    """硬编码英文检查。返回 (未豁免命中, 已豁免命中, 清单错误)。

    清单键与中文那套**写法一致**：前端命中是相对 `web/frontend/src` 的路径
    （如 `pages/Settings.tsx`），Electron 命中带 `electron/` 前缀（如
    `electron/main.js`）。两套豁免读同一份清单文件，键的写法必须一样——
    否则"照着上一行抄"写出来的条目永远对不上，只会变成一条僵尸。
    """
    table, errors = load_allowlist(root, prefix=EN_ALLOWLIST_PREFIX)
    seen = {}
    unallowed, ok_hits = [], []
    # (被遍历的目录, 清单键的基准目录, 键前缀)
    targets = (
        (os.path.join(root, SRC_REL, "pages"), os.path.join(root, SRC_REL), ""),
        (os.path.join(root, ELECTRON_REL), os.path.join(root, ELECTRON_REL),
         ELECTRON_KEY_PREFIX),
    )

    for base, key_base, prefix in targets:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in sorted(filenames):
                if not name.endswith((".tsx", ".ts", ".js")):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, key_base)
                if prefix:
                    rel = os.path.join(prefix, rel)
                if any(rel.startswith(skip) for skip in SKIP_DIRS):
                    continue
                with io.open(full, "r", encoding="utf-8") as f:
                    hits = find_hardcoded_english(f.read())
                if not hits:
                    continue
                allow = table.get(rel, set())
                for ln, snip, kind in hits:
                    seen.setdefault(rel, set()).add(snip)
                    if snip in allow:
                        ok_hits.append((rel, ln, snip, kind))
                    else:
                        unallowed.append((rel, ln, snip, kind))

    # 与中文清单同一套僵尸纪律：文件清了、片段翻掉了，都要同步删条目
    for rel, frags in sorted(table.items()):
        actual = seen.get(rel, set())
        if not actual:
            errors.append("英文清单里的文件已无命中或不存在：%s" % rel.replace(os.sep, "/"))
            continue
        for frag in sorted(frags - actual):
            errors.append("英文清单里的片段已不再出现（可能已翻译，请删掉）：%s  →  %s"
                          % (rel.replace(os.sep, "/"), frag))
    return unallowed, ok_hits, errors
# JSX 裸文本按「连续中文块」报，而不是逐字符——一条文案报出十几个字，
# 输出会淹没真正有用的那一行。
CJK_RUN = re.compile(u"[\u4e00-\u9fff]+")


def _scan_line(line, in_block):
    """把一行拆成 (字符串字面量列表, 非字符串文本, in_block)。

    逐字符扫而不是正则去注释：`"https://x"` 里的 `//` 不是注释，
    `"/*"` 同理——用正则去注释会把这些行改成另一行代码，检查随即失真。
    """
    strings = []
    plain = []
    i = 0
    n = len(line)
    while i < n:
        if in_block:
            end = line.find("*/", i)
            if end < 0:
                return strings, "".join(plain), True
            in_block = False
            i = end + 2
            continue
        ch = line[i]
        if ch in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == ch:
                    break
                j += 1
            strings.append(line[i + 1:j])
            i = j + 1
            continue
        if line.startswith("//", i):
            break
        if line.startswith("/*", i):
            in_block = True
            i += 2
            continue
        plain.append(ch)
        i += 1
    return strings, "".join(plain), in_block


def _in_jsx_expression(line, pos):
    """中文是否落在同一行的 `{...}` 里（JSX 表达式 = 取数，不是文案）。"""
    left = line.rfind("{", 0, pos)
    if left < 0:
        return False
    right = line.find("}", pos)
    return right > left


def _looks_like_field(text, start, end):
    """中文块是否属于「取数 / 类型声明」而不是「写给人看的字」。

    判定看紧邻字符：`it.公司`、`draft.JD文本`、`公司: string`、`面试id` 这类
    中文是标识符的一部分；JSX 文本（`<span>已挂</span>`）两边是标签符号。
    """
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    ident = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    # after 也要认 `?`：可选属性写成 `原阶段?: string`
    return (before in ident or before in "._?" or after in ident or after in "?:")


def find_hardcoded(text):
    """返回 [(行号, 片段, 种类)]，种类三种：

        string     字符串字面量里的中文（可能是数据，也可能是写死的文案）
        field      取数 / 类型声明里的中文（`it.公司`、`公司: string`）——数据
        jsx-text   JSX 裸文本里的中文（`<span>已挂</span>`）——一定是文案

    **清单只放行前两类**：jsx-text 没有正当理由，一旦允许它借同名数据片段
    放行，"往已豁免文件里再加一句写死的字"这个洞就又回来了。
    """
    hits = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        strings, plain, in_block = _scan_line(line, in_block)
        for s in strings:
            if CJK.search(s):
                hits.append((lineno, s.strip(), "string"))
        for m in CJK_RUN.finditer(plain):
            if _in_jsx_expression(line, m.start()):
                continue
            # 偏移要相对 plain（字符串与注释已被摘掉），不是原始行
            kind = "field" if _looks_like_field(plain, m.start(), m.end()) else "jsx-text"
            hits.append((lineno, m.group(0), kind))
    return hits


# 三种引号都认（项目风格是双引号，但单引号与模板串不该因此漏检）
PLURAL_CALL = re.compile(r"""\bt\(\s*['"`]([^'"`]+)['"`]""", re.S)


def _plural_bases(root):
    """源语言包里所有复数 key 的基名（xxx_one / xxx_other → xxx）。"""
    path = os.path.join(root, SRC_REL, "i18n", "locales", "zh-CN.ts")
    if not os.path.isfile(path):
        return set()
    with io.open(path, "r", encoding="utf-8") as f:
        keys = re.findall(r'^\s*"([^"]+)":', f.read(), re.M)
    return set(k.rsplit("_", 1)[0] for k in keys if k.endswith(("_one", "_other")))


def find_plural_without_count(root):
    """返回 [(文件, 行号, key)]：复数 key 的调用点漏传了 count。"""
    bases = _plural_bases(root)
    if not bases:
        return []
    src = os.path.join(root, SRC_REL)
    out = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), src)
            if any(rel.startswith(skip) for skip in SKIP_DIRS):
                continue
            with io.open(os.path.join(dirpath, name), "r", encoding="utf-8") as f:
                text = f.read()
            for m in PLURAL_CALL.finditer(text):
                if m.group(1) not in bases:
                    continue
                # 取出这次调用的参数文本：t("k" 之后扫到配平的右括号
                i, depth = m.end(), 1
                while i < len(text) and depth:
                    if text[i] == "(":
                        depth += 1
                    elif text[i] == ")":
                        depth -= 1
                    i += 1
                if not re.search(r"\bcount\s*:", text[m.end():i]):
                    out.append((rel, text[:m.start()].count("\n") + 1, m.group(1)))
    return out


CALL_KEY = re.compile(r"""\bt\(\s*['"`]([^'"`]+)['"`]""")


def find_missing_keys(root):
    """返回 [(文件, 行号, key)]：代码里 t("…") 写到、但源语言包里没有的 key。

    为什么需要：i18next 没做类型增强时 `t(key: string)` 接受任意字符串，拼错的
    key 编译期拦不住——界面会退化成直接显示 key 名（fallbackLng 也找不到时）。
    这是与「复数漏 count」并列的第二类盲区，都只有打开那一页才看得见。
    复数基名（xxx_one/xxx_other 对应的 xxx）算存在。
    """
    src = os.path.join(root, SRC_REL)
    locale = os.path.join(src, "i18n", "locales", "zh-CN.ts")
    if not os.path.isfile(locale):
        return []
    with io.open(locale, "r", encoding="utf-8") as f:
        raw = f.read()
    keys = set(re.findall(r'^\s*"([^"]+)":', raw, re.M))
    keys |= set(k.rsplit("_", 1)[0] for k in keys if k.endswith(("_one", "_other")))

    out = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), src)
            if any(rel.startswith(skip) for skip in SKIP_DIRS):
                continue
            with io.open(os.path.join(dirpath, name), "r", encoding="utf-8") as f:
                text = f.read()
            for m in CALL_KEY.finditer(text):
                key = m.group(1)
                # 模板串插值键（`domain.${group}.${raw}`）静态不可判定：拼错的
                # 字面量 key 才是这类检查的目标，带 ${} 的键跳过而非误报——
                # 否则「值→文案」的动态映射（lib/domainLabels.ts）永远过不了。
                if "${" in key:
                    continue
                if key not in keys:
                    out.append((rel, text[:m.start()].count("\n") + 1, key))
    return out


def load_allowlist(root, prefix=""):
    """读允许清单。格式（一行一个文件）：

        components/Foo.tsx = 已挂|已放弃|待投      # 阶段枚举（数据）
        en:pages/Settings.tsx = Provider          # 品牌名（英文检查的豁免）

    **只放行列出来的片段，不是整文件放行**。这一条是被实证逼出来的：
    2026-09-12 的未提交审查里，一个"整文件豁免"的已翻译文件里藏着 4 处
    漏翻（列头、差异标签、按钮 tooltip）——整文件豁免就是"新漏翻悄悄通过"
    的入口。片段级放行的代价是清单长一些，换来的是"往同一文件里再加一句
    硬编码文案"必然报错。

    `prefix` 用来把两套豁免分开：中文检查读**不带** `en:` 的条目，英文检查
    （`prefix="en:"`）只读带 `en:` 的条目。同一行里的 `en:` 段永远不会成为
    对方那套的放行依据——否则"某句中文是阶段枚举"会顺手放过同一文件的英文文案。

    `#` 之后是理由（人看的，不参与匹配）。返回 ({文件: 片段集合}, 错误列表)。
    """
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
            key = rel.strip()
            if prefix:
                if not key.startswith(prefix):
                    continue
                key = key[len(prefix):].strip()
            elif key.startswith(EN_ALLOWLIST_PREFIX):
                # 另一套豁免：对中文检查来说它既不是文件、也不该报"僵尸"
                continue
            # **合并**而不是赋值：同一文件允许分多行登记（每行写自己的理由）。
            # 赋值会让后面的行悄悄覆盖前面的——"清单里写了、实际没放行"，
            # 而且不报任何错（英文段尤其需要分行，见文件里的 `en:` 段）。
            table.setdefault(key.replace("/", os.sep), set()).update(
                x.strip() for x in frags.split("|") if x.strip())
    return table, errors


def check(root):
    """返回 (未豁免命中, 已豁免命中, 复数漏 count, 不存在的 key, 清单错误)。"""
    src = os.path.join(root, SRC_REL)
    if not os.path.isdir(src):
        return [], [], [], [], ["源码目录不存在：%s" % src]

    table, errors = load_allowlist(root)
    seen = {}
    unallowed, ok_hits = [], []

    # 两棵源码树：前端 src（清单键 = 相对 src 的路径）与 Electron 主进程
    # （清单键带 `electron\` 前缀）。Electron 目录可缺席（纯 Web 部署 / 测试树）。
    roots = [(src, "")]
    electron = os.path.join(root, ELECTRON_REL)
    if os.path.isdir(electron):
        roots.append((electron, ELECTRON_KEY_PREFIX))
    for base, prefix in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in sorted(filenames):
                if not name.endswith((".ts", ".tsx", ".js")):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, base)
                if prefix:
                    rel = os.path.join(prefix, rel)
                if any(rel.startswith(skip) for skip in SKIP_DIRS):
                    continue
                with io.open(full, "r", encoding="utf-8") as f:
                    hits = find_hardcoded(f.read())
                if not hits:
                    continue
                allow = table.get(rel, set())
                for ln, snip, kind in hits:
                    seen.setdefault(rel, set()).add(snip)
                    # **jsx-text 永不放行**。清单若不分类别地放行，`<span>已挂</span>`
                    # 这类裸文本会借着「已挂」这条数据豁免溜过去（独立审查发现）。
                    # 真实文件名那种情况（JobDetailView 的 解析卡.md）用 {"…"} 包成
                    # 字符串字面量即可。
                    if kind != "jsx-text" and snip in allow:
                        ok_hits.append((rel, ln, snip, kind))
                    else:
                        unallowed.append((rel, ln, snip, kind))

    # 清单问题（两类，都会让下一处真命中悄悄获得豁免）：
    #   1. 文件已不存在或已清干净——整条留着是僵尸；
    #   2. 片段列了却没出现——多半是那句中文已经翻掉了，留着它就等于给
    #      将来同名的一句中文预授权。
    for rel, frags in sorted(table.items()):
        actual = seen.get(rel, set())
        if not actual:
            errors.append("清单里的文件已无命中或不存在：%s" % rel.replace(os.sep, "/"))
            continue
        for frag in sorted(frags - actual):
            errors.append("清单里的片段已不再出现（可能已翻译，请删掉）：%s  →  %s"
                          % (rel.replace(os.sep, "/"), frag))
    return (unallowed, ok_hits, find_plural_without_count(root),
            find_missing_keys(root), errors)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="检查界面源码里的硬编码文案（中文 + 英文）")
    parser.add_argument("--root", default=None, help="仓库根目录（默认按本文件位置推断）")
    parser.add_argument("--list", action="store_true", help="列出全部命中（含已豁免）")
    parser.add_argument("--print-allowlist", dest="print_allowlist", action="store_true",
                        help="按当前命中打印清单草稿（复核后写进清单文件，理由要人写）")
    args = parser.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    unallowed, ok_hits, plural, missing_keys, errors = check(root)
    en_unallowed, en_ok, en_errors = check_english(root)
    errors = errors + en_errors

    if args.print_allowlist:
        by_file = {}
        for rel, _ln, snip, _kind in ok_hits + unallowed:
            by_file.setdefault(rel, set()).add(snip)
        for rel in sorted(by_file):
            print("%s = %s"
                  % (rel.replace(os.sep, "/"), "|".join(sorted(by_file[rel]))))
        en_by_file = {}
        for rel, _ln, snip, _kind in en_ok + en_unallowed:
            en_by_file.setdefault(rel, set()).add(snip)
        for rel in sorted(en_by_file):
            print("%s%s = %s"
                  % (EN_ALLOWLIST_PREFIX, rel.replace(os.sep, "/"),
                     "|".join(sorted(en_by_file[rel]))))
        return 0

    if args.list:
        for rel, ln, snip, kind in ok_hits:
            print("  豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        for rel, ln, snip, kind in unallowed:
            print("未豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        for rel, ln, snip, kind in en_ok:
            print("  豁免英文  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        for rel, ln, snip, kind in en_unallowed:
            print("未豁免英文  %s:%d  [%s] %s"
                  % (rel.replace(os.sep, "/"), ln, kind, snip))
        print("\n合计：中文已豁免 %d、未豁免 %d；英文已豁免 %d、未豁免 %d"
              % (len(ok_hits), len(unallowed), len(en_ok), len(en_unallowed)))
        return 0

    for rel, ln, snip, kind in unallowed:
        print("硬编码中文  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
    for rel, ln, snip, kind in en_unallowed:
        print("硬编码英文  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
    for rel, ln, key in plural:
        print("复数缺 count  %s:%d  %s" % (rel.replace(os.sep, "/"), ln, key))
    for rel, ln, key in missing_keys:
        print("key 不存在  %s:%d  %s" % (rel.replace(os.sep, "/"), ln, key))
    for err in errors:
        print("清单问题  %s" % err)

    if unallowed or en_unallowed or plural or missing_keys or errors:
        print("\n新增界面文案请走 t()（key 加进 i18n/locales/zh-CN.ts 与 en.ts）；"
              "确属数据/字段名/列名/文件名的，登记进 %s 并写明理由"
              "（中文命中写 `路径 = 片段`，英文命中写 `%s路径 = 片段`）；"
              "复数 key（_one/_other）必须传 count；t() 里的 key 必须真实存在"
              "——任何一类漏了，界面都会显示 key 名或冒出另一种语言的字。"
              % (ALLOWLIST_REL.replace(os.sep, "/"), EN_ALLOWLIST_PREFIX))
        return 1
    print("i18n 检查通过（中文已豁免 %d 处、英文已豁免 %d 处；复数调用点均带 count）"
          % (len(ok_hits), len(en_ok)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
