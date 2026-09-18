# -*- coding: utf-8 -*-
"""包版本：读**安装后的元数据**，不读仓库文件。

真值源是 `web/electron/package.json` 的 version（产品版本唯一真值源）。
构建期由 `setup.py` 读它并写进 wheel 元数据（那时仓库一定在侧）；运行时
从这个元数据读回 —— 装上之后就**不再依赖仓库**。

读不到的两种情形都属正常、不该炸：源码形态未安装（回退占位值）、
元数据被 PyInstaller 剥掉（打包时记得 `--copy-metadata jobws-core`）。
"""

from __future__ import annotations

_FALLBACK = "0.0.0.dev0"

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _metadata_version

    try:
        __version__ = _metadata_version("jobws-core")
    except PackageNotFoundError:
        # 未安装（源码直接跑）→ 给一个明确不是产品版本号的占位值
        __version__ = _FALLBACK
except ImportError:  # pragma: no cover —— 3.12 一定有 importlib.metadata
    __version__ = _FALLBACK
