# -*- coding: utf-8 -*-
"""从招聘平台原文（邮件 / 站内信 / 短信）里抽出投递状态线索，产出**建议**。

## 三条设计约束（来自 2026-09-12 的调研）

1. **两级流水线**：规则优先——确定、可解释、离线、零凭证。调研里最扎实的开源
   实现也是「正则覆盖约七成 + 模型兜底」，所以这里先把规则层做扎实，模型兜底
   留给调用方（BYOK）按需接。
2. **单调状态优先级**：只有「更强」的状态才建议覆盖；**拒信不能覆盖 offer**；
   **终态一律不回退**（用户已经拍板的事不该被一封邮件翻回去）。
3. **只产出建议，不改数据**：本模块没有任何写文件的路径。改不改由用户逐条确认，
   写回与留痕由调用方（`tracker.update` 那条链路）负责。

## 为什么是「对着既有记录匹配」而不是让模型抽公司名

调研里最容易出错的一环就是公司名：ATS 代发域是 `greenhouse.io` / `lever.co`，
正文里的公司名写法又五花八门（简称、全称、带不带「有限公司」）。对着**已经存在
于追踪表里的记录**做匹配，等于把这一环从「猜」变成「查」，误判面小得多。
"""

import datetime
import re

import tracker

# 正常流转顺序（用于单调比较）。终态不在其中——它们只进不出的。
PROGRESS_STAGES = list(tracker.STAGES)
TERMINAL_STAGES = list(tracker.TERMINAL_STAGES)

# 「负面终态」：被拒 / 放弃。它们可以被落下来，但**不得把 offer 打回**——
# 已拿到 offer 之后收到的那封「很遗憾」，多半来自另一个岗位或另一条流程；
# 用一封邮件推翻 offer 是这一层代价最大的误判（调研里点名的失败模式）。
NEGATIVE_TERMINALS = ("已挂", "已放弃")

# 「更强」的判定在 PROGRESS_STAGES 里按序比大小；终态单独处理

# --- 信号词表 -----------------------------------------------------------------
# 刻意只收**明确**的说法。宁可漏（交给人工或模型兜底），不可错把收据类邮件判成拒信：
# 「感谢您的关注」这种句子在「已收到简历」的自动回执里同样常见。
REJECT_MARKERS = (
    "不再推进", "不再继续推进", "未能通过", "没有通过", "未通过",
    "进入其他候选人", "已招到合适", "已找到合适", "很遗憾", "遗憾地通知",
    "暂不合适", "岗位已关闭", "已停止招聘", "简历未通过", "不合适这个岗位",
)
OFFER_MARKERS = ("录用", "offer", "意向书", "拟录用", "入职邀请", "薪资方案")

# 轮次判定：从强到弱，命中即止
ROUND_RULES = (
    ("三面", ("三面", "第三轮", "终面", "总监面", "总经理面")),
    ("HR面", ("hr面", "hr 面", "人力面", "hr面试", "谈薪", "薪酬", "人力")),
    ("二面", ("二面", "第二轮", "复试", "专业面", "技术面")),
    ("一面", ("一面", "初面", "第一轮", "面试邀请", "面试安排", "面试时间", "邀您参加面试")),
)

TEST_MARKERS = ("笔试", "在线测评", "测评链接", "机考", "在线编程", "coding test")
APPLIED_MARKERS = ("投递成功", "简历已收到", "已收到您的简历", "感谢您的投递",
                   "感谢投递", "申请已提交", "简历评估中", "已收到您的申请")

DATE_ISO_RE = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})")
DATE_CN_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _hits(text, markers):
    return [m for m in markers if m in text]


def parse(text):
    """从原文里抽出信号（不涉及追踪表，纯文本规则）。

    返回 {"signals": [...], "dates": [...], "ambiguous": bool}，signals 按
    「从强到弱」排列：拒信 / offer 早于面试，面试早于笔试，笔试早于「已收到简历」。
    同一条邮件里同时出现拒信与 offer 措辞时置 ambiguous 并**不给阶段建议**——
    猜错方向比不给建议更糟。
    """
    raw = text or ""
    lower = raw.lower()

    reject = _hits(raw, REJECT_MARKERS)
    offer = [m for m in OFFER_MARKERS if m.lower() in lower]

    signals = []
    if reject and offer:
        return {"signals": [], "dates": extract_dates(raw), "ambiguous": True,
                "ambiguous_reason": "同一段原文里既有拒信措辞又有 offer 措辞"}

    if reject:
        signals.append({"kind": "reject", "stage": "已挂",
                        "evidence": reject})
    if offer:
        signals.append({"kind": "offer", "stage": "offer", "evidence": offer})

    for stage, markers in ROUND_RULES:
        hit = _hits(raw, markers)
        if hit:
            signals.append({"kind": "interview", "stage": stage, "evidence": hit})
            break

    hit = _hits(raw, TEST_MARKERS)
    if hit:
        signals.append({"kind": "test", "stage": "笔试", "evidence": hit})

    hit = _hits(raw, APPLIED_MARKERS)
    if hit:
        signals.append({"kind": "applied", "stage": "已投", "evidence": hit})

    return {"signals": signals, "dates": extract_dates(raw), "ambiguous": False}


def extract_dates(text):
    """抽出原文里的日期（ISO 与「X月X日」两种写法），返回去重后的 ISO 字符串。

    只做提取不做推断：说不清是哪一年的（「X月X日」）按**当前年份**记，并在
    建议里标注需人工确认——猜年份会把「明年 3 月」写成过去。
    """
    dates = []
    for y, m, d in DATE_ISO_RE.findall(text or ""):
        dates.append("%04d-%02d-%02d" % (int(y), int(m), int(d)))
    year = datetime.date.today().year
    for m, d in DATE_CN_RE.findall(text or ""):
        dates.append("%04d-%02d-%02d" % (year, int(m), int(d)))
    return sorted(set(dates))


def match_rows(text, rows):
    """找出原文里提到的既有记录。

    公司名必须**完整出现**才算命中；岗位名也出现则记为更强命中。
    返回 [(行, 命中强度)]，强度取值 "公司+岗位" / "公司"。
    """
    hits = []
    raw = text or ""
    for row in rows or []:
        company = (row.get("公司") or "").strip()
        role = (row.get("岗位") or "").strip()
        if not company or company not in raw:
            continue
        if role and role in raw:
            hits.append((row, "公司+岗位"))
        else:
            hits.append((row, "公司"))
    return hits


def stage_rank(stage):
    """正常流转阶段的强弱序号；终态排在最后（它们不比强弱）。"""
    return PROGRESS_STAGES.index(stage) if stage in PROGRESS_STAGES else len(PROGRESS_STAGES)


def can_override(current, proposed):
    """能否用 proposed 覆盖 current。返回 (可否, 原因)。

    这是「单调优先级」的唯一实现——Web 与 CLI 都该走这里，别各写一份判断。
    """
    if current in TERMINAL_STAGES:
        return False, "当前阶段 `%s` 是终态；终态不回退，如需重投请新建记录" % current
    if proposed in TERMINAL_STAGES:
        if proposed in NEGATIVE_TERMINALS and stage_rank(current) >= stage_rank("offer"):
            return False, ("当前已是 `%s`，拒信不覆盖 offer 及以上；"
                           "请人工确认这封拒信属于哪条流程" % current)
        return True, ""
    if stage_rank(proposed) <= stage_rank(current):
        return False, "建议阶段 `%s` 不强于当前 `%s`（只有更强的状态才覆盖）" % (
            proposed, current)
    return True, ""


def suggest(text, rows, today=None):
    """把原文 + 既有记录合成建议。**纯函数：不写任何东西。**

    返回：
      {
        "signals":  [...],            # 命中的信号（含原文证据）
        "dates":    [...],            # 原文里的日期
        "matches":  [{id, 公司, 岗位, 当前阶段, 建议阶段, 可覆盖, 原因, 命中, 证据}],
        "ambiguous": bool,            # 原文自相矛盾（拒信 + offer 并存）
        "unmatched": bool,            # 没匹配到任何既有记录
        "ambiguous_match": bool,      # 匹配到多条，需人工选
        "notes":    [...],
      }
    """
    parsed = parse(text)
    notes = []
    matches = []

    top = parsed["signals"][0] if parsed["signals"] else None
    hits = match_rows(text, rows)

    if parsed.get("ambiguous"):
        notes.append(parsed["ambiguous_reason"])
    if not top:
        notes.append("没有识别出状态线索；可在确认框里手工指定阶段")
    if not hits:
        notes.append("原文里没有出现任何既有记录的公司名；请选择这条更新属于哪条记录")

    picked = hits
    ambiguous_match = len(hits) > 1
    if ambiguous_match:
        notes.append("原文提到了 %d 条既有记录，请人工选择要更新的那一条" % len(hits))

    for row, strength in picked:
        current = (row.get("当前阶段") or "").strip()
        item = {
            "id": row.get("id", ""),
            "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""),
            "当前阶段": current,
            "命中": strength,
            "证据": list(top["evidence"]) if top else [],
            "建议阶段": top["stage"] if top else "",
            "可覆盖": False,
            "原因": "",
        }
        if top:
            ok, why = can_override(current, top["stage"])
            item["可覆盖"] = ok
            item["原因"] = why
        else:
            item["原因"] = "没有可用的阶段建议"
        matches.append(item)

    if parsed["dates"]:
        notes.append("原文里的日期：%s（若用于「下次动作日期」，请确认年份）"
                     % "、".join(parsed["dates"]))

    return {
        "signals": parsed["signals"],
        "dates": parsed["dates"],
        "matches": matches,
        "ambiguous": bool(parsed.get("ambiguous")),
        "unmatched": not hits,
        "ambiguous_match": ambiguous_match,
        "notes": notes,
    }
