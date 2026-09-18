# -*- coding: utf-8 -*-
"""jobws_core —— 求职工作台的领域层（可安装包）。

**为什么有这个包**：领域函数原本都在仓库 `tools/` 下，MCP 与后端靠
`sys.path` 注入 import 它们 —— 于是 "MCP 必须 editable 安装、仓库必须在侧"
（`mcp/jobws_mcp/paths.py` 里曾有硬闸）。包化之后领域层是**装上去就能用**
的普通依赖，这条限制才有条件解除。

**为什么 import 名是 `jobws_core` 而不是 `jobws`**（2026-09-17 实测踩到）：
`tools/jobws.py` 是 CLI 入口**模块**，全仓 68 个用例与 `jobws.py` 自身都以
`import jobws` 取它。包若也叫 `jobws`，源码形态下（src 在 sys.path 里）会
抢先命中包 → `jobws.main()` 直接 AttributeError。**CLI 模块名优先**，故包名
加 `_core` 后缀（distribution 名仍是 `jobws-core`）。

**本包不是产品**：版本是 `web/electron/package.json` 的**派生物**（构建期写入、
运行时从 `importlib.metadata` 读回），不是第二套版本真值源。

**门面刻意极薄**：只暴露 `__version__`，不预导入任何子模块——
① 避免 import 副作用与启动开销；② `import jobws_core.filelock` 这类子模块导入
本就会先执行本文件，无需在此 `from . import ...`；③ 将来 tracker 主体迁入时
需要转发**可变全局**（WORKSPACE），届时必须用 PEP 562 的 `__getattr__` 转发
而不是 `from ._core import WORKSPACE`（值快照不跟随重绑定，见
`tools/tracker/__init__.py` 的完整论证）。
"""

from ._version import __version__

__all__ = ["__version__"]
