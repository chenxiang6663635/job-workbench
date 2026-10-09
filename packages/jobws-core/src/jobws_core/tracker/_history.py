# -*- coding: utf-8 -*-
"""时间线（history.csv）的**容错读**：坏行跳过、如实计数、不掩盖真损坏。

为什么单独一个模块（2026-10-09 审计 1.1-6 拆出）：`applications.py` 已贴 300 行
水位；容错读与"写时间线"的职责也不相干——本模块只回答"这份文件现在能读出什么"。

背景：history.csv 是唯一**非原子追加写**的表（`applications.append_history`，
理由见那里的 docstring）。崩溃会把最后一条记录写一半——表现为缺列（csv 默认
宽容不抛异常）、或多出半截字段。写侧现在会先补断行让残缺行自成一行；本模块
负责读侧的"损失止步于残缺行"：

- **逐行判**，不是"丢尾巴"：缺列行一旦被后续追加"续上"就落在中间，按尾截断的
  模型会把好行一起丢掉；结构不完好（缺列 restval=None / 多列 None 键）的行
  单独丢弃并计数。
- **解码容忍**：崩溃也可能把 UTF-8 字符切一半。整份严格解码失败时改用
  `errors="replace"` 继续读（该行的可读部分保留、残字显示为 U+FFFD），而不是
  让整份文件进 quarantine。
- **不掩盖真损坏**：表头（第一行）连锚点列（时间 / id）都没有时抛 ValueError，
  由调用方（`track check`）按真损坏处理——隔离并如实报告。

返回形状 `(rows, dropped)`：dropped = 丢弃的行数，调用方必须报出来（不静默）。
"""

from __future__ import annotations

import csv
import io
import os

from ..csv_cells import restore_row
from ._schema import HISTORY_FIELDS

# 表头锚点：缺了这两列的"csv"不是时间线（真损坏的判据；新增列不受影响）
_HEADER_ANCHORS = ("时间", "id")


def read_history_rows(path):
    """读时间线原始行，返回 `(rows, dropped)`。文件不存在 → `([], 0)`。"""
    if not os.path.isfile(path):
        return [], 0
    with io.open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8-sig", errors="replace")   # 半字符留 U+FFFD，不丢整份

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not set(_HEADER_ANCHORS) <= set(reader.fieldnames or ()):
        raise ValueError("时间线表头无法解析（缺 %s 列，需人工检查）"
                         % " / ".join(_HEADER_ANCHORS))

    rows = []
    dropped = 0
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            dropped += 1          # 残缺记录（崩溃写了一半）：丢这一条，其余不动
            continue
        rows.append(restore_row(dict(row)))
    return rows, dropped
