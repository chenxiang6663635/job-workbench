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


def due_from_rows(rows, today=None):
    """同上规则，但作用在**已读出的行**上（2026-09-20：抽题要用它）。

    为什么拆出这一层：`due_questions` 自己读工作区，而抽题拿到的行是**筛过**的
    （领域 / 科目 / 关键词在调用方就过滤掉了）。若抽题再按自己的口径算一遍 due，
    就会出现"界面上的队列和 CLI 不一样"这种无从解释的差异——规则只有一处。
    """
    day = today or datetime.date.today()
    if isinstance(day, str):
        day = _parse_date(day) or datetime.date.today()

    result = []
    for row in rows:
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


def due_questions(workspace=None, today=None):
    """今日待复习的题：返回 `[(row, reason)]`，按（最近复习升序、题目）排。

    `today` 可注入（测试与"模拟某天"用）；传字符串按 ISO 日期解析，解析不出
    就当没传。reason 是给人看的一句话，直接展示在 CLI 表格里。
    """
    return due_from_rows(question_bank.read_questions(workspace), today)


# --- 错题本（2026-09-19 收口批）---------------------------------------------
#
# 用**标签**而不是新增列：questions.csv 的列清单被 schema 自检锁着（缺列即报
# "schema 不匹配"，加列要动版本与老数据迁移）；「标签」本就是分类位（网络基础、
# 高频题…），加一个「错题」零迁移、Excel 里手改也自然。代价是它不是枚举列——
# 用错误拼写（"错提"）不会报错，只会静默不入选；文档与服务端口径都写明这一点。

WRONG_TAG = "错题"

# 标签分隔符：写出去统一用英文逗号；读入时容忍中文逗号 / 顿号 / 分号 / 空白
# （用户手改 CSV 的分隔习惯不止一种）
_TAG_SPLIT_RE = re.compile(r"[,，、;；\s]+")


def split_tags(text):
    """标签串 → 列表（去空、保序、不去重——去重交给写入口）。"""
    return [t for t in _TAG_SPLIT_RE.split((text or "").strip()) if t]


def wrong_questions(workspace=None):
    """错题本：标签里含「错题」的题，按（最近复习升序、题目）排。"""
    rows = [r for r in question_bank.read_questions(workspace)
            if WRONG_TAG in split_tags(r.get("标签"))]
    rows.sort(key=lambda r: ((r.get("最近复习") or "").strip(),
                             r.get("题目") or ""))
    return rows


def preview_mark_wrong(question_id, on, workspace=None):
    """预览把一道题标进 / 移出错题本（**不落盘**），返回 (errors, plan)。

    实现是「重算标签串 → 走既有的 update 预览」：**不新增写操作**——落盘通道、
    字段校验与"预览后数据变了"的冲突语义全部复用（`question.update`）。
    """
    qid = (question_id or "").strip()
    if not qid:
        return ["缺少题目 id（可用 `jobws bank wrong` 或 `bank list` 查）"], None
    rows = question_bank.read_questions(workspace)
    current = question_bank.find_question(rows, qid)
    if current is None:
        return ["找不到 id 为 %s 的题目" % qid], None
    tags = split_tags(current.get("标签"))
    if on:
        if WRONG_TAG in tags:
            return ["这道题的标签里本来就有「%s」（无变化）" % WRONG_TAG], None
        tags.append(WRONG_TAG)
    else:
        if WRONG_TAG not in tags:
            return ["这道题不在错题本里（无变化）"], None
        tags = [t for t in tags if t != WRONG_TAG]
    return question_bank.preview_update_fields(
        qid, {"标签": ",".join(tags)}, workspace)
