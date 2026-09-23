# -*- coding: utf-8 -*-
"""源码行的扫描原语：字符串字面量、裸文本、注释、JSX 表达式。

从 `check_i18n_hardcode.py` 拆出来（2026-09-23 审计 P2）：那个文件在
`tools/size_allowlist.txt` 里是**存量豁免**（水位只许变小），而这一轮要往它的
判定里加两条盲区修复——按仓库纪律，撑大只能拆，不许抬水位。

拆出来的边界是"怎么读一行代码"（纯文本处理，不含任何判定口径）：判定仍在
`check_i18n_hardcode.py` 里，两边的测试也各自落在自己的文件上。
"""

import re

# JSX 裸文本按「连续中文块」报，而不是逐字符——一条文案报出十几个字，
# 输出会淹没真正有用的那一行。
CJK_RUN = re.compile(u"[\u4e00-\u9fff]+")

_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_escapes(text):
    r"""还原 `\u4e2d\u6587` 这类转义写法。

    不还原的话，`"\u5df2\u6302"` 就是一串 ASCII，扫描器看不见中文——而它在页面上
    渲染出来就是"已挂"。转义是合法写法，但用它绕开文案检查没有任何正当理由。
    """
    return _UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


def scan_line(line, in_block):
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
            strings.append(_decode_escapes(line[i + 1:j]))
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


def in_jsx_expression(line, pos):
    """中文是否落在同一行的 `{...}` 里（JSX 表达式 = 取数，不是文案）。

    用**括号深度**而不是"左侧最近的 `{` + 右侧最近的 `}`"配成一对：一行里有多组
    表达式时（`{count} 条记录 {total}`），旧写法会把左半边的 `{` 与右半边的 `}`
    当成一对，于是两组之间的中文被判成"表达式里的取数"而放行——而它恰恰是写给
    人看的文案（`{count}` 是可以翻的，`条记录` 不是）。
    """
    depth = 0
    for ch in line[:pos]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
    return depth > 0


def looks_like_field(text, start, end):
    """中文块是否属于「取数 / 类型声明」而不是「写给人看的字」。

    判定看紧邻字符：`it.公司`、`draft.JD文本`、`公司: string`、`面试id` 这类
    中文是标识符的一部分；JSX 文本（`<span>已挂</span>`）两边是标签符号。
    """
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    ident = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    # after 也要认 `?`：可选属性写成 `原阶段?: string`
    return (before in ident or before in "._?" or after in ident or after in "?:")
