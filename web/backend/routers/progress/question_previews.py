# -*- coding: utf-8 -*-
"""题库的写路径预览：新增 / 导入 / 更新 / 错题标记 / 删除。

五个端点是一族职责——「预览差异 → 一次性令牌 → /api/approvals/apply」，
不落盘、不新增写通道。2026-09-21（批次 B-3/B-4）从 `questions.py` 拆出：
那边加完自拟新增与计数 / 原因后超了 300 行规模预算，而读端点（聚合视图 /
列表 / 抽题）与写路径预览本就分属两类。

（由 routers/progress.py 拆出；2026-09-16 重构批。经包 __init__
汇聚到 /api/progress——对外契约零变化。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from jobws_core import question_bank as question_store
from jobws_core import question_review
from jobws_core import question_delete
from apierror import ApiError
from deps import workspace_dir

router = APIRouter()


# 新增预览的查询参数名 -> CSV 中文字段名（与 update 同构：字段名即契约，全仓只在
# 此处做一次映射）。`题目` 必填由领域层校验；其余留空即未填。
_ADD_FIELD_PARAMS = (("title", "题目"), ("domain", "领域"), ("subject", "科目"),
                     ("tags", "标签"), ("difficulty", "难度"), ("answer", "答案要点"),
                     ("origin", "来源"), ("company", "关联公司"), ("role", "关联岗位"),
                     ("status", "状态"), ("note", "备注"))


@router.get("/questions/preview-add")
def preview_question_add(ws: str = Depends(workspace_dir), title: str = "",
                         domain: str = None, subject: str = None, tags: str = None,
                         difficulty: str = None, answer: str = None, origin: str = None,
                         company: str = None, role: str = None, status: str = None,
                         note: str = None):
    """1c 预览：自拟新增一道题（**不落盘**），返回令牌与将写入的字段表。

    与 1a / 1b 同构：只签发一次性令牌，落盘走既有的 `/api/approvals/apply`
    （写通道只有一条）。校验与判重在领域层 `preview_add_fields`——与 CLI `bank add`
    和 MCP `preview_add_question` 是**同一份实现**：题目没填、或已存在同名同领域的题，
    都在预览段就得到明确拒绝，不会等到落盘才炸。

    只把**给了值**的参数转成字段：空串与"没给"同义（领域层视空值为未填），
    避免把空串当成"显式清空"这类本语义不支持的意图。
    """
    provided = {"title": title, "domain": domain, "subject": subject, "tags": tags,
                "difficulty": difficulty, "answer": answer, "origin": origin,
                "company": company, "role": role, "status": status, "note": note}
    fields = dict((field, provided[param]) for param, field in _ADD_FIELD_PARAMS
                  if (provided[param] or "").strip())
    errors, plan = question_store.preview_add_fields(fields, ws)
    if plan is None:
        raise ApiError(400, "question.addFailed", "题库新增预览失败",
                       reason="；".join(errors))
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("question.add", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}


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
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("question.import", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}


# 更新预览的查询参数名 -> CSV 中文字段名。字段名即契约（CSV 表头、领域层
# `QUESTION_FIELDS`、前端类型三处同一字面量）——全仓只在此处做一次映射，不引入
# 第二套命名。`题目id` 不在表内：它是身份不是字段，只能由 `?id=` 指定、改不了。
_UPDATE_FIELD_PARAMS = (("answer", "答案要点"), ("status", "状态"),
                        ("difficulty", "难度"), ("note", "备注"), ("tags", "标签"))


@router.get("/questions/preview-update")
def preview_question_update(ws: str = Depends(workspace_dir), id: str = "",
                            answer: str = None, status: str = None,
                            difficulty: str = None, note: str = None,
                            tags: str = None):
    """1b 预览：修改一道题（**不落盘**），返回令牌与「原值 -> 新值」差异表。

    与 1a 导入同构：只签发一次性令牌，落盘走既有的 `/api/approvals/apply`
    （写通道只有一条）。可改字段是**两层白名单**——这里的五个查询参数，以及
    领域层 `preview_update_fields` 对 `QUESTION_FIELDS` 的过滤；两处都过才进载荷。

    空值等同「不改」：领域层会滤掉空串（清空字段不在本语义内），界面上如实说明。
    """
    provided = {"answer": answer, "status": status, "difficulty": difficulty,
                "note": note, "tags": tags}
    changes = dict((field, provided[param])
                   for param, field in _UPDATE_FIELD_PARAMS
                   if (provided[param] or "").strip())
    errors, plan = question_store.preview_update_fields(id, changes, ws)
    if plan is None:
        # 只回 reason，不回 id：id 可能本来就没给（「请给 --id」也是一种失败），
        # 塞进文案会渲染出空括号——具体原因已经在 errors 的句子里。
        raise ApiError(400, "question.updateFailed", "题库更新预览失败",
                       reason="；".join(errors))
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("question.update", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}


@router.get("/questions/preview-wrong")
def preview_question_wrong(ws: str = Depends(workspace_dir), id: str = "",
                           on: str = "1"):
    """预览把一道题标进 / 移出错题本（**不落盘**），返回令牌与差异表。

    复用领域层 `preview_mark_wrong`：标签重算规则只有一处——界面不该自己拼
    「错题」两个字（拼法一漂，今天标的和明天 due 出来的就不是同一批题）。
    落盘仍是既有的 `question.update` 与通用 apply 通道，不新增写操作。
    """
    want = (on or "1").strip().lower() not in ("0", "false", "no")
    errors, plan = question_review.preview_mark_wrong((id or "").strip(), want, ws)
    if plan is None:
        raise ApiError(400, "question.wrongFailed", "错题标记预览失败",
                       reason="；".join(errors))
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到
    result = approval.preview("question.update", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}


@router.get("/questions/preview-delete")
def preview_question_delete(ws: str = Depends(workspace_dir), id: str = ""):
    """删题预览：把"将删哪一行"列成差异表——**不落盘**，只签发一次性令牌。

    只做**单题**：批量撤回（按 来源 / 创建日期 等条件）留在命令行
    `jobws bank delete --origin 导入 --today`——界面上没有"选中可见的多行"这个
    前置动作，把批量删做成一次点击等于鼓励误操作。

    落盘同样走既有的 `/api/approvals/apply`：写通道只有一条，删也得先看过差异。
    领域层在落盘前会把整表快照写到**工作区之外**（删错可整份复制回来）。
    """
    errors, plan = question_delete.preview_delete_fields((id or "").strip(), None, ws)
    if plan is None:
        # 与 update 同口径：只回 reason（id 可能本来就没给，塞进文案会渲染出空括号）
        raise ApiError(400, "question.deleteFailed", "题库删除预览失败",
                       reason="；".join(errors))
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("question.delete", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}
