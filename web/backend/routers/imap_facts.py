# -*- coding: utf-8 -*-
"""邮件 → 候选事实（批 9）：只读解析端点。

**为什么单独成文件**：`routers/imap.py` 的水位线只许降（约 300 行的规模闸门），
这里与 `application_delete.py` 同款处置——新能力单开一个 router，同级前缀、
同组边界。

四条边界（与 `routers/imap.py` 逐条一致）：

1. **只读**：把已拉到手的正文 / ICS 解释成候选事实就结束——不持锁、不落盘；
2. **无后台路径**：没有定时器、轮询或保活；每次调用都是一次纯计算；
3. **写回不在这里**：邮件台账走 `POST /api/progress/mails`，阶段更新走
   `POST /api/applications/apply-status-suggestion`（都由用户逐条确认触发）；
4. **同义不新造错误码**：空输入复用 `status.textRequired`。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import tls_http
from apierror import ApiError
from deps import workspace_dir
from jobws_core import mail_facts, status_parse, tracker
from jobws_core.mail_text import MAX_BODY_CHARS

router = APIRouter(prefix="/api/imap")


class SuggestFacts(BaseModel):
    """正文与 ICS 都可选：有的邮件只有正文，有的只有日历邀请。

    `id` 用 Optional 而不是「str = None」：前端把「没选记录」序列化成 null 是
    最自然的写法，显式传 null 不该 422（与阶段 2 的 SuggestRequest 同款坑）。
    """
    原文: str = ""
    ics: str = ""
    id: Optional[str] = None


@router.post("/suggest-facts")
def suggest_facts(item: SuggestFacts, ws: str = Depends(workspace_dir)):
    """正文 / ICS → 候选事实（时间 / 会议链接 / 阶段 / 对应记录）。**只读。**

    追踪表只读一次用于记录匹配（`focus_id` 非空时按用户点选的那条，比子串匹配
    权威）；返回事实列表，写入与否由用户在界面逐条确认。
    """
    text = (item.原文 or "").strip()
    ics = (item.ics or "").strip()
    if not text and not ics:
        # 复用既有的同义 code（前端语言包已覆盖，避免同义两个码漂移）
        raise ApiError(422, "status.textRequired", "请先选择一封邮件或粘贴要解析的原文")

    rows = tracker.read_rows(ws)
    facts = mail_facts.extract_facts(text, ics_text=ics, rows=rows,
                                     focus_id=(item.id or "").strip())
    return {"facts": facts, "total": len(facts)}


# ---------------------------------------------------------------------------
# 可选 AI 增强（BYOK）：同样只产建议，**绝不写入**。
#
# 三条纪律：
#   1. 未配置 Provider 就不给入口（前端按 /api/provider 的 hasKey 渲染）；
#   2. AI 产出**一律 low 把握**——界面强制用户核对后才允许写入；
#   3. 白名单过滤：非三类 kind、空值、非法阶段名一律丢弃（宁可少给，不可错给）。
# ---------------------------------------------------------------------------

AI_TIMEOUT = 90
AI_MAX_FACTS = 8
# AI 只补「需要理解正文」的三类：记录匹配交回领域层的子串匹配（AI 猜公司名不可靠）
_AI_KINDS = ("时间", "会议链接", "阶段")
_AI_LABELS = {"时间": "时间", "会议链接": "会议链接", "阶段": "建议阶段"}

_AI_PROMPT = """你是招聘邮件解析助手。只依据下面的邮件内容抽取候选事实，输出 JSON：

{"facts": [{"kind": "时间|会议链接|阶段", "value": "...", "evidence": "命中的原文片段"}]}

规则：
- 时间：写成 YYYY-MM-DD 或 YYYY-MM-DD HH:MM；不确定就不输出；
- 会议链接：必须是原文里出现过的完整 URL（腾讯会议 / Zoom / Teams / Meet 等）；
- 阶段：只能取这些值之一：%s；
- 只输出 JSON，不要解释；最多 %d 条；
- **不要编造**：原文没有的宁可少给，也不要猜。

## 邮件正文
%s

## 日历（ICS，可能为空）
%s
"""


class SuggestFactsAi(BaseModel):
    原文: str = ""
    ics: str = ""
    model: str = ""


def _extract_json_object(content):
    """从模型回复里抠出 JSON 对象（兼容 ```json 包裹与前后废话）。"""
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("回复中没有 JSON 对象")
    return json.loads(text[start:end + 1])


def _call_model(cfg, prompt, model):
    """调 OpenAI 兼容 /chat/completions（标准库；出网走 tls_http 的严格校验）。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # 抽取不是创作：低温度更稳
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
    })
    with tls_http.open_url(req, timeout=AI_TIMEOUT, purpose="邮件事实 AI 增强") as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data["choices"][0]["message"]["content"]


def _valid_stages():
    return set(tracker.STAGES) | set(tracker.TERMINAL_STAGES)


def _parse_ai_facts(content):
    """模型回复 → 事实列表：白名单过滤 + 一律 low 把握 + 条数上限。"""
    obj = _extract_json_object(content)
    stages = _valid_stages()
    facts = []
    for item in (obj.get("facts") or []):
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "").strip()
        value = (item.get("value") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        if kind not in _AI_KINDS or not value:
            continue
        if kind == "阶段" and value not in stages:
            continue
        if kind == "会议链接" and not mail_facts.is_meeting_url(value):
            # 模型可能给出任意 URL（甚至 javascript:）——只放行白名单内的会议入口
            continue
        facts.append(mail_facts.make_fact(kind, value, _AI_LABELS[kind],
                                          evidence[:120], "low", "ai"))
        if len(facts) >= AI_MAX_FACTS:
            break
    return facts


@router.post("/suggest-facts-ai")
def suggest_facts_ai(item: SuggestFactsAi, ws: str = Depends(workspace_dir)):
    """AI 增强（可选，BYOK）：**只产建议、绝不写入**。

    与规则路径同一套输出形状（source="ai"、confidence="low"）；记录匹配仍旧由
    领域层的子串匹配给出（AI 不猜公司名）——文本里恰好命中一条记录时带上 targetId。
    """
    from routers import provider  # 延迟导入：与简历侧同一手法，避免路由层互相牵连

    # 上限与拉取侧同一条口径：这里是可独立调用的公开接口，不能收任意长文本
    text = (item.原文 or "").strip()[:MAX_BODY_CHARS]
    ics = (item.ics or "").strip()[:MAX_BODY_CHARS]
    if not text and not ics:
        raise ApiError(422, "status.textRequired", "请先选择一封邮件或粘贴要解析的原文")

    model = (item.model or "").strip()
    if not model:
        raise ApiError(422, "resume.modelRequired", "请填写模型名（如 deepseek-chat）")

    cfg = provider.read_config(ws)
    if not cfg.get("base_url") or not cfg.get("api_key"):
        raise ApiError(400, "resume.providerMissing",
                       "先在「设置」配置 Provider（BYOK）：base_url 与 api_key")

    prompt = _AI_PROMPT % ("/".join(sorted(_valid_stages())), AI_MAX_FACTS, text, ics)
    try:
        content = _call_model(cfg, prompt, model)
        facts = _parse_ai_facts(content)
    except urllib.error.HTTPError as exc:
        # 同码同参：`resume.modelHttpError` 在简历侧已有两处调用点（都带截断后的 body），
        # 少传一个参数会被 `test_error_code_params` 判为同码分叉——这里保持同款、截断 200。
        # （批末独立审查提过「4xx 响应体可能回显请求片段」：属全局取舍，留待统一决策。）
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise ApiError(502, "resume.modelHttpError",
                       "模型端点返回 %s：%s" % (exc.code, body),
                       status=str(exc.code), body=body)
    except urllib.error.URLError as exc:
        raise ApiError(502, "resume.modelUnreachable",
                       "连不上模型端点：%s" % exc.reason, reason=str(exc.reason))
    except (ValueError, KeyError, OSError) as exc:
        raise ApiError(502, "resume.modelCallFailed",
                       "模型调用失败：%s" % exc, error=str(exc))

    # 记录匹配用**剥离引用后的正文**（与规则路径同一口径）：回复邮件引用的上一封
    # 里的公司名不该把建议指到另一家。恰好命中一条才带 targetId，多命中留空交用户选。
    rows = tracker.read_rows(ws)
    hits = status_parse.match_rows(mail_facts.strip_quoted(text), rows)
    target_id = (hits[0][0].get("id") or "") if len(hits) == 1 else ""
    for fact in facts:
        fact["targetId"] = target_id
    return {"facts": facts, "total": len(facts), "model": model}
