# -*- coding: utf-8 -*-
"""题库的抽题与重练队列：把「今天该练什么」变成一次可执行的抽取。

刻意做成**纯函数**：不读工作区、不写任何数据；随机源与"今天"都从参数注入。
CLI 与界面共用同一份口径——两边各写一遍排序与去重，迟早会出现"手机上看到的
队列和电脑上不一样"这种无从解释的差异。

队列 = **错题 ∪ 当日待复习**（去重后按「最近复习升序、题目」排）：
- 错题是人**明确标出来**的弱点（标签里有「错题」）；
- due 是**时间算出来**的（沿用 question_review 的阶梯，未看恒在）；
两者并集才是"今天该看的"——只取其一都会漏掉另一半。

不引入记忆曲线：间隔仍然是 `question_review.REVIEW_INTERVALS` 那张写死的阶梯，
本模块只决定"抽哪几道、按什么顺序"，不改动"什么时候到期"。

筛选（领域 / 科目 / 关键词）**不在这里做**：调用方先按
`question_bank.read_questions` 的同一套口径过滤，再把行传进来——筛选也只有一处。
"""

import random

from .question_review import WRONG_TAG, due_from_rows, split_tags

# 一轮抽几道：默认 5，上限 20（一轮太长练不完，也失去"碎片化"的意义）
DEFAULT_N = 5
MAX_N = 20

MODES = ("due", "wrong", "random")


def _row_key(row):
    """去重键：有 id 用 id，没有（手改过的行）退回题目文本。"""
    return ((row.get("题目id") or "").strip()
            or (row.get("题目") or "").strip())


def _sort_key(row):
    """与 due_questions 同一条排序：没复习过的在前，其次按题目。"""
    return ((row.get("最近复习") or "").strip(), row.get("题目") or "")


def wrong_from_rows(rows):
    """行里的错题（标签含「错题」），按同一条排序。"""
    wrong = [row for row in rows if WRONG_TAG in split_tags(row.get("标签"))]
    wrong.sort(key=_sort_key)
    return wrong


def build_queue(rows, today=None):
    """重练队列 = 错题 ∪ 当日待复习（去重、按同一条排序）。"""
    merged = []
    seen = set()
    for row in list(wrong_from_rows(rows)) + [r for r, _reason
                                              in due_from_rows(rows, today)]:
        key = _row_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(row)
    merged.sort(key=_sort_key)
    return merged


def pick_drill(rows, mode="due", n=DEFAULT_N, rng=None, today=None):
    """抽一轮题，返回行的列表（不改动传入的数据）。

    - `mode`：`due`（重练队列）/ `wrong`（只错题）/ `random`（全库随机）；
    - `n`：默认 5、上限 20（超了按上限截断，0 / 负数按 1 处理）；
    - `rng`：随机源（测试注入固定序列）；`today`："今天"（测试钉住某一天）。
    """
    mode = (mode or "").strip() or "due"
    if mode not in MODES:
        raise ValueError("抽题模式只能是 %s（收到 %r）"
                         % (" / ".join(MODES), mode))
    try:
        limit = int(n)
    except (TypeError, ValueError):
        limit = DEFAULT_N
    limit = max(1, min(limit, MAX_N))

    if mode == "wrong":
        return wrong_from_rows(rows)[:limit]
    if mode == "random":
        pool = list(rows)
        (rng or random).shuffle(pool)
        return pool[:limit]
    return build_queue(rows, today)[:limit]
