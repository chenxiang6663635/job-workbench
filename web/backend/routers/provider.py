# -*- coding: utf-8 -*-
"""BYOK Provider 配置：读写 OpenAI 兼容端点的 base_url 与 key，并提供连通性测试。

配置读写 + 连通性测试（调 {base_url}/models），同时是 BYOK 的**调用入口**——
简历导入抽取与 AI 改写建议经本配置调真实 LLM（见 routers/resume.py 的
`_call_llm`）。评分判断仍由 AI CLI / 用户完成。key 只存本地 JSON，返回时
脱敏，日志不打印。
"""

from __future__ import annotations

import io
import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import tls_http
from apierror import ApiError
from iocaps import read_response
from atomicio import atomic_write_text
from deps import safe_join, workspace_dir
from lockctx import locked
from redact import mask_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/provider")

CONFIG_FILE = "provider.json"
# 连通性测试超时（秒），避免 key 无效或网络异常时卡死
TEST_TIMEOUT = 10
# /models 结果给界面的条数上限：OpenRouter 之类会返回几千个模型，整包塞过去
# 会同时拖慢响应与渲染。前端只渲染前 N 个，总数照报（见返回里的 modelCount/truncated）。
MODEL_LIST_LIMIT = 50


class ProviderConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


def _config_path(ws):
    """Provider 配置存工作区 config/ 下。"""
    return safe_join(ws, "config", CONFIG_FILE)


def _lock_path(ws):
    """Provider 锁文件。与配置内容分离，避免 locked 锁内容文件本身在 Windows 上的问题。"""
    return safe_join(ws, "config", "provider.lock")


def _empty_config():
    return {"base_url": "", "api_key": "", "model": ""}


def _read_config(path):
    """读配置；坏文件按「未配置」继续，但留一条 warning。

    逐字段容错（类型不对的回落默认值）：**缺 `model` 的旧配置按空串读**，
    所以本批不需要任何数据迁移。
    """
    cfg = _empty_config()
    if not os.path.isfile(path):
        return cfg
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError) as exc:
        # 静默返回空会让「key 怎么消失了」无从排查
        logger.warning("读取 Provider 配置失败，按未配置处理：%s", exc)
        return cfg
    if not isinstance(data, dict):
        return cfg
    for key in ("base_url", "api_key", "model"):
        value = data.get(key)
        if isinstance(value, str):
            cfg[key] = value
    return cfg


def _mask_key(key):
    """key 脱敏。实现已收进 `redact.mask_secret`（issue #50 m2：与 IMAP 的
    `_mask_password` 逐字相同，抽公共模块）；保留私名只因为调用点读起来更贴域。"""
    return mask_secret(key)


def read_config(ws):
    """供其他路由读取完整 Provider 配置（BYOK 调用前）。

    返回含完整 api_key 的字典——调用方不得把 key 写进日志或响应。
    """
    return _read_config(_config_path(ws))


def base_url_hint(base_url):
    """base_url 的**非阻断**提示：返回前端语言包的 key，或 None。

    只报两种确证过的写法，其余一律不提示——Open WebUI 的经验是「验证失败 ≠ 不兼容」：
    很多网关的路径本就是自定义的，误报会让人白改一趟。
    """
    url = (base_url or "").strip().lower()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        # 与前端 lib/providerPresets.validateBaseUrl 保持**同一 key 集合**：正常路径下
        # 缺协议头会被保存时的 422（`provider.baseUrlInvalid`）拦下，这条只防御手改
        # config/provider.json 的存量值——两处 key 不一致时，前端"本地提示优先"的
        # 合并会静默吞掉一边
        return "provider.hintNeedScheme"
    if "dashscope.aliyuncs.com" in url and "compatible-mode" not in url:
        # 通义千问：必须用兼容模式地址，原生 dashscope 路径会一直连不上
        return "provider.hintDashscope"
    if "/chat/completions" in url:
        # 把完整端点当成 base_url 填了：base_url 只到版本段（如 .../v1）
        return "provider.hintEndpointNotBase"
    return None


def _public(cfg):
    """对外响应：key 脱敏 + base_url 的可操作提示（GET 与 POST 共用一份）。"""
    return {
        "base_url": cfg["base_url"],
        "api_key": _mask_key(cfg["api_key"]),
        "hasKey": bool(cfg["api_key"]),
        "model": cfg["model"],
        "baseUrlHint": base_url_hint(cfg["base_url"]),
    }


@router.get("")
def get_provider(ws: str = Depends(workspace_dir)):
    """读当前工作区的 Provider 配置，key 脱敏。"""
    return _public(_read_config(_config_path(ws)))


class SaveProvider(BaseModel):
    base_url: str = ""
    api_key: str = ""  # 传完整新 key 则覆盖；传空则保留原 key
    model: str = ""    # 空串 = 清空默认模型（与 api_key「空则保留」的语义刻意不同）


@router.post("")
def save_provider(body: SaveProvider, ws: str = Depends(workspace_dir)):
    """保存 Provider 配置。api_key 传空则保留原 key（前端不来回传完整 key）。"""
    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 用独立锁文件（provider.lock），避免锁内容文件本身
    lock_path = _lock_path(ws)
    with locked(lock_path):
        cfg = _read_config(path)
        base_url = body.base_url.strip()
        # 去掉末尾 /v1 之前的部分不做规范化，由前端/用户决定；仅校验协议头
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ApiError(422, "provider.baseUrlInvalid",
                           "base_url 必须以 http:// 或 https:// 开头")
        new_key = (body.api_key or "").strip()
        cfg["base_url"] = base_url
        cfg["model"] = (body.model or "").strip()
        if new_key:
            cfg["api_key"] = new_key

        # 原子写：并发读（GET / test / 简历导入的 LLM 调用）不会看到半截文件；
        # 写仍持锁，两次并发保存不会互相覆盖（与 routers/imap.py 同口径）。
        atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2))

    return _public(cfg)


@router.post("/test")
def test_provider(ws: str = Depends(workspace_dir)):
    """连通性测试：调 {base_url}/models 验证 key 有效。超时控制，失败给人话。"""
    path = _config_path(ws)
    cfg = _read_config(path)
    if not cfg["base_url"]:
        raise ApiError(400, "provider.needBaseUrl", "请先保存 Provider 的 base_url")
    if not cfg["api_key"]:
        raise ApiError(400, "provider.needApiKey", "请先保存 Provider 的 api_key")

    # 规范化：base_url 末尾去掉斜杠
    base = cfg["base_url"].rstrip("/")
    url = base + "/models"

    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % cfg["api_key"],
        "Content-Type": "application/json",
    })
    # 出网统一走 tls_http：默认严格校验证书。旧实现为绕开本机证书库损坏而**关闭**
    # 了校验，但请求上挂着 Bearer key、目标又是用户填的公网地址——key 会在未校验
    # 的连接上暴露给中间人（issue #59）。证书库损坏时现在明确拒绝并给出路指引。
    try:
        with tls_http.open_url(req, timeout=TEST_TIMEOUT,
                               purpose="Provider 连通性测试") as resp:
            status = resp.status
            raw = read_response(resp).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raise ApiError(502, "provider.connectHttpError",
                       "连接失败（HTTP %s）：%s" % (e.code, _http_hint(e.code)),
                       status=str(e.code), hint=_http_hint(e.code))
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        raise ApiError(502, "provider.connectUnreachable",
                       "无法连接 %s：%s" % (base, reason or e),
                       base=base, reason=str(reason or e))
    except (ValueError, OSError) as e:
        raise ApiError(502, "provider.connectFailed", "连接异常：%s" % e, error=str(e))

    models = data.get("data", []) if isinstance(data, dict) else []
    model_names = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")] if isinstance(models, list) else []
    shown = model_names[:MODEL_LIST_LIMIT]
    truncated = len(model_names) > MODEL_LIST_LIMIT
    return {
        "ok": True,
        "status": status,
        "modelCount": len(model_names),
        "models": shown,
        "truncated": truncated,
        # 拉不到列表**不代表不能用**（很多网关没实现 /models）：那时这里是空串，
        # 界面据此告诉用户「可以直接手填模型名」。
        "hint": ("仅显示前 %d 个模型（共 %d 个）"
                 % (MODEL_LIST_LIMIT, len(model_names)) if truncated else ""),
    }


def _http_hint(code):
    if code in (401, 403):
        return "api_key 无效或无权限，请检查控制台生成的 key"
    if code == 404:
        return "base_url 路径可能不对，OpenAI 兼容端点应为 .../v1"
    return "请检查 base_url 与 key 是否正确"
