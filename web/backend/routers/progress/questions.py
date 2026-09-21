# -*- coding: utf-8 -*-
"""题库的读端点：聚合视图、自建列表与抽题。

写路径预览（新增 / 导入 / 更新 / 错题标记 / 删除）2026-09-21 拆到
`question_previews.py`——那族职责是「预览 → 令牌 → apply」，与本模块的
只读端点分开后，各自不再逼近规模预算。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from jobws_core import tracker
from jobws_core import question_bank as question_store
from jobws_core import question_drill
from jobws_core import question_review
from apierror import ApiError
from deps import workspace_dir

router = APIRouter()




# ---------------------------------------------------------------------------
# 面试题库（第二批）：把 interviews.csv 里已经答过的问题归集成库
#
# 面试记录一旦记下就是资产，但躺在 CSV 里等于没有——面试前想「这家公司以前
# 问过我什么」却翻不出来。这里按「公司 + 岗位」把问题记录、回答要点与复盘
# 聚合出来，支持关键词检索，纯只读（无新数据文件），不做语义聚类（YAGNI）。
# ---------------------------------------------------------------------------


@router.get("/question-bank")
def question_bank(ws: str = Depends(workspace_dir), q: str = None):
    """按公司+岗位聚合被问过的问题。q 为关键词，跨问题/回答/复盘/面试官匹配。

    只收有「问题记录」的面试——没记问题的面试对题库没有贡献，
    混进来只会稀释真正可复用的内容。
    """
    rows = tracker.read_interviews(ws)
    keyword = (q or "").strip().lower()

    groups = {}
    for row in rows:
        question = (row.get("问题记录") or "").strip()
        if not question:
            continue
        item = {
            "id": (row.get("面试id") or "").strip(),
            "轮次": (row.get("轮次") or "").strip(),
            "面试时间": (row.get("面试时间") or "").strip(),
            "面试官": (row.get("面试官") or "").strip(),
            "结果": (row.get("结果") or "").strip(),
            "问题记录": question,
            "我的回答要点": (row.get("我的回答要点") or "").strip(),
            "复盘与改进": (row.get("复盘与改进") or "").strip(),
        }
        if keyword:
            haystack = " ".join([item["问题记录"], item["我的回答要点"],
                                 item["复盘与改进"], item["面试官"],
                                 item["轮次"]]).lower()
            if keyword not in haystack:
                continue
        key = ((row.get("公司") or "").strip() or "（未填公司）",
               (row.get("岗位") or "").strip())
        groups.setdefault(key, []).append(item)

    items = []
    total = 0
    for (company, role), entries in groups.items():
        # 组内按面试时间倒序：同一岗位最近一次面经在最上面
        entries.sort(key=lambda r: r["面试时间"], reverse=True)
        items.append({
            "公司": company,
            "岗位": role,
            "items": entries,
            "total": len(entries),
        })
        total += len(entries)
    # 问题多的公司排在前面——面试前最该先过它的题库
    items.sort(key=lambda g: (-g["total"], g["公司"]))
    return {"groups": items, "total": total, "keyword": (q or "").strip()}



@router.get("/questions")
def questions(ws: str = Depends(workspace_dir), domain: str = None,
              subject: str = None, status: str = None, q: str = None):
    """我的题库（`questions.csv`）：领域 / 科目 / 状态 / 关键词筛选。

    筛选走**后端过滤**（与 CLI `bank list` 同一口径 `question_bank.read_questions`）——
    不做"前端拉全量再过滤"：题库会长到几百题，全量拉会把筛选这件小事变成
    每次打开都等一次全表传输。
    """
    rows = question_store.read_questions(
        ws, domain=(domain or "").strip() or None,
        subject=(subject or "").strip() or None,
        status=(status or "").strip() or None,
        keyword=(q or "").strip() or None)
    counts = {}
    for row in rows:
        key = (row.get("状态") or "未看").strip() or "未看"
        counts[key] = counts.get(key, 0) + 1
    # 待复习标记（2026-09-21 批次 B-3）：列表行据此显示「到期」徽章——原因复用
    # due_from_rows（界面不重算"今天该看什么"，与 CLI `bank due` 同源同口径）。
    due_reasons = {}
    for row, reason in question_review.due_from_rows(rows):
        due_reasons[(row.get("题目id") or "").strip()
                    or (row.get("题目") or "").strip()] = reason
    items = []
    for row in rows:
        item = dict(row)
        reason = due_reasons.get((row.get("题目id") or "").strip()
                                 or (row.get("题目") or "").strip(), "")
        if reason:
            item["due"] = True
            item["reason"] = reason
        items.append(item)
    return {"items": items, "total": len(items), "counts": counts,
            "filters": {"domain": domain or "", "subject": subject or "",
                        "status": status or "", "keyword": (q or "").strip()}}


@router.get("/questions/drill")
def drill_questions(ws: str = Depends(workspace_dir), mode: str = "due",
                    n: int = 5, domain: str = None, subject: str = None,
                    status: str = None, q: str = None):
    """抽一轮题（**只读**：不落盘、不改动任何字段）。

    与 CLI `jobws bank drill` **同一套口径**（都走 `question_drill.pick_drill`）：
    队列 = 错题 ∪ 当日待复习，去重后按「最近复习升序、题目」排；`mode` 还支持
    `wrong`（只错题）与 `random`（全库随机）。筛选与列表接口同参数、同样由后端做。

    答案要点**照常返回**（界面要"折叠后再展开"），但抽题本身不记录任何进度——
    自评与标错题走既有的 `question.update` 两段式，不在这里新增写操作。
    """
    rows = question_store.read_questions(
        ws, domain=(domain or "").strip() or None,
        subject=(subject or "").strip() or None,
        status=(status or "").strip() or None,
        keyword=(q or "").strip() or None)
    try:
        picked = question_drill.pick_drill_with_reasons(
            rows, mode=(mode or "").strip(), n=n)
    except ValueError as exc:
        raise ApiError(400, "question.drillFailed", "题库抽题失败",
                       reason=str(exc))
    # 每行附「为什么在队列里」（B-3）：题卡直接展示，用户不用猜抽题规则
    items = []
    for row, reason in picked:
        item = dict(row)
        if reason:
            item["reason"] = reason
        items.append(item)
    # 三态计数（筛选范围内，B-4）：训练结束卡显示"练到哪了"——「会了」在涨
    counts = {}
    for row in rows:
        key = (row.get("状态") or "未看").strip() or "未看"
        counts[key] = counts.get(key, 0) + 1
    return {"items": items, "total": len(items),
            "mode": (mode or "").strip() or "due", "counts": counts,
            "filters": {"domain": domain or "", "subject": subject or "",
                        "status": status or "", "keyword": (q or "").strip()}}
