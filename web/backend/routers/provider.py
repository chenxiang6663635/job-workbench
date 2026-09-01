# -*- coding: utf-8 -*-
"""BYOK Provider 配置：读写 OpenAI 兼容端点的 base_url 与 key，并提供连通性测试。

一期只做配置骨架 + 连通性测试（调 {base_url}/models），不接真实 LLM 调用——
评分判断仍由 AI CLI / 用户完成。key 只存本地 JSON，返回时脱敏，日志不打印。
"""

from __future__ import annotations

import io
import json
import os
import ssl
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import safe_join, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/provider")

CONFIG_FILE = "provider.json"
# 连通性测试超时（秒），避免 key 无效或网络异常时卡死
TEST_TIMEOUT = 10


class ProviderConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""


def _config_path(ws):
    """Provider 配置存工作区 config/ 下。"""
    return safe_join(ws, "config", CONFIG_FILE)


def _lock_path(ws):
    """Provider 锁文件。与配置内容分离，避免 file_lock 锁内容文件本身在 Windows 上的问题。"""
    return safe_join(ws, "config", "provider.lock")


def _read_config(path):
    if not os.path.isfile(path):
        return {"base_url": "", "api_key": ""}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "base_url": data.get("base_url", ""),
            "api_key": data.get("api_key", ""),
        }
    except (ValueError, OSError):
        return {"base_url": "", "api_key": ""}


def _mask_key(key):
    """key 脱敏：只显示末尾 4 位，其余用 * 遮挡。空 key 原样返回。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


@router.get("")
def get_provider(ws: str = Depends(workspace_dir)):
    """读当前工作区的 Provider 配置，key 脱敏。"""
    path = _config_path(ws)
    cfg = _read_config(path)
    return {
        "base_url": cfg["base_url"],
        "api_key": _mask_key(cfg["api_key"]),
        "hasKey": bool(cfg["api_key"]),
    }


class SaveProvider(BaseModel):
    base_url: str = ""
    api_key: str = ""  # 传完整新 key 则覆盖；传空则保留原 key


@router.post("")
def save_provider(body: SaveProvider, ws: str = Depends(workspace_dir)):
    """保存 Provider 配置。api_key 传空则保留原 key（前端不来回传完整 key）。"""
    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 用独立锁文件（provider.lock），避免锁内容文件本身
    lock_path = _lock_path(ws)
    with file_lock(lock_path):
        cfg = _read_config(path)
        base_url = body.base_url.strip()
        # 去掉末尾 /v1 之前的部分不做规范化，由前端/用户决定；仅校验协议头
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise HTTPException(status_code=422, detail="base_url 必须以 http:// 或 https:// 开头")
        new_key = (body.api_key or "").strip()
        cfg["base_url"] = base_url
        if new_key:
            cfg["api_key"] = new_key

        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    return {
        "base_url": cfg["base_url"],
        "api_key": _mask_key(cfg["api_key"]),
        "hasKey": bool(cfg["api_key"]),
    }


@router.post("/test")
def test_provider(ws: str = Depends(workspace_dir)):
    """连通性测试：调 {base_url}/models 验证 key 有效。超时控制，失败给人话。"""
    path = _config_path(ws)
    cfg = _read_config(path)
    if not cfg["base_url"]:
        raise HTTPException(status_code=400, detail="请先保存 Provider 的 base_url")
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="请先保存 Provider 的 api_key")

    # 规范化：base_url 末尾去掉斜杠
    base = cfg["base_url"].rstrip("/")
    url = base + "/models"

    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % cfg["api_key"],
        "Content-Type": "application/json",
    })
    # 不用 ssl.create_default_context()：它加载 Windows 系统证书存储，
    # 在本机触发 ASN1: NOT_ENOUGH_DATA 崩溃（与目标 Provider 无关的环境 bug）。
    # 连通性测试是本地配置检查，用 unverified context 即可（不加载证书库）。
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=TEST_TIMEOUT, context=ctx) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=502, detail="连接失败（HTTP %s）：%s" % (e.code, _http_hint(e.code)))
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        raise HTTPException(status_code=502, detail="无法连接 %s：%s" % (base, reason or e))
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=502, detail="连接异常：%s" % e)

    models = data.get("data", []) if isinstance(data, dict) else []
    model_names = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")] if isinstance(models, list) else []
    return {
        "ok": True,
        "status": status,
        "modelCount": len(model_names),
        "models": model_names[:20],
    }


def _http_hint(code):
    if code in (401, 403):
        return "api_key 无效或无权限，请检查控制台生成的 key"
    if code == 404:
        return "base_url 路径可能不对，OpenAI 兼容端点应为 .../v1"
    return "请检查 base_url 与 key 是否正确"
