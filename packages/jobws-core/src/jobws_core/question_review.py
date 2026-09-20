# -*- coding: utf-8 -*-
"""题库的复习视图：今日待复习（due today）。

刻意是**纯视图**：不改 questions.csv 一个字节，也不引入记忆曲线调参——间隔是
一张写死的阶梯。理由：
- 个性化的间隔重复（SM-2 之类）要用户调参、要存"难度因子"等状态，是另一个
  产品；当前一步是先把「什么时候该看什么」从凭感觉变成**有清单**；
- 纯视图 = 零数据迁移：升级之后老题库立刻可用——`最近复习` 为空 / 脏数据 /
  未知状态都有明确的保守规则（见 `due_questions`）。

规则（写死、可解释、可测试）：
- `未看`：永远待复习——还没学过的东西谈不上"到没到期"；
- `看过` / `会了`：`最近复习` 为空 → 待复习（没复习过）；否则
  `最近复习 + 间隔 ≤ 今天` 才待复习；
- `最近复习` 解析不出日期（脏数据）→ 视为待复习（宁可多提醒，不要静默漏）。
"""

import datetime
import re

from . import question_bank

# 复习间隔（天）：按状态给下一次复习的时间点。保守默认、不做个性化（见 docstring）。
REVIEW_INTERVALS = {"看过": 3, "会了": 14}

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _parse_date(text):
    """严格 ISO 日期（YYYY-MM-DD）→ date；空 / 脏 → None（保守策略交给调用方）。"""
    match = _DATE_RE.match((text or "").strip())
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)),
                             int(match.group(3)))
    except ValueError:
        return None


def due_questions(workspace=None, today=None):
    """今日待复习的题：返回 `[(row, reason)]`，按（最近复习升序、题目）排。

    `today` 可注入（测试与"模拟某天"用）；传字符串按 ISO 日期解析，解析不出
    就当没传。reason 是给人看的一句话，直接展示在 CLI 表格里。
    """
    day = today or datetime.date.today()
    if isinstance(day, str):
        day = _parse_date(day) or datetime.date.today()

    result = []
    for row in question_bank.read_questions(workspace):
        status = (row.get("状态") or "").strip() or "未看"
        raw_last = (row.get("最近复习") or "").strip()
        last = _parse_date(raw_last)
        if status == "未看":
            result.append((row, "还没学（未看）"))
            continue
        if last is None:
            result.append((row, "从没复习过" if not raw_last
                           else "「最近复习」不是日期，按待复习处理"))
            continue
        interval = REVIEW_INTERVALS.get(status)
        if interval is None:
            result.append((row, "状态无法识别，按待复习处理"))
            continue
        due = last + datetime.timedelta(days=interval)
        if due <= day:
            overdue = (day - due).days
            result.append((row, "已到期" if overdue == 0 else "已到期 %d 天" % overdue))
    # 没复习过的（空串）排在日期之前：它们最该先看
    result.sort(key=lambda item: ((item[0].get("最近复习") or "").strip(),
                                  item[0].get("题目") or ""))
    return result
