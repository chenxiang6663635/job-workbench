# -*- coding: utf-8 -*-
"""S4 负向探针：**只在 CI** 失败，验证 Required Checks 真的阻断合并（用完即删）。

本地跑（无 `CI` 环境变量）保持绿——否则 pre-commit 的全量 pytest 会先把提交拦住，
那就变成"绕过 hook 才能验证"，没有必要。CI（GitHub Actions 恒设 `CI=true`）里失败。
"""

import os


def test_required_check_blocks_merge():
    assert not os.environ.get("CI"), "S4 negative probe: this PR must NOT be mergeable"
