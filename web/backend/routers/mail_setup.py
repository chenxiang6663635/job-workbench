# -*- coding: utf-8 -*-
"""邮箱配置辅助端点：服务商预设清单 + 文件夹候选。

为什么单开一个薄路由：这两件事都不属于 `routers/imap.py` 的职责（配置读写 /
连通性测试 / 只读拉取），而那个文件登记 304 行、只许变小——同 `imap_facts.py`、
`snapshot.py`、`diagnostics.py`、`reminders.py` 的先例。

两条边界与主路由一致：

1. **凭证只存本地**：本模块不读也不写任何凭证文件，只复用主路由的读配置与
   host 解析（同一套形状校验与推断口径，避免两处漂移）；
2. **无后台路径**：文件夹候选是用户点开下拉时的一次连接，连完即登出。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from jobws_core import mail_providers

import imap_fetch
from apierror import ApiError
from deps import workspace_dir
from routers import imap as imap_routes

router = APIRouter(prefix="/api/mail")


def _public_provider(entry):
    """预设表 → 前端下拉需要的字段（内部字段不外露）。"""
    item = {
        "id": entry["id"],
        "labelKey": entry["labelKey"],
        "domains": list(entry["domains"]),
        "host": entry["host"],
        "port": entry["port"],
        # 界面要据此显示「这一步必须用授权码 / 应用专用密码」
        "requiresAppPassword": bool(entry["requiresAppPassword"]),
        "authHintKey": entry["authHintKey"],
        "docUrl": entry.get("docUrl", ""),
        # 163 / 126 / yeah.net 必须先在 SELECT 前声明身份（否则 Unsafe Login）
        "imapIdRequired": bool(entry["imapIdRequired"]),
        "unsupported": bool(entry.get("unsupported", False)),
    }
    reason = entry.get("unsupportedReasonKey")
    if reason:
        item["unsupportedReasonKey"] = reason
    return item


@router.get("/providers")
def list_providers():
    """邮箱服务商预设清单。

    **纯数据**：不读工作区、不连网、不含任何凭证字段——前端在还没选工作区时
    也要能画出这张下拉。
    """
    return {
        "items": [_public_provider(entry) for entry in mail_providers.MAIL_PROVIDERS],
        "count": len(mail_providers.MAIL_PROVIDERS),
    }


@router.post("/folders")
def list_folders(ws: str = Depends(workspace_dir)):
    """用已保存的凭证连一次，列出可选文件夹（只读 `LIST`，连完即登出）。

    候选是锦上添花：列不出来时返回空列表（界面退回自由输入），
    但连接或登录失败要给人话——那是用户要修的东西。
    """
    cfg = imap_routes._read_config(imap_routes._config_path(ws))
    if not cfg["user"]:
        raise ApiError(400, "imap.needEmail", "请先保存邮箱地址")
    if not cfg["password"]:
        raise ApiError(400, "imap.needPassword", "请先保存 IMAP 授权码")

    host = imap_routes._resolve_host(cfg)
    try:
        folders = imap_fetch.probe_folders(
            host, cfg["user"], cfg["password"], cfg["port"])
    except imap_fetch.ImapFetchError as exc:
        # 会话层已经把"登录失败"细分成可操作的几类（`imap.unsafeLogin` / `imap.authFailed`）：
        # 那几条的下一步与"列文件夹失败"完全不同，不能被 catch-all 吞掉
        raise ApiError(502, exc.code or "imap.foldersFailed", str(exc), error=str(exc))

    return {"folders": folders, "count": len(folders), "server": host}
