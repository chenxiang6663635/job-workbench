# -*- coding: utf-8 -*-
"""PyInstaller 冻结入口（#271 P2-2）：把 `jobws_mcp.server:main` 作为**包内模块**跑起来。

为什么单独要它：直接拿 `jobws_mcp/server.py` 当 PyInstaller 的入口脚本时，冻结产物
把它按**顶层脚本**执行（`__name__ == "__main__"`、没有父包）——server.py 里
`from . import paths, ...` 这类相对导入当场 `ImportError: attempted relative import
with no known parent package`（2026-10-07 冒烟实证）。入口放包外、只做一次绝对导入，
`jobws_mcp` 就以正常包形态进依赖图。

源码形态不受影响：`python -m jobws_mcp.server` 与 `[project.scripts] jobws-mcp`
（server.py 的 `__main__` 守卫）照旧可用；本文件只服务打包。
"""

import sys

from jobws_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
