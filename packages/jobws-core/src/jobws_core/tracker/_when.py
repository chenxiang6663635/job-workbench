# -*- coding: utf-8 -*-
"""「日期或日期+时刻」的判定（面试时间 / 宣讲会时间 / 邮件日期）。

单独一个模块的理由是**规模**：`_core.py` 已贴着 300 行的逻辑型上限（存量豁免只许
变小），而这套判定要同时被领域层的校验函数与 CLI 的直写路径引用。放这里两侧都能
用，不必各自抄一遍——判定抄两份的下场是某一侧先改、另一侧静默不一致。

口径与 Web 侧的 `icsutil.parse_when` 一致（两处都改才算同步）。
"""

import re
from datetime import datetime

# `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM(:SS)`；分隔符允许空格或 T
WHEN_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$")


def check_when(value, label, allow_empty=True):
    """校验并返回错误列表（空列表 = 通过）。

    为什么不用 `check_date`：这几个字段的常见形态带时刻（`2026-09-16 10:00`），
    纯日期校验会把合法值误拒。为什么不能只查正则：`2026-02-31` 能过正则，落库后
    `.ics` 导出与看板时间线会**静默跳过**这一行——用户看不到面试从日历里消失，
    却也不会收到任何报错（2026-09-23 二轮审计的发现之一）。
    """
    if not value:
        if allow_empty:
            return None
        return ["`%s` 不能为空" % label]
    text = str(value).strip()
    m = WHEN_RE.match(text)
    if not m:
        return ["`%s: %s` 格式错误，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM" % (label, text)]
    try:
        datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                 int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
    except ValueError:
        return ["`%s: %s` 不是有效时间（如 2 月没有 31 日、没有 25 点）" % (label, text)]
    return None
