# -*- coding: utf-8 -*-
"""MCP 包**不再需要仓库在侧**的验收（2026-09-19 批 6 第二批 PR-B）。

这是本批的核心承诺：删掉 `paths.py` 里的 sys.path 注入与 `JOBWS_REPO_ROOT` 推导之后，
`jobws-mcp` 应当**装上就能用**——领域层全部在 `jobws_core` 包里。

RED 的形态（本测试第一次跑的预期）：`paths.py` 还在用 `dirname²(__file__)` 推仓库根，
把包**复制到仓库之外**（模拟装进 site-packages）之后 `web/backend` 与 `tools/` 都不存在，
导入直接 `ImportError`——这正是「仓库不在默认位置就用不了」的机器形态。

为什么要复制而不是改 cwd：硬闸推的是**包位置**（不是 cwd），光换 cwd 它照样能找到仓库，
测不出真问题（`test_stdio_smoke.py` 在仓库里跑，永远绿）。
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

_PKG = pathlib.Path(__file__).resolve().parents[1] / "jobws_mcp"


def test_importable_outside_the_repository(tmp_path):
    """包复制到仓库外（无 JOBWS_REPO_ROOT）后，读侧与写侧都能导入。"""
    shutil.copytree(_PKG, tmp_path / "jobws_mcp",
                    ignore=shutil.ignore_patterns("__pycache__"))
    env = {k: v for k, v in os.environ.items() if k != "JOBWS_REPO_ROOT"}
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-c",
         "from jobws_mcp import tools_readonly, tools_writable; "
         "from jobws_mcp import paths; "
         "assert not hasattr(paths, 'REPO_ROOT'), '硬闸还在'; "
         "print('ok')"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, "仓库之外导入失败：\n%s" % (proc.stderr or proc.stdout)
