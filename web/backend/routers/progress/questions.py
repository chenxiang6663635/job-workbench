# -*- coding: utf-8 -*-
"""题库：聚合视图、自建列表与导入预览。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
import tracker
import question_bank as question_store
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
    return {"items": rows, "total": len(rows), "counts": counts,
            "filters": {"domain": domain or "", "subject": subject or "",
                        "status": status or "", "keyword": (q or "").strip()}}



@router.get("/questions/preview-import")
def preview_question_import(ws: str = Depends(workspace_dir)):
    """1a 预览：解析 `<工作区>/03_面试准备/**/*.md` 成候选题目——**不落盘**。

    目录是**固定的**（1a 的口径就是这个模块），不接受查询参数：曾经把它做成
    `module_dir` 参数，而 `os.path.join` 遇绝对路径会丢掉工作区——`?module_dir=C:\\…`
    就能让服务端去扫任意目录并把正文摘要回进响应（第二轨 MAJOR-1）。固定目录后
    这条路径不成立；真有第二个目录的需求时再按 `deps.safe_join` 的纪律加。

    只返回一个一次性令牌；真正的落盘走既有的 `/api/approvals/apply`（通用端点），
    所以这里不新增写端点——写通道只有一条，更容易守住"预览不碰数据"。
    """
    errors, plan = question_store.preview_import(ws)
    if plan is None:
        # 动态值走 params（语言包按 {{module}} / {{detail}} 渲染），不在文案里写死
        # 注意：ApiError 的第三个位置参数本身就是 detail，params 里不能再叫 detail
        raise ApiError(400, "question.importFailed", "题库导入失败",
                       module=question_store.MODULE_DIR, reason="；".join(errors))
    import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("question.import", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}
