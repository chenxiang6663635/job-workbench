# -*- coding: utf-8 -*-
"""界面硬编码中文检查的**唯一**实现（CI 与 pytest 共用）。

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

用法：
    python tools/check_i18n_hardcode.py              # 检查，未豁免命中即退出码 1
    python tools/check_i18n_hardcode.py --list       # 列出全部命中（含已豁免），供重新生成清单
    python tools/check_i18n_hardcode.py --print-allowlist  # 打印清单草稿
    python tools/check_i18n_hardcode.py --root <dir> # 指定仓库根
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

SRC_REL = os.path.join("web", "frontend", "src")
SKIP_DIRS = (os.path.join("i18n", "locales"), os.path.join("i18n", "index.ts"))
ALLOWLIST_REL = os.path.join("tools", "i18n_hardcode_allowlist.txt")
CJK = re.compile(u"[\u4e00-\u9fff]")
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
                if m.group(1) not in keys:
                    out.append((rel, text[:m.start()].count("\n") + 1, m.group(1)))
    return out


def load_allowlist(root):
    """读允许清单。格式（一行一个文件）：

        components/Foo.tsx = 已挂|已放弃|待投      # 阶段枚举（数据）

    **只放行列出来的片段，不是整文件放行**。这一条是被实证逼出来的：
    2026-09-12 的未提交审查里，一个"整文件豁免"的已翻译文件里藏着 4 处
    漏翻（列头、差异标签、按钮 tooltip）——整文件豁免就是"新漏翻悄悄通过"
    的入口。片段级放行的代价是清单长一些，换来的是"往同一文件里再加一句
    硬编码文案"必然报错。

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
            table[rel.strip().replace("/", os.sep)] = set(
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

    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, src)
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
    parser = argparse.ArgumentParser(description="检查前端源码里的硬编码中文")
    parser.add_argument("--root", default=None, help="仓库根目录（默认按本文件位置推断）")
    parser.add_argument("--list", action="store_true", help="列出全部命中（含已豁免）")
    parser.add_argument("--print-allowlist", dest="print_allowlist", action="store_true",
                        help="按当前命中打印清单草稿（复核后写进清单文件，理由要人写）")
    args = parser.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    unallowed, ok_hits, plural, missing_keys, errors = check(root)

    if args.print_allowlist:
        by_file = {}
        for rel, _ln, snip, _kind in ok_hits + unallowed:
            by_file.setdefault(rel, set()).add(snip)
        for rel in sorted(by_file):
            print("%s = %s"
                  % (rel.replace(os.sep, "/"), "|".join(sorted(by_file[rel]))))
        return 0

    if args.list:
        for rel, ln, snip, kind in ok_hits:
            print("  豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        for rel, ln, snip, kind in unallowed:
            print("未豁免  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
        print("\n合计：已豁免 %d，未豁免 %d" % (len(ok_hits), len(unallowed)))
        return 0

    for rel, ln, snip, kind in unallowed:
        print("硬编码中文  %s:%d  [%s] %s" % (rel.replace(os.sep, "/"), ln, kind, snip))
    for rel, ln, key in plural:
        print("复数缺 count  %s:%d  %s" % (rel.replace(os.sep, "/"), ln, key))
    for rel, ln, key in missing_keys:
        print("key 不存在  %s:%d  %s" % (rel.replace(os.sep, "/"), ln, key))
    for err in errors:
        print("清单问题  %s" % err)

    if unallowed or plural or missing_keys or errors:
        print("\n新增界面文案请走 t()（key 加进 i18n/locales/zh-CN.ts 与 en.ts）；"
              "确属数据/字段名/列名的，登记进 %s（`路径 = 片段`）并写明理由；"
              "复数 key（_one/_other）必须传 count；t() 里的 key 必须真实存在"
              "——这三类漏了任何一个，界面都会直接显示 key 名。"
              % ALLOWLIST_REL.replace(os.sep, "/"))
        return 1
    print("i18n 检查通过（已豁免 %d 处，复数调用点均带 count）" % len(ok_hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
