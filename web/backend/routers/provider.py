# -*- coding: utf-8 -*-
"""BYOK Provider 配置：读写 OpenAI 兼容端点的 base_url 与 key，并提供连通性测试。

配置读写 + 连通性测试（调 {base_url}/models），同时是 BYOK 的**调用入口**——
简历导入抽取与 AI 改写建议经本配置调真实 LLM（见 routers/resume.py 的
`_call_llm`）。评分判断仍由 AI CLI / 用户完成。key 只在返回时脱敏，日志不打印。

**key 的存放形态**（issue #203）：策略在 `jobws_core.credentials`——桌面版默认写
Windows 凭据管理器、配置文件只留引用串 `api_key_ref`；显式回退（环境变量
`JOBWS_CREDENTIAL_STORE=plaintext` 或凭据管理器不可用）才是明文，旧明文在下次读
配置时就地迁移（见 `_resolve`）。**「引用在手却取不到」≠「没配置」**：`read_config`
此时必须抛 409，不能静默按未配置处理（界面看着正常、调用却拿不到 key）。
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

import credential_fields
import tls_http
from apierror import ApiError
from iocaps import read_response
from atomicio import atomic_write_text
from deps import safe_join, workspace_dir
from jobws_core import credentials
import lockctx
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


def _config_path(ws):
    """Provider 配置存工作区 config/ 下。"""
    return safe_join(ws, "config", CONFIG_FILE)


def _lock_path(ws):
    """Provider 锁文件（走 lockctx）。与配置内容分离，避免 locked 锁内容文件本身在 Windows 上的问题。"""
    return lockctx.lock_path(ws, "provider")


def _read_config(path):
    """读配置；坏文件按「未配置」继续，但留一条 warning。

    逐字段容错（类型不对的回落默认值）：**缺 `model` 的旧配置按空串读**，所以本批
    不需要任何数据迁移；`api_key_ref` 同理（缺它 = 明文形态，交给 `_resolve` 迁移）。
    """
    cfg = {"base_url": "", "api_key": "", "api_key_ref": "", "model": ""}
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
    for key in ("base_url", "api_key", "api_key_ref", "model"):
        value = data.get(key)
        if isinstance(value, str):
            cfg[key] = value
    return cfg


def _mask_key(key):
    """key 脱敏。实现已收进 `redact.mask_secret`（issue #50 m2：与 IMAP 的
    `_mask_password` 逐字相同，抽公共模块）；保留私名只因为调用点读起来更贴域。"""
    return mask_secret(key)


def _resolve(cfg, ws, *, strict, persist=True, inject=True):
    """取出 cfg 里的 key（旧明文就地迁移）；`strict` 时「引用取不到」抛 409。

    返回 (cfg, outcome) 沿用既有形状（read_config / read_config_lenient 与 POST、
    /test 都按它消费）；解析与迁移落盘的接线在 `credential_fields`（与 imap 共用）。

    `persist=False` 给 POST 用：它已在同一把锁里、自己负责那唯一一次落盘——`filelock`
    不可重入，这里再取一次锁只会超时成 429。此时不传 `reload`（自己刚读完又自己写，
    没有并发窗口）。

    `inject=True` 把解析出的 key 写回 `cfg["api_key"]`——那是 `read_config` 的既有
    形状（resume / imap_facts 这些 BYOK 调用面按它取 key）。**POST 必须传 False**：
    它随后会把 cfg 落盘，"注入"就等于把明文 key 写回配置文件，正好抵消 #203
    （凭据住系统存储、文件只留引用）。
    """
    kwargs = dict(path=_config_path(ws), ws=ws, ref_key="api_key_ref",
                  legacy_key="api_key", prefix="provider", lock_name="provider",
                  reload=lambda: _read_config(_config_path(ws)))
    if strict:
        outcome = credential_fields.resolve_strict(
            cfg, error_code="provider.credentialUnavailable",
            error_message="凭据在本机凭据管理器里找不到（可能换了 Windows 账户或被系统清理），"
                          "请在设置里重新保存 API Key", **kwargs)
    else:
        outcome = credential_fields.resolve(cfg, persist=persist, **kwargs)
    if inject:
        cfg["api_key"] = outcome.secret or ""
    return cfg, outcome


def read_config(ws):
    """供其他路由读取完整 Provider 配置（BYOK 调用前）。

    返回含完整 api_key 的字典——调用方不得把 key 写进日志或响应。**引用取不到时抛
    409 `provider.credentialUnavailable`**，不静默按未配置处理。
    """
    cfg, _outcome = _resolve(_read_config(_config_path(ws)), ws, strict=True)
    return cfg


def read_config_lenient(ws):
    """读配置 + 解析 key，**不抛**（GET 用）：返回 `(cfg, outcome)`；`kind` 是存放形态，
    `secret` 为空 = 没有可用的 key（没配过，或引用取不到——后者由调用面报 409）。"""
    return _resolve(_read_config(_config_path(ws)), ws, strict=False)


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


def _public(cfg, outcome):
    """对外响应：key 脱敏 + 存放形态 + base_url 的可操作提示（GET 与 POST 共用）。"""
    return {
        "base_url": cfg["base_url"],
        "api_key": _mask_key(outcome.secret),
        "hasKey": bool(outcome.secret),
        "model": cfg["model"],
        "baseUrlHint": base_url_hint(cfg["base_url"]),
        # 形态给界面用：plaintext = key 就明文躺在配置文件里（#203）
        "storage": outcome.kind,
    }


@router.get("")
def get_provider(ws: str = Depends(workspace_dir)):
    """读当前工作区的 Provider 配置，key 脱敏（引用取不到时不报错，交给 hasKey）。"""
    cfg, outcome = read_config_lenient(ws)
    return _public(cfg, outcome)


class SaveProvider(BaseModel):
    base_url: str = ""
    api_key: str = ""  # 传完整新 key 则覆盖；传空则保留原 key
    model: str = ""    # 空串 = 清空默认模型（与 api_key「空则保留」的语义刻意不同）


@router.post("")
def save_provider(body: SaveProvider, ws: str = Depends(workspace_dir)):
    """保存 Provider 配置。api_key 传空则保留原 key（前端不来回传完整 key）。"""
    path = _config_path(ws)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    base_url = body.base_url.strip()
    # 去掉末尾 /v1 之前的部分不做规范化，由前端/用户决定；仅校验协议头
    if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ApiError(422, "provider.baseUrlInvalid",
                       "base_url 必须以 http:// 或 https:// 开头")
    new_key = (body.api_key or "").strip()

    # 用独立锁文件（provider.lock），避免锁内容文件本身
    with locked(_lock_path(ws)):
        cfg = _read_config(path)
        cfg["base_url"] = base_url
        cfg["model"] = (body.model or "").strip()
        if new_key:
            # 新 key 交给策略层（写凭据管理器，失败才留明文），按**最终**形态回报
            storage = credentials.store_secret(
                cfg, new_key, ref_key="api_key_ref", legacy_key="api_key",
                prefix="provider", store=credential_fields.store())
            outcome = credentials.ResolveOutcome(new_key, storage, False)
        else:
            # 空 key = 不改凭据：可能触发「旧明文 → 系统存储」的惰性迁移。
            # inject=False 是必须的：本块紧接着会把 cfg 落盘（见下），注入明文
            # key 等于把凭据又写回文件（#203 的验收点之一）。
            cfg, outcome = _resolve(cfg, ws, strict=False, persist=False, inject=False)

        # 原子写：并发读（GET / test / 简历导入的 LLM 调用）不会看到半截文件；
        # **锁内只写这一次**——迁移（persist=False）已就地改进 cfg，与新 key /
        # base_url / model 一起落盘，两次并发保存也不会互相覆盖（与 imap.py 同口径）。
        atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2))

    return _public(cfg, outcome)


@router.post("/test")
def test_provider(ws: str = Depends(workspace_dir)):
    """连通性测试：调 {base_url}/models 验证 key 有效。超时控制，失败给人话。"""
    path = _config_path(ws)
    cfg = _read_config(path)
    if not cfg["base_url"]:
        raise ApiError(400, "provider.needBaseUrl", "请先保存 Provider 的 base_url")
    # strict：引用在手却取不到 → 409（与 BYOK 调用面同口径，不假装 key 还在）
    cfg, outcome = _resolve(cfg, ws, strict=True)
    if outcome.secret is None:
        raise ApiError(400, "provider.needApiKey", "请先保存 Provider 的 api_key")

    # 规范化：base_url 末尾去掉斜杠
    base = cfg["base_url"].rstrip("/")
    url = base + "/models"

    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % outcome.secret,
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


@router.delete("/credential")
def clear_provider_credential(ws: str = Depends(workspace_dir)):
    """「清除即删」（#203）：key 引用与明文一并清理，系统存储条目同步删除（幂等）。"""
    cfg, kind = credential_fields.clear_credential(
        path=_config_path(ws), ws=ws, ref_key="api_key_ref",
        legacy_key="api_key", lock_name="provider", read=_read_config)
    return _public(cfg, credentials.ResolveOutcome(None, kind, False))
