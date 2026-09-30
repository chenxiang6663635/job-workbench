# -*- coding: utf-8 -*-
"""锁文件名的防复发静态测试（issue #210 的验收之一）。

锁路径的唯一真源是 `jobws_core.workspace_io.lock_path`（`_LOCK_KINDS` 表）。后端各
router 曾各自手拼字符串——今天逐字一致，但改一处就会**静默失配**，而互斥失效是数据
丢失级的故障（CLI / 桌面端 / 网页端用同一把锁）。这条网扫 `web/backend/**`：出现
「引号包裹的锁文件名」即失败。

判定口径：
- 只匹配引号里的字面量——注释 / docstring 里的裸词不算（那里的叙述是允许的）；
- `lockctx.py` 自身除外（它是工厂的调用方，不是第二处真相源）；
- 打包产物（`build/` / `dist/`）与 `__pycache__` 不扫。
- 名单**不手抄**：从工厂的 `_LOCK_KINDS` 生成——工厂换了名字，这条网自动跟上；
  若表结构变了就大声失败，而不是静默漏检。
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "web", "backend")

# 自插 sys.path：单独跑本文件也要能过（未安装领域包时退到源码形态，与 tools/ 同一条路）
try:
    from jobws_core import workspace_io  # noqa: E402
except ImportError:  # pragma: no cover - 开发机未安装领域包时的兜底
    sys.path.insert(0, os.path.join(ROOT, "packages", "jobws-core", "src"))
    from jobws_core import workspace_io  # noqa: E402

_SKIP_DIRS = {"build", "dist", "__pycache__"}
_ALLOWED_FILES = {"lockctx.py"}


def _lock_names():
    """从工厂的锁名表取名（不手抄）。"""
    kinds = getattr(workspace_io, "_LOCK_KINDS", None)
    if not isinstance(kinds, dict) or not kinds:
        pytest.fail("workspace_io._LOCK_KINDS 不是预期结构——本测试的名单来源变了，请同步更新")
    names = sorted({name for _rel, name in kinds.values()})
    # 抽样自检：名字真取自表（不是空集或意外形状）
    assert "tracker.lock" in names and ".jobs.lock" in names, names
    return names


def _offenders(text, names):
    """返回 [(行号, 锁名)]：文本里出现的「引号包裹的锁文件名」。"""
    hits = []
    for name in names:
        for quote in ('"', "'"):
            pattern = re.compile(re.escape("%s%s%s" % (quote, name, quote)))
            for match in pattern.finditer(text):
                hits.append((text.count("\n", 0, match.start()) + 1, name))
    return sorted(hits)


def test_backend_has_no_hardcoded_lock_names():
    """`web/backend` 里除了 lockctx.py，不许再出现引号形式的锁文件名。"""
    names = _lock_names()
    offenders = []
    for dirpath, dirnames, filenames in os.walk(BACKEND):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in sorted(filenames):
            if not filename.endswith(".py") or filename in _ALLOWED_FILES:
                continue
            path = os.path.join(dirpath, filename)
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            for line, name in _offenders(text, names):
                offenders.append("%s:%d 手拼锁名 %s"
                                 % (os.path.relpath(path, ROOT).replace("\\", "/"),
                                    line, name))
    assert offenders == [], (
        "锁路径只能来自 lockctx.lock_path（唯一真源 workspace_io._LOCK_KINDS）：\n  - "
        + "\n  - ".join(offenders)
    )
