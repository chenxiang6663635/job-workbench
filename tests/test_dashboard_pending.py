# -*- coding: utf-8 -*-
"""看板的「待推进」段（pending）：健康度降序 + 同档 id 升序。

钉住两处实现互为副本的排序口径（`routers/dashboard._pending_health` 与
`mcp/jobws_mcp/dashboard_sections.pending`）：`health_score` 只定档、不排序，
两端此前只按档位 sort——同档多条时文序取决于 sort 稳定性与读表原序，和 CLI
`sort_key`（id 升序）不是同一个口径。这条把同档次序、三档全貌、空值、
跨天边界与终态豁免一次钉住（MCP 侧有对应的纯函数直测）。
"""

import os
import sys
from datetime import date, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import tracker  # noqa: E402
import routers.dashboard as dash  # noqa: E402

TODAY = date(2026, 9, 14)


def _row(**kw):
    row = {f: "" for f in tracker.FIELDS}
    row.update(kw)
    return row


def _pending(rows):
    """直测路由内的排序函数：today 显式传参，不依赖真实日期。"""
    return dash._pending_health(rows, [], TODAY)


def test_pending_orders_by_health_level_then_id():
    rows = [
        # urgent 同档三条：文件里 id 乱序 + 一个空 id → 出去必须 id 升序
        _row(id="7", 公司="云帆智算", 岗位="数据平台", 当前阶段="待投",
             截止日期=(TODAY - timedelta(days=1)).isoformat()),
        _row(id="", 公司="", 岗位="", 当前阶段="待投",
             截止日期=TODAY.isoformat()),
        _row(id="3", 公司="星海智能", 岗位="算法工程师", 当前阶段="待投",
             截止日期=(TODAY - timedelta(days=4)).isoformat()),
        # overdue：下次动作昨天（今天是边界——今天不算逾期，见 id=6）
        _row(id="5", 公司="示例科技", 岗位="后端开发", 当前阶段="已投",
             投递日期=(TODAY - timedelta(days=2)).isoformat(),
             下次动作="跟进 HR", 下次动作日期=(TODAY - timedelta(days=1)).isoformat()),
        # stale：停留 20 天（无时间线条目时基准取投递日期）
        _row(id="9", 公司="旧识网络", 岗位="前端工程师", 当前阶段="一面",
             投递日期=(TODAY - timedelta(days=20)).isoformat()),
        # 不入列：下次动作是今天（未逾期）→ ok
        _row(id="6", 公司="边界公司", 岗位="测试工程师", 当前阶段="已投",
             投递日期=(TODAY - timedelta(days=2)).isoformat(),
             下次动作="今天跟进", 下次动作日期=TODAY.isoformat()),
        # 不入列：截止还远 → ok
        _row(id="4", 公司="从容公司", 岗位="运维工程师", 当前阶段="待投",
             截止日期=(TODAY + timedelta(days=10)).isoformat()),
        # 不入列：终态（level=None）
        _row(id="8", 公司="终结公司", 岗位="产品经理", 当前阶段="已挂"),
    ]

    items = _pending(rows)

    assert [i["id"] for i in items] == ["", "3", "7", "5", "9"]
    assert [i["level"] for i in items] == ["urgent", "urgent", "urgent",
                                           "overdue", "stale"]
    # 空值行进得来、字段是空串而不是 KeyError
    empty = items[0]
    assert empty["公司"] == "" and empty["岗位"] == ""
