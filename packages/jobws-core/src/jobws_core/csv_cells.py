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


def csv_cell(value):
    """单元格出口：None → 空串；危险开头 → 前置单引号。"""
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_PREFIXES:
        return "'" + text
    return text
