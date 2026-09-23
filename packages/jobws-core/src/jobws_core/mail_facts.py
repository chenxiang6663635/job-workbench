# -*- coding: utf-8 -*-
"""邮件 → 候选事实（批 9）：纯函数、零依赖、只产出建议。

## 四条设计边界

1. **ICS 优先、正文兜底**：会议邀请的结构化字段（时间 / 会议链接）以
   `text/calendar` 部件为准（解析在 `mail_ics`）；正文正则只在前者缺位时兜底。
2. **引用与签名不参与解析**：回复邮件里被引的旧时间 / 旧链接必须剥离后再解析，
   否则「上一次面试」的时间会被当成本次线索。
3. **白名单才算会议链接**：判定集中在 `mail_links`（域名 + 路径前缀），
   不做过宽的 `https?://` 匹配。
4. **只产出建议**：本模块没有任何写文件的路径；改不改由用户逐条确认，
   写回由调用方（`apply-status-suggestion` / 邮件台账那条链路）负责。

阶段信号与记录匹配**全部复用 `status_parse`**（词表、单调优先级、子串匹配与
「短名被长名前缀吞掉」的修正都在那边），这里只把它翻译成统一的事实卡片。
"""

import datetime
import re

from .mail_ics import parse_ics
from .mail_links import find_urls, is_meeting_url
from .status_parse import DATE_CN_RE, DATE_ISO_RE, match_rows, parse as parse_signals


def _fact(kind, value, label, evidence, confidence, source, target_id="", note=""):
    """候选事实的统一形状（前端只消费这个结构，不自己解析正文）。"""
    return {
        "kind": kind,              # 时间 / 会议链接 / 阶段 / 公司岗位
        "value": value,            # 规范化取值（ISO 时间 / 规范化链接 / 阶段名 / 记录id）
        "label": label,            # 面向用户的短标题
        "evidence": evidence,      # 命中的原文片段（可追溯）
        "confidence": confidence,  # high / low（low 需人工复核后才可写入）
        "source": source,          # ics / body / ai
        "targetId": target_id,     # 命中的投递记录 id（未命中为空串）
        "note": note,              # 补充说明（重复会议、墙钟时区等；可为空）
    }


def _ics_facts(events):
    """ICS 事件 → 时间 / 会议链接事实（source=ics，把握程度高）。"""
    facts = []
    for ev in events:
        if ev["start"]:
            note = ""
            if ev["recurring"]:
                note = "重复会议：只标注首个时间（不展开 RRULE，请回原邮件确认）"
            if ev["startUtc"]:
                note = (note + "；" if note else "") + "时间为 UTC（原文未给时区）"
            facts.append(_fact("时间", ev["start"], "会议时间", ev["rawStart"],
                               "high", "ics", note=note))
        for url in ev["urls"]:
            if is_meeting_url(url):
                facts.append(_fact("会议链接", url, "会议链接",
                                   ev["summary"] or url, "high", "ics"))
    return facts


# --- 正文兜底：引用剥离 / 时间 / 链接 ---------------------------------------------

# 引用块起点：中文「在 … 写道：」、英文「On … wrote:」、被引邮件头、原始邮件分隔线
_QUOTE_START_RE = re.compile(
    r"^(?:在.{0,80}写道[:：]|on .{0,80}wrote[:：]|from[:：]|发件人[:：]|sent[:：]|发送时间[:：]|"
    r"-{3,}\s*(?:原始邮件|original message)|-{5,})",
    re.IGNORECASE)

# 「2026年9月25日」这种全量中文日期（与 status_parse 的短式「9月25日」区分）
DATE_CN_FULL_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)(?!\d)")
_REL_DAYS = (("大后天", 3), ("后天", 2), ("明天", 1), ("今天", 0))
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
NEXT_WEEKDAY_RE = re.compile(r"下\s*周\s*([一二三四五六日天])")


def strip_quoted(text):
    """剥离引用块与签名，只留本次新增正文。

    回复邮件整段引用上一封是常态：不剥离的话，「上一次面试」的时间与链接会被
    当成本次线索（这是业界公认的高频误判，见 talon / email-reply-extractor 的
    同类做法）。行级 `>` 引用先删；遇到引用头或签名分隔线（`--`）即**截断**。
    """
    out = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if line.startswith(">"):
            continue
        if _QUOTE_START_RE.match(line):
            break
        if line == "--" or line.startswith("-- "):
            break
        out.append(raw)
    return "\n".join(out).strip("\n")


def _time_fact_from_line(line, today):
    """单行 → 时间事实（没有日期就返回 None：只有钟点没有日期没有落点价值）。

    把握程度：写出年份的（ISO / 中文全量）为 high；缺年份、相对日（今天/明天/
    下周X）为 low——那种值必须人工复核后才可写入。
    """
    ref = today or datetime.date.today()
    value, confidence, note = "", "high", ""

    m = DATE_ISO_RE.search(line)
    if m:
        value = "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    else:
        m = DATE_CN_FULL_RE.search(line)
        if m:
            value = "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
        else:
            m = DATE_CN_RE.search(line)
            if m:
                mo, d = (int(x) for x in m.groups())
                value = "%04d-%02d-%02d" % (ref.year, mo, d)
                confidence = "low"
                note = "原文没有年份，按 %d 年记，请确认" % ref.year
            else:
                rel = next(((n, delta) for n, delta in _REL_DAYS if n in line), None)
                if rel:
                    day = ref + datetime.timedelta(days=rel[1])
                    value, confidence = day.isoformat(), "low"
                    note = "相对日期，按 %s 计算，请确认" % ref.isoformat()
                else:
                    m = NEXT_WEEKDAY_RE.search(line)
                    if m:
                        # 下周一 = 下一个自然周的周一（今天所在周为「本周」）
                        day = ref + datetime.timedelta(
                            days=7 - ref.weekday() + _WEEKDAYS[m.group(1)])
                        value, confidence = day.isoformat(), "low"
                        note = "相对日期，按 %s 计算，请确认" % ref.isoformat()

    if not value:
        return None
    t = TIME_RE.search(line)
    if t:
        value += " %02d:%02d" % (int(t.group(1)), int(t.group(2)))
    return _fact("时间", value, "时间", line.strip()[:120], confidence, "body", note=note)


def _body_link_facts(text):
    """按行找白名单内的会议链接（同一行多个链接都收，出处即该行）。"""
    facts = []
    for line in (text or "").split("\n"):
        for url in find_urls(line):
            if is_meeting_url(url):
                facts.append(_fact("会议链接", url, "会议链接",
                                   line.strip()[:120], "high", "body"))
    return facts


def _body_facts(text, today):
    """正文事实（调用方已剥引用；此处只做抽取）。"""
    facts = []
    for line in text.split("\n"):
        fact = _time_fact_from_line(line, today)
        if fact:
            facts.append(fact)
    facts.extend(_body_link_facts(text))
    return facts


# --- 阶段与记录匹配 ---------------------------------------------------------------

def _stage_or_record_facts(text, rows, focus_id):
    """阶段信号 + 命中的投递记录（口径全部复用 status_parse，不另造一套）。"""
    parsed = parse_signals(text)
    top = parsed["signals"][0] if parsed["signals"] else None

    if focus_id:
        target = next((r for r in (rows or [])
                       if (r.get("id") or "").strip() == (focus_id or "").strip()), None)
        hits = [(target, "手动指定")] if target is not None else []
    else:
        hits = match_rows(text, rows or [])

    target_id = (hits[0][0].get("id") or "") if hits else ""
    facts = []
    if top:
        facts.append(_fact("阶段", top["stage"], "建议阶段", "、".join(top["evidence"]),
                           "high", "body", target_id=target_id))
    for row, strength in hits:
        facts.append(_fact("公司岗位", row.get("id", ""),
                           "%s · %s" % (row.get("公司", ""), row.get("岗位", "")),
                           row.get("公司", ""), "high", "body",
                           target_id=row.get("id", ""), note=strength))
    return facts


# --- 入口 ---------------------------------------------------------------------

def extract_facts(body, ics_text="", today=None, rows=None, focus_id=""):
    """把一封邮件（正文 + ICS）变成候选事实列表。**纯函数：不写任何东西。**

    - `ics_text` 非空时先走结构化路径（source="ics"、confidence="high"）；
    - 正文兜底：先剥离引用 / 签名，再抽时间与白名单内的会议链接，最后接
      阶段信号与记录匹配（`rows` / `focus_id` 由调用方从追踪表取）；
    - ICS 与正文的**同一取值只保留先出现的**（ICS 在前），避免卡片重复；
    - `today` 只为可测（相对日期的年份来源显式化），默认取系统当天。
    """
    text = strip_quoted(body)
    facts = _ics_facts(parse_ics(ics_text))
    facts.extend(_body_facts(text, today))
    facts.extend(_stage_or_record_facts(text, rows, focus_id))

    seen, deduped = set(), []
    for fact in facts:
        key = (fact["kind"], fact["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped
