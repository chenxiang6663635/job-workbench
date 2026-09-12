# -*- coding: utf-8 -*-
"""IMAP 只读配置与拉取：凭证存工作区本地、连通性测试、拉取最近邮件。

三条边界（与实时投递状态的调研红线一致）：

1. **凭证只存本地**：`<工作区>/config/imap.json`，读取接口返回脱敏值，
   传空密码表示保留原值；错误消息与日志不出现完整凭证。
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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import imap_fetch
from atomicio import atomic_write_text
from deps import safe_join, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/imap")

CONFIG_FILE = "imap.json"


def _config_path(ws):
    """IMAP 配置存工作区 config/ 下（与 provider.json 同级，文件名独立）。"""
    return safe_join(ws, "config", CONFIG_FILE)


def _lock_path(ws):
    """独立锁文件：与配置内容分离，避免 file_lock 锁内容文件本身的问题（同 provider）。"""
    return safe_join(ws, "config", "imap.lock")


def _empty_config():
    return {
        "host": "",
        "port": imap_fetch.DEFAULT_PORT,
        "user": "",
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
    for key in ("host", "user", "password", "folder"):
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
    """授权码脱敏：只显示末 4 位；空值原样返回。"""
    if not password:
        return ""
    if len(password) <= 4:
        return "****"
    return "*" * (len(password) - 4) + password[-4:]


def _public(cfg):
    """对外响应：不含完整密码；附服务器推断提示便于前端展示。"""
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "folder": cfg["folder"],
        "password": _mask_password(cfg["password"]),
        "hasPassword": bool(cfg["password"]),
        # 前端提示用：留空 host 时实际会连哪台服务器（未知域名返回空串）
        "serverHint": imap_fetch.guess_server(cfg["user"]),
    }


def _resolve_host(cfg):
    """host 留空时按邮箱域名推断；推断不出就明确让人话报错。"""
    host = cfg["host"] or imap_fetch.guess_server(cfg["user"])
    if not host:
        raise HTTPException(
            status_code=400,
            detail="IMAP 服务器地址为空且无法按邮箱域名推断：请在设置里手填服务器地址")
    return host


@router.get("")
def get_imap(ws: str = Depends(workspace_dir)):
    """读当前工作区的 IMAP 配置，授权码脱敏。"""
    return _public(_read_config(_config_path(ws)))


class SaveImap(BaseModel):
    host: str = ""
    port: int = imap_fetch.DEFAULT_PORT
    user: str = ""
    password: str = ""  # 传完整新授权码则覆盖；传空则保留原值
    folder: str = imap_fetch.DEFAULT_FOLDER


@router.post("")
def save_imap(body: SaveImap, ws: str = Depends(workspace_dir)):
    """保存 IMAP 配置。password 传空则保留原值（前端不来回传完整凭证）。"""
    if not (1 <= body.port <= 65535):
        raise HTTPException(status_code=422, detail="端口需在 1–65535 之间")

    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with file_lock(_lock_path(ws)):
        cfg = _read_config(path)
        cfg["host"] = body.host.strip()
        cfg["port"] = body.port
        cfg["user"] = body.user.strip()
        cfg["folder"] = body.folder.strip() or imap_fetch.DEFAULT_FOLDER
        new_password = (body.password or "").strip()
        if new_password:
            cfg["password"] = new_password

        # 原子写：并发读（GET/test/fetch）不会看到半截文件；
        # 写仍持锁，两次并发保存不会互相覆盖。
        atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2))

    return _public(cfg)


@router.post("/test")
def test_imap(ws: str = Depends(workspace_dir)):
    """连通性测试：真实连接一次（登录 + 只读打开文件夹 + 登出）。

    只验证凭证与服务器；不读取任何邮件内容，也不改服务端任何状态。
    """
    cfg = _read_config(_config_path(ws))
    if not cfg["user"]:
        raise HTTPException(status_code=400, detail="请先保存邮箱地址")
    if not cfg["password"]:
        raise HTTPException(status_code=400, detail="请先保存 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = cfg["folder"] or imap_fetch.DEFAULT_FOLDER
    try:
        count = imap_fetch.test_connection(
            host, cfg["user"], cfg["password"], cfg["port"], folder)
    except imap_fetch.ImapFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "ok": True,
        "server": host,
        "folder": folder,
        "messageCount": count,
        "note": "只读连接成功；本次测试没有读取、修改或删除任何邮件。",
    }


class FetchRequest(BaseModel):
    limit: int = imap_fetch.DEFAULT_LIMIT
    folder: str = ""  # 可选覆盖配置里的文件夹
    # 只拉最近 N 天；0 = 不限（取最近 limit 封）。
    # 用 Optional：前端显式传 null 时不该 422（pydantic v2 的坑，同阶段 2 注释）
    since_days: Optional[int] = imap_fetch.DEFAULT_SINCE_DAYS


@router.post("/fetch")
def fetch_imap(body: FetchRequest, ws: str = Depends(workspace_dir)):
    """拉取最近邮件（只读取样，默认 dry-run）。

    **不写任何数据**：返回的邮件正文只是给「解析 → 建议 → 用户确认」
    链路做输入素材；追踪表的改动一律走 apply-status-suggestion。
    """
    cfg = _read_config(_config_path(ws))
    if not cfg["user"]:
        raise HTTPException(status_code=400, detail="请先在设置里配置邮箱地址")
    if not cfg["password"]:
        raise HTTPException(status_code=400, detail="请先在设置里配置 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = (body.folder or cfg["folder"] or imap_fetch.DEFAULT_FOLDER).strip()
    since_days = body.since_days or 0

    try:
        messages = imap_fetch.fetch_messages(
            host, cfg["user"], cfg["password"], cfg["port"], folder,
            body.limit, since_days)
    except imap_fetch.ImapFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "messages": messages,
        "count": len(messages),
        "server": host,
        "folder": folder,
        "sinceDays": since_days,
        "dryRun": True,
        "note": "只读拉取，未改动任何数据；状态改动需要你逐条确认后才会写回。",
    }
