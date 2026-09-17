# -*- coding: utf-8 -*-
"""jobws-mcp：求职工作台的 MCP 服务。

本地优先：读本机的 Markdown / CSV 工作区，不出网。**默认只读**；写入走
两段式（`preview_*` 只给令牌与差异，用户确认后 `apply_approval` 才落盘）。
"""

__version__ = "0.1.0"
