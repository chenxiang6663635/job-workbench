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
import socket
from jobws_core import tls_policy
import unicodedata

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import imap_fetch
from apierror import ApiError
from atomicio import atomic_write_text
from deps import safe_join, workspace_dir
from jobws_core.filelock import file_lock
from redact import mask_secret

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
    """授权码脱敏。实现已收进 `redact.mask_secret`（issue #50 m2：与 Provider 的
    `_mask_key` 逐字相同，抽公共模块）；保留私名只因为调用点读起来更贴域。"""
    return mask_secret(password)


# DNS 名字的通用上限（RFC 1035：253 个字符）
MAX_HOST_LEN = 253


def _is_ipv6_literal(host):
    """是不是 IPv6 字面量——含冒号但**不是** host:port。

    认三种写法：`[::1]`、裸 `::1`，以及带作用域标识的 `fe80::1%eth0`
    （`inet_pton` 不认 `%eth0`，剥掉再判——否则合法地址会被误报成
    "端口请填另一栏"）。
    """
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    candidate = candidate.split("%", 1)[0]
    try:
        socket.inet_pton(socket.AF_INET6, candidate)
        return True
    except (OSError, ValueError):
        return False


def _check_host_shape(host):
    """使用前的 host 形状校验（issue #50 A1），返回原值。

    为什么是"使用前"而不只是"保存时"：保存校验是后加的，老配置里可能已经存着
    坏值；而且留空 host 时推断出来的值也该走同一道关。坏值最终都会在 `_connect`
    里变成"连不上 993 端口"——那句话对用户没有任何指向性，真正的原因（把
    `https://` 或 `host:port` 整段粘了进来）必须在**换得出正确说法的地方**报出来。

    分三个 code 而不是一个通用 code：三种形状问题的**出路不一样**（去掉协议头 /
    端口填另一栏 / 只填主机名），合成一句话等于把可操作的指引磨成一句废话，
    英文界面也只能渲染成同一段含糊文案。

    形状判定先做 **NFKC 归一化**：中文输入法下 `imap.qq.com：993`（全角冒号）
    是一敲就出来的形态，ASCII 判定看不住它，结果就退回到"连接期一句连不上"。
    归一化**只用于判定**，落盘与响应里仍是用户输入的原值。
    """
    probe = unicodedata.normalize("NFKC", host)
    if len(probe) > MAX_HOST_LEN:
        raise ApiError(422, "imap.hostTooLong",
                       "服务器地址过长（%d 字符，上限 %d）：只填主机名，不要带路径"
                       % (len(probe), MAX_HOST_LEN),
                       length=len(probe))
    if "://" in probe:
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不要带协议头：去掉 http:// 或 https://，"
                       "只填主机名（如 imap.qq.com）")
    if "/" in probe:
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不能含斜杠：只填主机名，路径不要写进来")
    if any(ch.isspace() for ch in probe):
        raise ApiError(422, "imap.hostMalformed",
                       "服务器地址不能含空格：请检查是否多粘了一段")
    if ":" in probe and not _is_ipv6_literal(probe):
        raise ApiError(422, "imap.hostPortInline",
                       "端口请填在「端口」栏：地址里不要写成 host:port"
                       "（例如 imap.qq.com:993 应拆成两栏）")
    return host


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
        raise ApiError(
            400, "imap.hostUnknown",
            "IMAP 服务器地址为空且无法按邮箱域名推断：请在设置里手填服务器地址")
    # 推断出来的值也走同一道形状校验：坏值的终点都一样（连接期一句"连不上"）
    return _check_host_shape(host)


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
        raise ApiError(422, "imap.portRange", "端口需在 1–65535 之间")

    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with file_lock(_lock_path(ws)):
        cfg = _read_config(path)
        raw_host = body.host.strip()
        # 留空是合法输入（表示"按邮箱域名推断"）；非空则先过形状校验
        cfg["host"] = _check_host_shape(raw_host) if raw_host else ""
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
        raise ApiError(400, "imap.needEmail", "请先保存邮箱地址")
    if not cfg["password"]:
        raise ApiError(400, "imap.needPassword", "请先保存 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = cfg["folder"] or imap_fetch.DEFAULT_FOLDER
    try:
        count = imap_fetch.test_connection(
            host, cfg["user"], cfg["password"], cfg["port"], folder)
    except imap_fetch.ImapFetchError as exc:
        raise ApiError(502, "imap.testFailed", str(exc), error=str(exc))

    note = "只读连接成功；本次测试没有读取、修改或删除任何邮件。"
    if tls_policy.is_insecure(tls_policy.IMAP_ENV_VAR):
        # 降级是用户显式选的，但界面上必须再说一次——连处于未校验状态这件事
        # 不该只留在日志里（日志没人看，界面天天看）。语义不变，只加提示。
        # 措辞必须留余地：降级只在**本机证书库加载失败**时才真的生效——证书库
        # 正常时上下文仍是严格校验（tls_policy 口径第 1 条）。写成「已跳过校验」
        # 会在大多数机器上说假话（独立审查 m1）。
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
        raise ApiError(400, "imap.needEmail", "请先在设置里配置邮箱地址")
    if not cfg["password"]:
        raise ApiError(400, "imap.needPassword", "请先在设置里配置 IMAP 授权码")

    host = _resolve_host(cfg)
    folder = (body.folder or cfg["folder"] or imap_fetch.DEFAULT_FOLDER).strip()
    since_days = body.since_days or 0

    try:
        messages = imap_fetch.fetch_messages(
            host, cfg["user"], cfg["password"], cfg["port"], folder,
            body.limit, since_days)
    except imap_fetch.ImapFetchError as exc:
        raise ApiError(502, "imap.fetchFailed", str(exc), error=str(exc))

    return {
        "messages": messages,
        "count": len(messages),
        "server": host,
        "folder": folder,
        "sinceDays": since_days,
        "dryRun": True,
        "note": "只读拉取，未改动任何数据；状态改动需要你逐条确认后才会写回。",
    }
