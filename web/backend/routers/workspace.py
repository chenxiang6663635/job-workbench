# -*- coding: utf-8 -*-
"""工作区管理：列出、**新建**可用工作区。

工作区判定标准：目录下含 `config/profile.md` 即为有效工作区
（与 tools/jobws.py jd 的 resolve_profile 判定一致，保持单一事实源）。

扫描范围：应用根（ROOT）+ 可写数据根（打包后可能在系统用户目录），
两者都扫并去重——保证便携模式与回退模式下都能列出工作区。
只读扫描，不加缓存——保持 CLI 与 Web 共用同一数据源。

**新建**走的是与命令行完全相同的两段式：`/preview` 只算清单并登记一次性令牌
（**不落盘**），`/apply` 才真正创建。实现直接调 `tools/init_workspace.py` 的
`plan_init` 与 `tools/approval.py` 的 `apply`——网页端不另写一套初始化逻辑，
否则「网页创建的工作区」与「CLI 创建的工作区」迟早长得不一样。
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from jobws_core import approval
import init_workspace
from apierror import ApiError
from deps import ROOT, allowed_roots, data_root, resolve_default_workspace

router = APIRouter(prefix="/api/workspaces")

# demo 数据是配这个插件写的（与 tools/init_workspace.py 的常量同源）
DEMO_DEFAULT_DOMAIN = init_workspace.DEMO_DEFAULT_DOMAIN


@router.get("")
def list_workspaces():
    """扫描含 config/profile.md 标记的目录，返回可用工作区名列表。

    返回项：
      name      目录名（相对路径，即 ?ws= 要传的值）
      isDefault 是否为当前默认工作区
    """
    default = os.path.normpath(resolve_default_workspace())
    items = []
    seen = set()

    for base in allowed_roots():
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue

        for name in entries:
            if name.startswith(".") or name in seen:
                continue
            marker = os.path.join(base, name, "config", "profile.md")
            if os.path.isfile(marker):
                full = os.path.normpath(os.path.join(base, name))
                seen.add(name)
                items.append({
                    "name": name,
                    "isDefault": default == full,
                })

    return {"items": items, "total": len(items)}


@router.get("/domains")
def list_domains():
    """可装入的领域插件——新建工作区向导的第 2 步要选一个。

    插件的显示名就写 id（如 `software-backend`）：它本身就是给人读的短标识，
    再维护一份"id → 中文名"的映射只会多一处要同步的地方。
    """
    return {
        "items": [
            {"id": name, "isDemoDefault": name == DEMO_DEFAULT_DOMAIN}
            for name in init_workspace.list_domains()
        ],
        "demoDefault": DEMO_DEFAULT_DOMAIN,
    }


class WorkspaceInitBody(BaseModel):
    name: str
    domain: Optional[str] = None
    demo: bool = False
    force: bool = False


# Windows 保留设备名：这些名字（含带扩展名的形式）不能作目录名，系统会拒绝或
# 把它当设备处理。跨平台一律拦——本产品要在 Windows 上双击即用。
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % i for i in range(1, 10)]
    + ["LPT%d" % i for i in range(1, 10)]
)


def _resolve_new_workspace(name: str) -> str:
    """把工作区名解析成**可写数据根**下的绝对路径；非法或越界即拒绝。

    只收单个目录名，且**不接受会被系统悄悄改写的名字**：首尾空白、尾随点、
    Windows 保留设备名——它们要么让目录名与用户输入的不一致，要么与既有目录
    **静默合并**（`"ws."` 在 Windows 上就是 `"ws"`）。"静默错位比报错危险"
    这条规矩，在目录名上同样适用（独立审查 MAJOR-1）。

    落在数据根（而不是应用根）之下是刻意的：打包安装到不可写位置时，
    数据根会回退到系统用户目录。
    """
    raw = name or ""
    candidate = raw.strip()
    if not candidate:
        raise ApiError(422, "ws.nameRequired", "工作区名不能为空")
    if candidate != raw:
        raise ApiError(422, "ws.nameInvalid",
                       "工作区名不能带首尾空白（会被系统悄悄去掉）", name=raw)
    if (os.path.isabs(candidate) or "/" in candidate or "\\" in candidate
            or candidate in (".", "..") or candidate.startswith(".")):
        raise ApiError(422, "ws.nameInvalid",
                       "工作区名只能是单个目录名（不含路径分隔符、不以点开头）", name=name)
    if candidate.endswith(".") or candidate.split(".")[0].upper() in _RESERVED_NAMES:
        raise ApiError(422, "ws.nameInvalid",
                       "`%s` 不能用作目录名（尾随点会被系统丢掉；CON/NUL 这类是保留名）"
                       % candidate, name=name)

    root = os.path.normpath(data_root())
    full = os.path.normpath(os.path.join(root, candidate))
    # 前缀比较前先 normcase：Windows 文件系统大小写不敏感、而字符串比较敏感——
    # 盘符大小写不同时，正常名字会被误判越界（独立审查 MAJOR-2）。
    try:
        inside = (os.path.normcase(os.path.commonpath([root, full]))
                  == os.path.normcase(root))
    except ValueError:      # 不同盘符
        inside = False
    if not inside or os.path.normcase(full) == os.path.normcase(root):
        raise ApiError(400, "ws.outOfRange", "工作区越出允许范围")
    return full


@router.post("/preview")
def preview_workspace(body: WorkspaceInitBody):
    """预览新建工作区（**不落盘**）：返回一次性令牌与「将新建 / 将覆盖」清单。

    前端要把 diff **展示给用户**、拿到确认后再调 `/apply`——这正是「首启引导」
    需要的流程：新建是低频且不可逆的动作，值得多一次确认。
    """
    target = _resolve_new_workspace(body.name)
    errors, plan = init_workspace.plan_init(target, body.domain, body.demo, body.force)
    if errors:
        detail = "；".join(errors)
        # detail 同时作为 error_params 传下去：前端命中本地化文案时 detail 会被
        # 忽略，具体的失败原因（"找不到领域插件 x"）只能靠参数带过去。
        raise ApiError(422, "ws.initInvalid", detail, detail=detail)

    result = approval.preview("init", target, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {
        "token": result["token"],
        "summary": result["summary"],
        "diff": result["diff"],
        "path": target,
        "expiresAt": result["expires_at"],
    }


class WorkspaceApplyBody(BaseModel):
    token: str


@router.post("/apply")
def apply_workspace(body: WorkspaceApplyBody):
    """凭令牌真正创建工作区（两段式的第二步）。

    令牌绑定的就是目标目录本身，所以这里**不接收路径参数**——"要写哪里"在令牌
    里，"这次请求要执行哪张确认书"才是这里的输入。冲突（预览之后目标被填了内容）
    返回 409，令牌不可用返回 422。
    """
    try:
        result = approval.apply(body.token)
    except approval.ApprovalConflict as exc:
        raise ApiError(409, "ws.initConflict", str(exc))
    except approval.ApprovalError as exc:
        raise ApiError(422, "ws.tokenInvalid", str(exc))
    return {
        "created": result.get("written"),
        "summary": result.get("summary"),
        "path": result.get("path") or "",
    }
