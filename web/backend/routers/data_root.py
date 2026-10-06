# -*- coding: utf-8 -*-
"""数据根控制面（A3/B2）：读回诊断 / 记住选择 / 清除选择 / 迁移事务。

为什么单独一个模块：`routers/system.py` 的水位只许变小（登记 332 行），而
这些路由与「导出 / 快照 / 打开目录」不是一件事——它们是 spec 决策 4 / 5 的
**补救与迁移通道**：失效态（unavailable）下用户必须能重选或清除数据根；
搬家则必须是可预览、可确认、可续跑、可回滚的事务（B2 引导式迁移）。

两条纪律：
- **三态下都可用**：不依赖 `workspace_dir`，也不走 `_require_usable_data_root`
  ——失效态里工作区解析没有意义，恰恰是这条闸把普通数据端点挡住了；
- 呈现分工（spec §五）：返回的仍是 `dataroot.describe()` 的同一份诊断对象
  （与 CLI `doctor` / MCP `jobws.info` 同源）——本模块只做「写动作 + 序列化」。

迁移协议（spec 决策 5 的「预览 → 确认」形状，与 MCP 的 preview_* → apply
同构但独立实现）：
- `POST /data-root/migrate/preview`：纯读计划（清单 + 预检），**永远 200**——
  blocked 与否是**报告内容**，不是传输错误；附 `plan_token`（计划指纹，
  `dataroot_migrate.plan_fingerprint`）；
- `POST /data-root/migrate/apply`：先看计划本身（blocked → 409），再凭
  `plan_token` 复核「确认的就是这份计划」（不一致 → 409
  `sys.dataRootPlanStale`）——源数据在预览与确认之间变过就绝不按旧计划执行；
  成功返回事务结果（`status: done`），引擎失败**也是 200**（`status: failed`
  + 原因——那是事务报告，状态机停在 failed 等续跑，不是服务器坏了）。

错误码：`sys.dataRootInvalidPath`（400）与 `sys.dataRootWriteFailed`（500）为
A3 既有；B2 新增 `sys.dataRootPlanStale` / `sys.dataRootMigrateBlocked`（409）
与 `sys.dataRootMigrateFailed`（500，控制面 IO）——同族中英双语键在
`web/frontend/src/i18n/locales/`。
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from jobws_core import dataroot, dataroot_migrate as migrate
from apierror import ApiError

router = APIRouter(prefix="/api/system")


class DataRootBody(BaseModel):
    path: str = ""


class MigratePreviewBody(BaseModel):
    target: str = ""


class MigrateApplyBody(BaseModel):
    target: str = ""
    plan_token: str = ""


class MigrateActionBody(BaseModel):
    apply: bool = False


def _diagnose():
    """同一份诊断对象：与 CLI / MCP / 设置页共用的单一事实源。"""
    from deps import ROOT  # 函数内 import：与 system.py 的延迟依赖同款
    workspace_name = (os.environ.get("JOBWS_WORKSPACE") or "").strip() \
        or dataroot.DEFAULT_WORKSPACE_NAME
    return dataroot.describe(dataroot.form_for_process(), ROOT,
                             workspace_name=workspace_name)


def _migrate_source_root():
    """迁移的源根 = 当前生效的数据根（与诊断对象同一条解析链）。"""
    from deps import ROOT
    res = dataroot.resolve_data_root(dataroot.form_for_process(), ROOT)
    return res.path


def _plan_view(plan):
    """计划的前端视图（逐文件清单不进响应——事务记录里有全量）。"""
    manifest = plan.get("manifest") or {}
    return {
        "ok": plan["ok"],
        "already_current": plan["already_current"],
        "source_root": plan["source_root"],
        "target_root": plan["target_root"],
        "workspace": plan["workspace"],
        "target_workspace": plan["target_workspace"],
        "staging": plan["staging"],
        "root_id": plan["root_id"],
        "entries": len(manifest.get("entries") or []),
        "skipped": len(manifest.get("skipped") or []),
        "links": manifest.get("links") or [],
        "total_bytes": manifest.get("total_bytes"),
        "free_bytes": plan.get("free_bytes"),
        "reasons": plan.get("reasons") or [],
        "plan_token": migrate.plan_fingerprint(plan),
    }


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


# --- 迁移事务（B2 引导式迁移；状态机与三条纪律见 dataroot_migrate）----------------

@router.post("/data-root/migrate/preview")
def migrate_preview(body: MigratePreviewBody):
    """计划一次迁移：纯读（清单 + 预检），不写任何东西；blocked 是报告内容。"""
    plan = migrate.plan(body.target, _migrate_source_root())
    return _plan_view(plan)


@router.post("/data-root/migrate/apply")
def migrate_apply(body: MigrateApplyBody):
    """执行迁移：先看计划（blocked → 409），再凭指纹复核，然后 copy → verify → switch。"""
    plan = migrate.plan(body.target, _migrate_source_root())
    if plan.get("already_current"):
        return {"status": "noop", "already_current": True}
    if not plan["ok"]:
        raise ApiError(409, "sys.dataRootMigrateBlocked", migrate.reasons_text(plan),
                       reason=migrate.reasons_text(plan))
    if migrate.plan_fingerprint(plan) != (body.plan_token or "").strip():
        raise ApiError(409, "sys.dataRootPlanStale",
                       "迁移计划与预览时不一致（源数据或参数已变化）——请重新预览后再确认",
                       target=body.target)
    try:
        return migrate.apply(plan)
    except OSError as exc:
        raise ApiError(500, "sys.dataRootMigrateFailed",
                       "迁移事务记录写入失败：%s（源目录未受影响）" % exc, error=str(exc))


@router.post("/data-root/migrate/resume")
def migrate_resume(body: MigrateActionBody):
    """续跑在途事务（apply=false 是演练：只报相位与差量，不写任何东西）。"""
    try:
        return migrate.resume(apply=body.apply)
    except OSError as exc:
        raise ApiError(500, "sys.dataRootMigrateFailed",
                       "迁移事务记录写入失败：%s（源目录未受影响）" % exc, error=str(exc))


@router.post("/data-root/migrate/rollback")
def migrate_rollback(body: MigrateActionBody):
    """把持久化选择指回旧根（不删、不回搬；apply=false 是演练）。"""
    try:
        return migrate.rollback(apply=body.apply)
    except OSError as exc:
        raise ApiError(500, "sys.dataRootMigrateFailed",
                       "迁移事务记录写入失败：%s（源目录未受影响）" % exc, error=str(exc))
