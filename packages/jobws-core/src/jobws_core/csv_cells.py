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


def _needs_escape(text):
    """写侧要加引号、读侧要去引号，用的是**同一个**判据。

    传进来的都是「相对原值去掉/加上一个前导引号后的那段」：写侧传原值，读侧传
    「读到的值去掉一个前导引号」。递归那一支处理「本来就是引号 + 公式前缀」的形态
    （`'- 待定`、`''=x`…）——只能补一层的话，两个引号那种形态会读侧多剥一层，
    写读不再对合（2026-09-23 二轮审查抓的反例）。
    """
    if text[:1] in _FORMULA_PREFIXES:
        return True
    return text[:1] == "'" and _needs_escape(text[1:])


def csv_cell(value):
    """单元格出口：None → 空串；危险开头 → 前置单引号。"""
    text = "" if value is None else str(value)
    if _needs_escape(text):
        return "'" + text
    return text


def csv_read_cell(value):
    """单元格入口：还原写入时中和掉的单引号（`'- 待定` → `- 待定`）。

    为什么必须成对：中和是**为了 Excel**，不是为了改用户数据——读回来若少了这一步，
    备注会永远多一个引号（界面、CLI、导出、下一次写回都带着它），而"写进去什么、
    读出来什么"才是这份数据的基本承诺。
    """
    text = "" if value is None else str(value)
    if text[:1] == "'" and _needs_escape(text[1:]):
        return text[1:]
    return text


def restore_row(row):
    """整行还原（读取侧统一入口）。"""
    return dict((key, csv_read_cell(value)) for key, value in row.items())
