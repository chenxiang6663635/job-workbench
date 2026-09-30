# -*- coding: utf-8 -*-
"""锁路径的防复发静态测试（issue #210 的验收之一）。

锁路径的唯一真源是 `jobws_core.workspace_io.lock_path`（`_LOCK_KINDS` 表）。后端各
router 与域包的两处写入路径曾各自手拼字符串——今天逐字一致，但改一处就会**静默失配**，
而互斥失效是数据丢失级的故障（CLI / 桌面端 / 网页端用同一把锁）。这条网扫
`web/backend` 与域包源码（`packages/jobws-core/src/jobws_core`）：

1. **具名网**：出现「引号包裹的**已知**锁文件名」即失败（名单从 `_LOCK_KINDS` 生成）；
2. **泛化网**：出现任何「引号包裹且以 `.lock` 结尾的路径」（如 `"config/imap.lock"`、
   `"05_投递追踪/tracker.lock"`）也失败——表外的**新**锁名同样兜得住。
   唯一的例外是裸后缀 `".lock"` 本身：那是"过滤锁文件"的常见写法（`resume.py` /
   `system.py` / `workspace_io.py` 各一处），不是锁名。

判定口径：
- 只匹配引号里的字面量——注释 / docstring 里的**裸词**不算；但**注释里也别给锁名加引号**，
  加了引号就会红（这里不做语法分析，「引号里出现 .lock」一律按疑似第二份真相源处理）。
- 例外只有两处，按**相对路径**白名单：`web/backend/lockctx.py`（后端唯一入口）与
  `packages/.../workspace_io.py`（表本身）；打包产物（`build/` / `dist/`）与
  `__pycache__` 不扫。
"""
from __future__ import annotations

import io
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOTS = (
    os.path.join(ROOT, "web", "backend"),
    os.path.join(ROOT, "packages", "jobws-core", "src", "jobws_core"),
)
ALLOWED_FILES = {
    "web/backend/lockctx.py",                     # 后端唯一入口（调工厂）
    "packages/jobws-core/src/jobws_core/workspace_io.py",   # 锁名表本身
}
_SKIP_DIRS = {"build", "dist", "__pycache__"}
_ANY_LOCK_RE = re.compile(r"""["'][^"'\r\n]*\.lock["']""")

# 自插 sys.path：单独跑本文件也要能过（未安装领域包时退到源码形态，与 tools/ 同一条路）
try:
    from jobws_core import workspace_io  # noqa: E402
except ImportError:  # pragma: no cover - 开发机未安装领域包时的兜底
    sys.path.insert(0, os.path.join(ROOT, "packages", "jobws-core", "src"))
    from jobws_core import workspace_io  # noqa: E402


def _lock_names():
    """从工厂的锁名表取名（不手抄）；表结构变了就大声失败，而不是静默漏检。"""
    kinds = getattr(workspace_io, "_LOCK_KINDS", None)
    if not isinstance(kinds, dict) or not kinds:
        pytest.fail("workspace_io._LOCK_KINDS 不是预期结构——本测试的名单来源变了，请同步更新")
    try:
        names = sorted({name for _rel, name in kinds.values()})
    except (TypeError, ValueError) as exc:      # 值形状变了（三元组 / 字符串…）
        pytest.fail("workspace_io._LOCK_KINDS 的值不是 (目录, 文件名)：%s" % exc)
    assert "tracker.lock" in names and ".jobs.lock" in names, names
    return names


def _offenders(text, names):
    """返回 [(行号, 命中片段)]：具名网 + 泛化网。"""
    hits = []
    for name in names:
        for quote in ('"', "'"):
            for match in re.finditer(re.escape("%s%s%s" % (quote, name, quote)), text):
                hits.append((text.count("\n", 0, match.start()) + 1, name))
    for match in _ANY_LOCK_RE.finditer(text):
        if match.group(0) in ('".lock"', "'.lock'"):    # 裸后缀过滤，不是锁名
            continue
        hits.append((text.count("\n", 0, match.start()) + 1, match.group(0)))
    return sorted(set(hits))


def test_scan_covers_real_files():
    """网必须真的扫到东西——路径写错时不许静默变绿。"""
    for root in SCAN_ROOTS:
        assert os.path.isdir(root), "扫描根不存在：%s" % root
    scanned = 0
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            scanned += sum(1 for name in filenames if name.endswith(".py"))
    assert scanned > 20, "只扫到 %d 个 py 文件，扫描面可疑" % scanned


def test_no_hardcoded_lock_paths():
    """除白名单两处，不许再出现引号形式的锁路径（具名 + 泛化两张网）。"""
    names = _lock_names()
    offenders = []
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, ROOT).replace("\\", "/")
                if rel in ALLOWED_FILES:
                    continue
                with io.open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                for line, hit in _offenders(text, names):
                    offenders.append("%s:%d 手拼锁路径 %s" % (rel, line, hit))
    assert offenders == [], (
        "锁路径只能来自 workspace_io.lock_path（唯一真源 _LOCK_KINDS）；"
        "后端入口是 lockctx.lock_path：\n  - " + "\n  - ".join(offenders)
    )
