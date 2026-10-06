# -*- coding: utf-8 -*-
"""工具注解（MCP 规范 hints，2026-10-05 D1）：把「危险等级」声明给宿主看。

为什么单独一个模块：`server.py` 贴着规模水位线（只许变小），而注解是**一处
定义、十五处引用**；集中在这里也让「等级表」可被测试与文档单点对账。

等级（对齐数据根 spec 决策 7 的「注解 + 宿主强制两手」）：

- `READ_ONLY`：6 个领域只读 + 7 个 `preview_*` + `jobws.info`。preview 不改环境
  （只渲染 diff 与铸一次性令牌），按规范可以声明只读——**两段式纪律不靠注解**，
  靠令牌机制（`apply_approval` 才是唯一写入）。
- `WRITE_CONFIRMED`：`apply_approval` 一个。`destructiveHint` 刻意**不声明**
  （留规范默认 `true`）——apply 会覆盖既有字段（阶段 / 复盘 / 备注等），不宣称
  「仅追加」是保守诚实；宿主按最谨慎路径处理，与「确认后才写」同向。

全部工具 `openWorldHint=False`：本服务只读本机工作区，不联网（AI / IMAP / JD
抓取都在产品另一侧，不经过 MCP 工具面）。

注意：注解是**非强制提示**（规范原文：hints，不可信服务端同样适用）——宿主
可以忽略它们。安全边界始终在服务端：越界拒绝 + 两段式令牌。
"""

from mcp.types import ToolAnnotations

#: 只读 / 预览 / 诊断：不改环境、闭合世界。
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

#: 唯一写入工具：非只读、非幂等（令牌一次性）、destructiveHint 留默认（保守）。
WRITE_CONFIRMED = ToolAnnotations(read_only_hint=False, idempotent_hint=False,
                                  open_world_hint=False)
