# -*- coding: utf-8 -*-
"""【已废弃】`workspace_io` 的旧路径 —— 转发到 `jobws_core.workspace_io`。

2026-09-17 批 6：领域层开始包化（`packages/jobws-core`，import 名 `jobws_core`）。
本文件不再有实现，只做**转发**，让后端（含 `web/backend/atomicio.py` 的薄
转发链）、tracker 与各测试文件**零改动**继续工作。

转发而非重新实现/值快照的理由、`sys.modules` 替换的机理与下一步计划，
见同目录 `filelock.py` 的模块注释（两处是同一套写法）。

注意：本模块是**四端唯一入口**（批 8 收敛），旧路径只是它的一个别名——
新增代码请一律 `from jobws_core import workspace_io`。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings

warnings.warn(
    "import workspace_io 已废弃：领域层已包化，请改用 "
    "`from jobws_core import workspace_io`。旧路径将在下一版删除。",
    DeprecationWarning,
    stacklevel=2,
)


def _import_real():
    """导入真身；未安装时退化为源码形态（把包的 src 加进 sys.path 再试）。"""
    try:
        return importlib.import_module("jobws_core.workspace_io")
    except ImportError:
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "packages",
            "jobws-core",
            "src",
        )
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)
        return importlib.import_module("jobws_core.workspace_io")


_real = _import_real()
sys.modules[__name__] = _real
__path__ = list(getattr(_real, "__path__", []))


def __getattr__(name):  # PEP 562 兜底
    return getattr(_real, name)
