# -*- coding: utf-8 -*-
"""日期字段的入口校验（2026-09-23 审计 P1 补网）。

起因：`check_date` 此前只装在投递主表的三条写路径上，其余四张从表（联系人 /
Offer / 邮件 / 面试 / 宣讲会）照收任何字符串。后果不是"界面报错"，而是**静默
丢数据**：日历上不存在的日期（`2026-02-31`）写进去以后，`icsutil.parse_when`
解析失败 → 导出 .ics 时那一行被 `continue` 跳过（用户看不见面试从日历里消失），
看板的时间线也同样跳过。

两种校验分开，因为语义不同：
- **纯日期**（`2026-02-31` 非法）：走领域层 `tracker.check_date`（与 CLI / 界面
  投递表的判定同源，不用第二套规则）；
- **带时刻的时间**（`2026-02-31 14:00`）：走 `icsutil.parse_when`——投递表的
  纯日期校验会误拒它。

空值一律放行（"还没定"是合法状态）；`None` 表示「这次不改这个字段」，由调用方
自行过滤。
"""

from apierror import ApiError
from jobws_core import tracker

from icsutil import parse_when


def check_date_fields(pairs):
    """pairs 形如 [(值, 字段名)]：非法纯日期抛 422（`err.date.format`）。"""
    for value, label in pairs:
        text = (value or "").strip()
        if not text:
            continue
        errs = tracker.check_date(text, label)
        if errs:
            raise ApiError(422, "date.format", errs[0], label=label, value=text)


def check_when_fields(pairs):
    """pairs 形如 [(值, 字段名)]：非法「日期 + 可选时刻」抛 422（`err.date.when`）。"""
    for value, label in pairs:
        text = (value or "").strip()
        if not text or parse_when(text):
            continue
        raise ApiError(422, "date.when", "%s：%s 不是合法日期或时间" % (label, text),
                       label=label, value=text)
