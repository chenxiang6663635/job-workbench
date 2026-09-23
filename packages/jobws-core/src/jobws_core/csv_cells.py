# -*- coding: utf-8 -*-
"""CSV 单元格的**唯一**出口：`workspace_io.atomic_write_csv` 与 tracker 的时间线
追加（history.csv）两个写入点共用它。

这些字符开头的单元格会被 Excel / WPS / LibreOffice 当公式或命令执行，而追踪表
里的「备注」「新值」可以是用户粘贴的邮件原文、也可以来自各方解析结果——把它们
原样写进 CSV，等于把「打开导出文件」变成「执行一段不受控的表达式」。前置一个
单引号后，表格软件按文本显示它；代价只有一个字符，读回来仍是同一份数据。

为什么不内联在 `workspace_io` 里：那里已经是 300 行规模闸门的上限，而这个
函数是「策略」不是「写入原语」——它还要被另一个写入点（追加路径）引用。
"""

# `= + - @` 是公式前缀；Tab 与 CR 在部分解析器里有特殊含义，一并中和
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _escaped_form(text):
    """文本是否已经是「转义形态」（`'` + 公式前缀）。"""
    return text[:1] == "'" and text[1:2] in _FORMULA_PREFIXES


def csv_cell(value):
    """单元格出口：None → 空串；危险开头 → 前置单引号。

    `_escaped_form` 那一支是为了让**写读构成真正的对合**（2026-09-23 二轮审计）：
    用户本来就想留的 `'- 待定` 若不再补一层引号，读侧会把它当成转义还原成 `- 待定`
    ——用户看到自己写的内容被改掉。补一层后写读两侧可逆。
    """
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_PREFIXES or _escaped_form(text):
        return "'" + text
    return text


def csv_read_cell(value):
    """单元格入口：还原写入时中和掉的单引号（`'- 待定` → `- 待定`）。

    为什么必须成对：中和是**为了 Excel**，不是为了改用户数据——读回来若少了这一步，
    备注会永远多一个引号（界面、CLI、导出、下一次写回都带着它），而"写进去什么、
    读出来什么"才是这份数据的基本承诺。判定与写侧对称：剥一层后仍是"`'` + 公式
    前缀"（即写侧补的第二层）也继续剥，两层剥完就是原值。
    """
    text = "" if value is None else str(value)
    if text[:1] == "'" and (text[1:2] in _FORMULA_PREFIXES or _escaped_form(text[1:])):
        return text[1:]
    return text


def restore_row(row):
    """整行还原（读取侧统一入口）。"""
    return dict((key, csv_read_cell(value)) for key, value in row.items())
