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

## 已知边界（刻意不做）

- **日期与时长怎么算**（相对日、时长基准、工作日，以及各自的已知边界）下沉在
  `mail_dates`；这一层只保留**语义边界**：
- **时长表达**（N 天内 / N 小时内 / N 个工作日内）要**带指令语气或任务词**才算
  待办——「我们会在 N 个工作日内联系你」是对方的承诺，不产出；
- **链接有效期**与「任务截止」分开成两类 kind：前者是链接会失效（要你复制保存），
  后者是要你完成；「链接」与「有效」须同时出现（只写「链接：https://…」不算）；
- 「截止」只认**能落成具体日期**的句子（截止 / 请于…前 / 前完成 / 有效期至 /
  deadline / 时长表达）：光有「截止另行通知」而没有日期时不产出——没有落点价值；
- 引用分隔线只认**整行都是连字符**（`-----`）：正文里的 Markdown 分隔线后若还带
  文字，不会被误当成引用起点而截掉后文。
"""

import datetime
import re

from . import mail_dates
from .mail_ics import parse_ics
from .mail_links import find_urls, is_meeting_url
from .status_parse import match_rows, parse as parse_signals


def _fact(kind, value, label, evidence, confidence, source, target_id="", note=""):
    """候选事实的统一形状（前端只消费这个结构，不自己解析正文）。"""
    return {
        "kind": kind,              # 时间 / 截止 / 会议链接 / 阶段 / 公司岗位
        "value": value,            # 规范化取值（ISO 时间 / 规范化链接 / 阶段名 / 记录id）
        "label": label,            # 面向用户的短标题
        "evidence": evidence,      # 命中的原文片段（可追溯）
        "confidence": confidence,  # high / low（low 需人工复核后才可写入）
        "source": source,          # ics / body / ai
        "targetId": target_id,     # 命中的投递记录 id（未命中为空串）
        "note": note,              # 补充说明（重复会议、墙钟时区等；可为空）
    }


def make_fact(kind, value, label, evidence, confidence, source,
              target_id="", note=""):
    """公开的事实构造器：调用方（如 Web 层的 AI 增强）据此产出同一形状的卡片。"""
    return _fact(kind, value, label, evidence, confidence, source, target_id, note)


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
    r"-{3,}\s*(?:原始邮件|original message)|-{5,}\s*$)",
    re.IGNORECASE)

# 日期与时长解析已下沉到 `mail_dates`（2026-09-24 拆出：本文件随「截止 / 链接
# 有效期」一度涨到 380 行、超了逻辑型 300 行的规模预算）——这边只判"哪一类事实"。

# 截止语气：这类日期是**任务倒计时**（要交东西），与「到场」的面试时间语义不同，
# 所以单独成 kind=截止。写入时同时落「下次动作日期」与「下次动作」文案——
# 到点提醒读的就是这两个字段，识别到即自动覆盖（不再另建提醒链路）。
DEADLINE_RE = re.compile(
    r"(截止|请于|前完成|前提交|前上传|前答复|有效期至|有效至|deadline)",
    re.IGNORECASE)

# 任务名（长词优先）：拼成「完成在线测评」这样的动作短语写进「下次动作」。
# 不含「面试」——面试有专属链路（面试表 / .ics / 面试列表倒计时），
# 把它并进来会让「请于 X 前确认面试时间」被写成「完成面试」。
_TASK_WORDS = ("在线测评", "在线笔试", "在线编程", "性格测试", "视频面试",
               "AI 面试", "AI面试", "AI面", "测评", "笔试", "测验", "机考")

# 时长表达：N 天内 / N 小时内 / N 个工作日内。前一条负向断言把小写「9月25日」里的
# 「25日」排除掉（那不是时长）；基准是**邮件发出的那天**（见 `_duration_value`）。
_DURATION_RE = re.compile(
    r"(?<!月)(\d{1,3})\s*(?:个)?\s*(工作日|自然日|天|日|小时)\s*(?:内|以内|之内)")

# 宽松版（2026-09-25 加）：只给「链接有效期」用——「链接有效期：7天」这类**没有
# 「内」**的紧凑写法（TCL 实业 AI 面试通知真机实测：此前两头都断，用户拿不到
# 这条倒计时）。截止路径仍用严格版：「内」是挡「我们会在 3 个工作日内联系你」
# 类承诺噪音的一道门，而链接有效期有「链接 + 有效」双词门，语义已足够明确。
_DURATION_LOOSE_RE = re.compile(
    r"(?<!月)(\d{1,3})\s*(?:个)?\s*(工作日|自然日|天|日|小时)")

# 指令语气：时长只在「要你做点什么」的句子里才算你的待办——
# 「我们会在 3 个工作日内联系你」是对方的承诺，这类句子在招聘邮件里非常常见，
# 不加这道门就会变成噪音（虽然写入前有逐条确认兜底，噪音本身就是缺陷）。
_ASK_RE = re.compile(r"(请|需|务必|尽快|完成|提交|上传|答复|截止)")


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


def _deadline_label(line, link=False):
    """截止行的动作短语：命中任务名就写「完成在线测评」，否则用通用词。

    `link=True` 是「链接有效期」：它与「你要交东西」是两件事——一个要你复制保存
    链接，一个要你完成，所以同一个任务名也要在文案里区分（到点提醒直接读这句）。
    """
    task = ""
    for word in _TASK_WORDS:
        if word in line:
            task = "完成%s" % word
            break
    if link:
        return ("%s（链接即将失效）" % task) if task else "链接即将失效"
    return task or "截止事项"


def _is_link_validity(line):
    """「链接…有效」= 链接会失效（要你复制保存），与「你要交东西」分开成两类。"""
    return "链接" in line and "有效" in line


def _is_deadline_line(line):
    """这行说的是「你的待办截止」吗？

    两条来源：① 截止语气（截止 / 请于…前 / deadline）；② **带指令语气或任务词的
    时长表达**（「请在 3 天内完成」）——时长本身不构成截止语义，所以第二条同时
    把对方承诺（「我们会在 3 个工作日内联系你」）挡在外面：那种句子没有"请 /
    完成 / 提交"这类词，不该变成你的待办。
    """
    if DEADLINE_RE.search(line):
        return True
    return bool(_DURATION_RE.search(line)) and bool(
        _ASK_RE.search(line) or any(w in line for w in _TASK_WORDS))


def _time_fact_from_line(line, today, mail_date=None):
    """单行 → 时间 / 截止 / 链接有效期事实（没有日期就返回 None：没有落点价值）。

    日期部分（含基准口径：相对日按今天、**时长按邮件日期**、工作日算法）在
    `mail_dates`；这里只判"属于哪一类事实"：

    - 含「链接…有效」→ `kind="链接有效期"`（链接会失效，与「要交东西」分开）；
    - 含截止语气、或**带指令语气的时长表达** → `kind="截止"`，label 带任务名；
    - 其余 → `kind="时间"`。

    把握程度由 `mail_dates` 给（绝对日期 high、其余 low——low 必须人工核对）。
    """
    ref = today or datetime.date.today()
    value, confidence, note = mail_dates.find_absolute(line, ref)
    if not value:
        # 时长表达按语义分流（2026-09-25）：截止用严格版（「内」必需），链接有效期
        # 用宽松版（"有效期：7天"没有「内」）——此前入口条件只认截止语气，链接
        # 有效期根本没机会走到这里。
        token = None
        if _is_deadline_line(line):
            token = _DURATION_RE.search(line)
        elif _is_link_validity(line):
            token = _DURATION_LOOSE_RE.search(line)
        if token:
            value, confidence, note = mail_dates.duration_date(token, ref, mail_date)
    if not value:
        return None
    value = mail_dates.with_clock(value, line)
    if _is_link_validity(line):
        return _fact("链接有效期", value, _deadline_label(line, link=True),
                     line.strip()[:120], confidence, "body", note=note)
    if _is_deadline_line(line):
        return _fact("截止", value, _deadline_label(line),
                     line.strip()[:120], confidence, "body", note=note)
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


def _body_facts(text, today, mail_date=None):
    """正文事实（调用方已剥引用；此处只做抽取）。"""
    facts = []
    for line in text.split("\n"):
        fact = _time_fact_from_line(line, today, mail_date)
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

def extract_facts(body, ics_text="", today=None, rows=None, focus_id="",
                  mail_date=None):
    """把一封邮件（正文 + ICS）变成候选事实列表。**纯函数：不写任何东西。**

    - `ics_text` 非空时先走结构化路径（source="ics"、confidence="high"）；
    - 正文兜底：先剥离引用 / 签名，再抽时间与白名单内的会议链接，最后接
      阶段信号与记录匹配（`rows` / `focus_id` 由调用方从追踪表取）；
    - ICS 与正文的**同一取值只保留先出现的**（ICS 在前），避免卡片重复；
    - `today` 只为可测（相对日期的年份来源显式化），默认取系统当天；
    - `mail_date` 是这封邮件的发出日期（date 或字符串）：**时长表达**（「3 天内」）
      以它为基准，取不到时退回今天并在 note 里写明——基准不该是"你什么时候看的"。
    """
    text = strip_quoted(body)
    facts = _ics_facts(parse_ics(ics_text))
    facts.extend(_body_facts(text, today, mail_dates.coerce_date(mail_date)))
    facts.extend(_stage_or_record_facts(text, rows, focus_id))

    seen, deduped = set(), []
    for fact in facts:
        key = (fact["kind"], fact["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped
