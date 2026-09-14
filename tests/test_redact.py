# -*- coding: utf-8 -*-
"""脱敏的公共实现（`web/backend/redact.py`）。

来源：issue #50 的 m2 —— `routers/imap.py::_mask_password` 与
`routers/provider.py::_mask_key` 是两份逐字相同的实现（rule of three 第 2 次），
抽到这里。抽出来的同时把行为钉住，因为它是**凭证在界面上的唯一可见形态**：

- 保留末 4 位（用户要能认出"是不是这把 key"），其余全部遮成 `*`；
- 短值（≤4）整串遮掉——不能因为短就露出全部；
- 空值返回空串（`hasKey` / `hasPassword` 由另一个字段表达，不靠这里的形态猜）。

**不做的事**：不保留前缀。前缀常含项目/环境标识（`sk-live-…`），露出来对识别
价值不大，却多给一段可被关联的信息。
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

from redact import mask_secret  # noqa: E402


def test_keeps_last_four_and_masks_the_rest():
    # 15 字符 → 前 11 位遮掉；这里写字面量而不是 len()-4，避免断言跟着实现一起错
    assert mask_secret("sk-abcdefgh1234") == "***********1234"


def test_exactly_four_characters_is_fully_masked():
    assert mask_secret("1234") == "****"


def test_shorter_than_four_is_fully_masked_not_leaked():
    """短值不能因为短就露出来——"只有 3 位"不是可显示的正当理由。"""
    assert mask_secret("abc") == "****"


def test_empty_value_stays_empty():
    assert mask_secret("") == ""

    # 与 hasKey / hasPassword 的分工：空值由形态表达，调用方不必先判空
    assert mask_secret(None) == ""
