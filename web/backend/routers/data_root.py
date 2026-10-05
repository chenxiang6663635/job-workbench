# -*- coding: utf-8 -*-
"""数据根控制面（A3）：读回诊断 / 记住选择 / 清除选择。

为什么单独一个模块：`routers/system.py` 的水位只许变小（登记 332 行），而
这三条路由与「导出 / 快照 / 打开目录」不是一件事——它们是 spec 决策 4 的
**补救通道**：失效态（unavailable）下用户必须能重选或清除数据根。

两条纪律：
- **三态下都可用**：不依赖 `workspace_dir`，也不走 `_require_usable_data_root`
  ——失效态里工作区解析没有意义，恰恰是这条闸把普通数据端点挡住了；
- 呈现分工（spec §五）：返回的仍是 `dataroot.describe()` 的同一份诊断对象
  （与 CLI `doctor` / MCP `jobws.info` 同源）——本模块只做「写动作 + 序列化」。

错误码：`sys.dataRootInvalidPath`（400，相对 / 空路径）与
`sys.dataRootWriteFailed`（500，磁盘 / 权限问题）——与 A2 的 `sys.dataRoot*`
同族，中英双语键在 `web/frontend/src/i18n/locales/`。
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from jobws_core import dataroot
from apierror import ApiError

router = APIRouter(prefix="/api/system")


class DataRootBody(BaseModel):
    path: str = ""


def _diagnose():
    """同一份诊断对象：与 CLI / MCP / 设置页共用的单一事实源。"""
    from deps import ROOT  # 函数内 import：与 system.py 的延迟依赖同款
    workspace_name = (os.environ.get("JOBWS_WORKSPACE") or "").strip() \
        or dataroot.DEFAULT_WORKSPACE_NAME
    return dataroot.describe(dataroot.form_for_process(), ROOT,
                             workspace_name=workspace_name)


@router.get("/data-root")
def get_data_root():
    """读回数据根诊断（失效态照常可用——要找失败原因的是人）。"""
    return _diagnose()


@router.post("/data-root")
def set_data_root(body: DataRootBody):
    """记住数据根（只接受绝对路径）：写 `<user_data_dir>/state/data-root.json`。"""
    try:
        dataroot.write_persisted_selection(body.path, source="user")
    except ValueError as exc:
        raise ApiError(400, "sys.dataRootInvalidPath", str(exc), path=body.path)
    except OSError as exc:
        raise ApiError(500, "sys.dataRootWriteFailed",
                       "写入持久化选择失败：%s" % exc, error=str(exc))
    return _diagnose()


@router.delete("/data-root")
def clear_data_root():
    """清除持久化选择（幂等）——失效态里的明路之一。"""
    dataroot.clear_persisted_selection()
    return _diagnose()
