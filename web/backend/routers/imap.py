# -*- coding: utf-8 -*-
"""IMAP 只读配置与拉取：凭证存工作区本地、连通性测试、拉取最近邮件。

三条边界（与实时投递状态的调研红线一致）：

1. **授权码存系统凭据管理器**：桌面版写 **Windows 凭据管理器**，配置文件
   `<工作区>/config/imap.json` 里只留引用 `auth_ref`；源码 / CLI 形态是显式
   明文回退（密文留在那个文件里）。读取接口返回脱敏值，传空密码表示保留原值；
   错误消息与日志不出现完整凭证。
2. **只读、默认 dry-run**：拉取走 `tools/imap_fetch.py`（select 只读 +
   BODY.PEEK），`/fetch` 只返回邮件列表供用户挑选——**不写任何数据**。
   状态改动仍然只发生在用户逐条确认后的
   `POST /api/applications/apply-status-suggestion`（阶段 2 的链路原样复用）。
3. **无后台路径**：这里所有端点都是「用户点了才连一次」——不存在定时器、
   轮询、连接保活或后台任务；校验失败也不会留下半开会话。
   面向用户的文案不承诺任何形式的后台运行，也不使用那类措辞。

这不是邮箱托管功能：它是一次性的只读取样，样本怎么用由用户逐条决定。
"""

from __future__ import annotations

import io
import json
import os
from jobws_core import credentials, tls_policy

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import credential_fields
import imap_fetch
import imapguard
from apierror import ApiError
from atomicio import atomic_write_text
from deps import safe_join, workspace_dir
from imap_host import check_host_shape
from lockctx import lock_path, locked
from redact import mask_secret

router = APIRouter(prefix="/api/imap")

CONFIG_FILE = "imap.json"


def _config_path(ws):
    """IMAP 配置存工作区 config/ 下（与 provider.json 同级，文件名独立）。"""
    return safe_join(ws, "config", CONFIG_FILE)


def _lock_path(ws):
    """独立锁文件（走 lockctx）：与配置内容分离，避免 locked 锁内容文件本身的问题（同 provider）。"""
    return lock_path(ws, "imap")


def _empty_config():
    return {
        "host": "",
        "port": imap_fetch.DEFAULT_PORT,
        "user": "",
        "auth_ref": "",     # 凭据管理器条目的引用（credman 形态；明文形态为空）
        "password": "",
        "folder": imap_fetch.DEFAULT_FOLDER,
    }


def _read_config(path):
    """读配置。逐字段容错：类型不对的字段回落到默认值，绝不因一条脏字段整体失败。"""
    cfg = _empty_config()
    if not os.path.isfile(path):
        return cfg
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    for key in ("host", "user", "auth_ref", "password", "folder"):
        value = data.get(key)
        if isinstance(value, str):
            cfg[key] = value
    raw_port = data.get("port", cfg["port"])
    # 只接受真正的整数：float（如 993.5）会被 int() 静默取整，字符串会被强转——
    # 那类"看起来接受了"的脏值比明确回落默认更危险
    if isinstance(raw_port, int) and not isinstance(raw_port, bool):
        if 1 <= raw_port <= 65535:
            cfg["port"] = raw_port
    return cfg


def _mask_password(password):
    """授权码脱敏。实现已收进 `redact.mask_secret`（issue #50 m2：与 Provider 的
    `_mask_key` 逐字相同，抽公共模块）；保留私名只因为调用点读起来更贴域。"""
    return mask_secret(password)


def _resolve(cfg, ws, *, strict, persist=True):
    """解析授权码（必要时迁移旧明文并落盘；接线在 `credential_fields`，与 provider 共用）。

    `strict=True`（/test 与 /fetch）区分 secret=None 的两种含义：「引用在手但系统
    存储取不到」是凭据没了（409，出路是重新保存），「两边都没配」才是没配置过。

    `persist=False` 供**已持锁**的调用点（POST）用：迁移结果由调用方在同一次原子写
    里落盘——`file_lock` 不重入，锁内再 `locked()` 只会等到超时。
    """
    kwargs = dict(path=_config_path(ws), ws=ws, ref_key="auth_ref",
                  legacy_key="password", prefix="imap", lock_name="imap",
                  # 展示面顺带迁移时可能撞上并发保存：锁内重读、只应用引用变更（见 credential_fields）
                  reload=lambda: _read_config(_config_path(ws)))
    if strict:
        return credential_fields.resolve_strict(
            cfg, error_code="imap.credentialUnavailable",
            error_message="凭据在本机凭据管理器里找不到（可能换了 Windows 账户或被系统清理），"
                          "请在设置里重新保存 IMAP 授权码", **kwargs)
    return credential_fields.resolve(cfg, persist=persist, **kwargs)


# host 形状校验搬去 `imap_host`（#203 收口批：让 imap.py 回到尺寸预算内）。保留私名
# 别名：旧名 `_check_host_shape` 照旧可用（低成本的兼容兜底，无其它模块引用）。
_check_host_shape = check_host_shape


def _public(cfg, outcome):
    """对外响应：不含完整密码；附服务器推断提示便于前端展示。

    `storage` 如实报告本次解析的形态（credman / plaintext）：前端据此说明
    "授权码已存进系统凭据管理器"；写失败退回明文时也能说清它还在文件里。
    """
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "folder": cfg["folder"],
        "password": _mask_password(outcome.secret or ""),
        "hasPassword": bool(outcome.secret),
        "storage": outcome.kind,
        # 前端提示用：留空 host 时实际会连哪台服务器（未知域名返回空串）
        "serverHint": imap_fetch.guess_server(cfg["user"]),
    }


def _resolve_host(cfg):
    """host 留空时按邮箱域名推断；推断不出就明确让人话报错。"""
    host = cfg["host"] or imap_fetch.guess_server(cfg["user"])
    if not host:
        raise ApiError(
            400, "imap.hostUnknown",
            "IMAP 服务器地址为空且无法按邮箱域名推断：请在设置里手填服务器地址")
    # 推断出来的值也走同一道形状校验：坏值的终点都一样（连接期一句"连不上"）
    return _check_host_shape(host)


@router.get("")
def get_imap(ws: str = Depends(workspace_dir)):
    """读当前工作区的 IMAP 配置，授权码脱敏。

    lenient（不抛）：引用在手但取不到时照常 200（hasPassword=False、
    storage=credman）——用户打开设置页先要能看见现状；报错留给真正要使用
    凭据的 /test 与 /fetch。顺带做一次惰性迁移（见 `_resolve`）。
    """
    cfg = _read_config(_config_path(ws))
    return _public(cfg, _resolve(cfg, ws, strict=False))


class SaveImap(BaseModel):
    host: str = ""
    port: int = imap_fetch.DEFAULT_PORT
    user: str = ""
    password: str = ""  # 传完整新授权码则覆盖；传空则保留原值
    folder: str = imap_fetch.DEFAULT_FOLDER


@router.post("")
def save_imap(body: SaveImap, ws: str = Depends(workspace_dir)):
    """保存 IMAP 配置。password 传空则保留原值（前端不来回传完整凭证）。

    授权码优先写系统凭据管理器（桌面版的 Windows 凭据管理器），配置文件里只留
    引用 `auth_ref`；写失败退回明文（`storage` 字段如实告知，见 credentials 铁律）。
    """
    if not (1 <= body.port <= 65535):
        raise ApiError(422, "imap.portRange", "端口需在 1–65535 之间")

    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store = credential_fields.store()

    with locked(_lock_path(ws)):
        cfg = _read_config(path)
        raw_host = body.host.strip()
        # 留空是合法输入（表示"按邮箱域名推断"）；非空则先过形状校验
        cfg["host"] = _check_host_shape(raw_host) if raw_host else ""
        cfg["port"] = body.port
        cfg["user"] = body.user.strip()
        cfg["folder"] = body.folder.strip() or imap_fetch.DEFAULT_FOLDER
        new_password = (body.password or "").strip()
        if new_password:
            kind = credentials.store_secret(
                cfg, new_password, ref_key="auth_ref", legacy_key="password",
                prefix="imap", store=store)
            outcome = credentials.ResolveOutcome(new_password, kind, False)
        else:
            # 传空 = 保留原值，顺带把旧明文惰性迁移进系统存储。persist=False：
            # 迁移的落盘并入本块的统一原子写（锁不重入，见 `_resolve`）。
            outcome = _resolve(cfg, ws, strict=False, persist=False)

        # 原子写：并发读（GET/test/fetch）不会看到半截文件；
        # 写仍持锁，两次并发保存不会互相覆盖。
        atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2))

    return _public(cfg, outcome)


@router.post("/test")
def test_imap(ws: str = Depends(workspace_dir)):
    """连通性测试：真实连接一次（登录 + 只读打开文件夹 + 登出）。

    只验证凭证与服务器；不读取任何邮件内容，也不改服务端任何状态。
    """
    cfg = _read_config(_config_path(ws))
    if not cfg["user"]:
        raise ApiError(400, "imap.needEmail", "请先保存邮箱地址")
    # strict：引用在手却取不到 → 409「重新保存」（不是 400「没配置」）
    outcome = _resolve(cfg, ws, strict=True)
    if outcome.secret is None:
        raise ApiError(400, "imap.needPassword", "请先保存 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = cfg["folder"] or imap_fetch.DEFAULT_FOLDER
    try:
        count = imap_fetch.test_connection(
            host, cfg["user"], outcome.secret, cfg["port"], folder)
    except imap_fetch.ImapFetchError as exc:
        raise ApiError(502, exc.code or "imap.testFailed", str(exc), error=str(exc))

    note = "只读连接成功；本次测试没有读取、修改或删除任何邮件。"
    if tls_policy.is_insecure(tls_policy.IMAP_ENV_VAR):
        # 降级是用户显式选的，但界面上必须再说一次（日志没人看，界面天天看）。措辞要留余地：
        # 降级只在**本机证书库加载失败**时才真的生效，证书库正常时上下文仍严格校验
        # （tls_policy 口径第 1 条）——写成「已跳过校验」会在大多数机器上说假话（审查 m1）。
        note += ("注意：已设置 %s=insecure——本机证书库可用时仍严格校验，"
                 "仅在其加载失败时才跳过证书与主机名校验；"
                 "用完请取消该环境变量。" % tls_policy.IMAP_ENV_VAR)

    return {
        "ok": True,
        "server": host,
        "folder": folder,
        "messageCount": count,
        # note 是给人看的展示句，界面语言该由渲染方决定：前端用
        # settings.imapTestNote 自己渲染，这里保留字段只为不破坏既有响应契约。
        "note": note,
    }


class FetchRequest(BaseModel):
    limit: int = imap_fetch.DEFAULT_LIMIT
    folder: str = ""  # 可选覆盖配置里的文件夹
    # 只拉最近 N 天，0 = 不限；Optional 是给前端显式传 null 用（不该 422）
    since_days: Optional[int] = imap_fetch.DEFAULT_SINCE_DAYS


@router.post("/fetch")
def fetch_imap(body: FetchRequest, ws: str = Depends(workspace_dir)):
    """拉取最近邮件（只读取样，默认 dry-run）。

    **不写任何数据**：返回的邮件正文只是给「解析 → 建议 → 用户确认」
    链路做输入素材；追踪表的改动一律走 apply-status-suggestion。
    """
    cfg = _read_config(_config_path(ws))
    if not cfg["user"]:
        raise ApiError(400, "imap.needEmail", "请先在设置里配置邮箱地址")
    # strict：引用在手却取不到 → 409「重新保存」（不是 400「没配置」）
    outcome = _resolve(cfg, ws, strict=True)
    if outcome.secret is None:
        raise ApiError(400, "imap.needPassword", "请先在设置里配置 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = (body.folder or cfg["folder"] or imap_fetch.DEFAULT_FOLDER).strip()
    since_days = body.since_days or 0
    imapguard.check_fetch_range(since_days, body.limit)  # 越界 422（见模块说明）

    try:
        messages = imap_fetch.fetch_messages(
            host, cfg["user"], outcome.secret, cfg["port"], folder,
            body.limit, since_days)
    except imap_fetch.ImapFetchError as exc:
        raise ApiError(502, exc.code or "imap.fetchFailed", str(exc), error=str(exc))

    return {
        "messages": messages,
        "count": len(messages),
        "server": host,
        "folder": folder,
        "sinceDays": since_days,
        "dryRun": True,
        "note": "只读拉取，未改动任何数据；状态改动需要你逐条确认后才会写回。",
    }
