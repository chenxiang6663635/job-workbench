# -*- coding: utf-8 -*-
"""凭证脱敏的**唯一实现**（issue #50 m2）。

来源：`routers/imap.py::_mask_password` 与 `routers/provider.py::_mask_key`
是两份逐字相同的实现（rule of three 第 2 次命中）。抽出来不只是去重——脱敏是
**凭证在界面上的唯一可见形态**，两份实现意味着将来"改一处忘一处"会让某个字段
悄悄露出更多字符。

口径（`tests/test_redact.py` 逐条钉住）：

- 保留**末 4 位**：用户要能认出"是不是这把 key"，末位是最有用的那一段；
- 短值（≤ keep）整串遮掉：不能因为"只有 3 位"就露出来；
- 空值/None 返回空串（"有没有存过"由 `hasKey` / `hasPassword` 表达，不靠形态猜）；
- **不保留前缀**：前缀常含项目/环境标识（`sk-live-…`），对识别价值不大，
  却多给一段可被关联的信息。

调用方传 `keep` 只在确有理由时用；默认值就是全项目的口径。
"""

from __future__ import annotations

# 默认保留位数：改这里等于改全项目的可见形态，改之前先看 tests/test_redact.py
KEEP = 4


def mask_secret(value, keep=KEEP):
    """把 value 的中段遮成 `*`，只保留末尾 keep 位；空值返回空串。"""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * keep
    return "*" * (len(value) - keep) + value[-keep:]
