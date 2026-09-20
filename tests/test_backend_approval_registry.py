# -*- coding: utf-8 -*-
"""后端的 apply 入口必须看到**完整**登记表（2026-09-19 批 6 第二批 PR-B）。

为什么单开一条、而且必须在**子进程**里跑：同进程的其它测试文件自己就
`import approval`（仓内），会替路由器完成登记——把 `routers/approvals.py` 改回
包内协议壳（只登记十一个），那些用例**仍然全绿**，而真实的后端会在用户点确认时
才 422 `unknown_operation`。

这不是假设：本批的 UI 冒烟抓到过一模一样的一次（笔记勾选框写回失败），而当时
840 个 pytest 全绿。这条网就是为那个盲区补的——它必须**只** import `main`，
不碰任何会顺带注册的测试辅助。
"""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 13 项 = 包内自登记的十一个 + 仓内追加的 prep.toggle / init
_EXPECTED = 13


def test_backend_apply_entry_sees_the_full_registry():
    code = """
import os, sys
sys.path.insert(0, os.path.join(%(root)r, "web", "backend"))
import main  # noqa: F401  —— 它把 tools/ 加进 sys.path 并导入全部路由
from routers import approvals  # noqa: F401  —— 真实入口
from jobws_core import approval as shell
ops = shell.registered_operations()
assert "prep.toggle" in ops, ops
assert "init" in ops, ops
assert len(ops) == %(expected)d, (len(ops), ops)
print("ok")
""" % {"root": _ROOT, "expected": _EXPECTED}
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=_ROOT,
        capture_output=True, text=True, timeout=180,
        env={**os.environ, "JOBWS_NO_BROWSER": "1"},
    )
    assert proc.returncode == 0, (
        "后端的 apply 入口看不到完整登记表——routers/approvals.py 是不是用了"
        "包内协议壳（那样只有十个操作，prep.toggle / init 会在用户点确认时才 422）：\n%s"
        % (proc.stderr or proc.stdout))
