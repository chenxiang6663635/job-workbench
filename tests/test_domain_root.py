# -*- coding: utf-8 -*-
"""工作区根与默认工作区的守卫——**不依赖仓库根的位置**。

为什么要有这个文件（2026-09-17 批 6）：

`tools/tracker/_core.py` 用 `os.path.dirname(__file__)` 推导 `ROOT` 与
`DEFAULT_WORKSPACE`。领域层还在仓库 `tools/` 下时，拿「ROOT 下面有
CHANGELOG.md」当守卫是够用的；但**一旦搬进可安装包**（site-packages），
ROOT 会跟着漂，`DEFAULT_WORKSPACE` 变成 `<site-packages>/personal`——而
`_core.py` 读不到方向配置时是**直接放行**校验的，故障全程静默、还会把用户
数据写到 Python 安装目录。

所以这里改成**位置无关**的两条断言，先于搬迁建立起来：

1. 默认工作区的父目录必须等于应用根（`pathres.resolve_root()`）——层级错
   一层就红，与领域层到底住在仓库还是 site-packages 无关；
2. 注入 `JOBWS_DATA_DIR` 后，可写数据根必须精确落在注入值上（env 模式）。

「先立后拆」的顺序很重要：等第二批真的搬 tracker 时，守卫已经在位，
不会出现「旧守卫已失效、新守卫还没建」的窗口。
"""

from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pathres  # noqa: E402
import tracker  # noqa: E402


def test_default_workspace_sits_under_app_root():
    """默认工作区 = <应用根>/personal——写成「父目录等于应用根」，位置无关。

    包化后 ROOT 的 dirname 层级曾少一层（tools/tracker/ 比 tools/tracker.py
    深一级）→ 默认工作区落到 tools/personal（独立审查 MAJOR-2 实测）。
    这条断言在领域层搬进 site-packages 后依然成立：那时 ROOT 若漂了，
    dirname(DEFAULT_WORKSPACE) 就不再等于 resolve_root()，当场变红。
    """
    app_root = os.path.abspath(pathres.resolve_root())
    default_ws = os.path.abspath(tracker.DEFAULT_WORKSPACE)
    assert os.path.basename(default_ws) == "personal"
    assert os.path.dirname(default_ws) == app_root, (
        "默认工作区的父目录应等于应用根：领域层的 ROOT 推导层级错了"
        "（默认工作区=%s，应用根=%s）" % (default_ws, app_root)
    )


def test_data_dir_env_wins_over_app_root(monkeypatch, tmp_path):
    """JOBWS_DATA_DIR 是最高的优先级——注入后数据根必须精确落在它上面。

    这条不碰领域层，只钉 `pathres` 的优先级链，所以在任何形态下都成立。
    """
    monkeypatch.setenv(pathres.ENV_DATA_DIR, str(tmp_path))
    root, mode = pathres.resolve_workspace_root()
    assert mode == "env"
    assert os.path.abspath(root) == os.path.abspath(str(tmp_path))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
