# -*- coding: utf-8 -*-
"""投递追踪表增删改查。

复用 tools/tracker.py 的读写与校验函数（read_rows/write_rows/check_date/
check_direction/next_id/sort_key），Web 层只做 HTTP 编排与文件锁。
写操作全部持锁——write_rows 是全量重读重写，并发会互相覆盖。

变更时间线：写操作在锁内调用 tracker.append_history 落 history.csv，
时间线的读写与停留天数计算全部由 tracker.py 提供，此处不重复实现。
"""

from __future__ import annotations

import math
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import status_parse
import tracker
from apierror import ApiError
from deps import DIR_TRACKING, workspace_dir
from filelock import file_lock
# 目录名拆分只有一处实现（jobs._split_dir）。前端「一键投递」传目录名过来，
# 由这里拆——不再让每个调用方各自镜像一份拆分规则。
from routers import jobs as jobs_router

router = APIRouter(prefix="/api/applications")

# PATCH 允许更新的字段，与 CLI 的 UPDATABLE 保持单一事实源；公司与岗位不可改
UPDATABLE = tracker.UPDATABLE

STAGES = ["待投", "已投", "笔试", "一面", "二面", "三面", "HR面", "offer", "签约"]
TERMINAL = tracker.TERMINAL_STAGES

# 排序键。default 与 CLI 的 list 一致（终态沉底、按下次动作日期升序）
SORTS = ["default", "next", "score", "stale", "health"]

# 健康度排序优先级：越靠前越该先处理；None（终态）与 ok 沉底
HEALTH_ORDER = {"urgent": 0, "overdue": 1, "stale": 2, "ok": 3}


class NewApplication(BaseModel):
    # 岗位目录名（`<公司>_<岗位>`）。**给了它就以它为准**：公司与岗位由后端拆分，
    # 客户端不必也不该自己拆——拆分口径只该有一处实现（`jobs._split_dir`）。
    # 此前前端镜像了一份 JavaScript 版，两份实现迟早会漂。
    岗位目录: str = None
    公司: str = ""
    岗位: str = ""
    方向: str
    批次: str
    来源: str = ""
    截止日期: str = ""
    投递日期: str = ""
    当前阶段: str = "待投"
    状态原因: str = ""
    下次动作: str = ""
    下次动作日期: str = ""
    简历版本: str = ""
    # 未评分留空（None → 空串）。此前默认 0 会把「还没评分」写成「0 分」——
    # 0 分是一个具体判断，不是「没有判断」，两者在追踪表里不能混为一谈。
    # 允许小数：解析卡的维度分可能带小数（如 24.5/30），落库前取整。
    评分: float = None
    备注: str = ""


class PatchApplication(BaseModel):
    当前阶段: str = None
    状态原因: str = None
    下次动作: str = None
    下次动作日期: str = None
    备注: str = None
    评分: int = None
    投递日期: str = None
    截止日期: str = None


def _find(rows, app_id):
    for row in rows:
        if (row.get("id") or "").strip() == app_id:
            return row
    return None


def _score(row):
    """评分在 CSV 里是字符串，转 int 失败按 0 处理（比让排序崩溃好）。"""
    try:
        return int(str(row.get("评分") or "").strip())
    except (TypeError, ValueError):
        return 0


def _match_keyword(row, keyword):
    if not keyword:
        return True
    k = keyword.strip().lower()
    if not k:
        return True
    for field in ("公司", "岗位", "备注"):
        if k in (row.get(field) or "").lower():
            return True
    return False


def _with_stage_days(rows, ws):
    """给每行附加 stageDays（当前阶段停留天数）与 health（健康度）。

    构造新 dict 返回，不写到行对象上——rows 会原样传回 write_rows，
    附加字段混进去虽会被 extrasaction 忽略，但让它根本不出现更安全。
    """
    entries = tracker.read_history(ws)
    out = []
    for row in rows:
        item = dict(row)
        days = tracker.stale_days(row, entries)
        item["stageDays"] = days if days is not None else ""
        # 健康度与健康度理由：给理由不给黑箱分数，前端逐条照抄展示
        item["health"] = tracker.health_score(row, entries)
        out.append(item)
    return out


def _sort_items(items, sort):
    if sort == "health":
        # 严重度优先，同级里停留久的在前（越拖越该处理）
        items.sort(key=lambda r: (
            HEALTH_ORDER.get((r.get("health") or {}).get("level"), 3),
            -(r["stageDays"] if isinstance(r.get("stageDays"), int) else -1),
            r.get("id", "")))
        return items
    if sort == "score":
        items.sort(key=lambda r: (-_score(r), r.get("id", "")))
    elif sort == "stale":
        # 无基准日（空串）排在最后
        items.sort(key=lambda r: (-(r["stageDays"] if isinstance(r["stageDays"], int) else -1),
                                  r.get("id", "")))
    elif sort == "next":
        items.sort(key=lambda r: (0 if (r.get("下次动作日期") or "").strip() else 1,
                                  (r.get("下次动作日期") or ""), r.get("id", "")))
    else:
        items.sort(key=tracker.sort_key)
    return items


def _validate_dates(app: NewApplication):
    for value, label in ((app.截止日期, "截止日期"), (app.投递日期, "投递日期"),
                         (app.下次动作日期, "下次动作日期")):
        errs = tracker.check_date(value or "", label)
        if errs:
            raise ApiError(422, "app.dateFormat", errs[0], label=label, value=value or "")
    # 评分为 None 表示「还没评分」——跳过区间校验并留空；只有真填了才要求落在 0–100
    if app.评分 is not None and not (0 <= app.评分 <= 100):
        raise ApiError(422, "app.scoreRange", "评分必须在 0–100 之间")
    if not (app.岗位目录 or "").strip() and not (app.公司.strip() and app.岗位.strip()):
        raise ApiError(
            422, "app.needDirOrCompanyRole",
            "要么给 `岗位目录`，要么同时给 `公司` 与 `岗位`（前者由后端按目录名拆分）")
    if app.当前阶段 not in STAGES + TERMINAL:
        raise ApiError(422, "app.stageInvalid",
                       "当前阶段必须是 %s 之一" % "/".join(STAGES + TERMINAL),
                       stages="/".join(STAGES + TERMINAL))
    errs = tracker.check_reason_required(app.当前阶段, app.状态原因)
    if errs:
        raise ApiError(422, "app.reasonRequired", errs[0], stage=app.当前阶段)


@router.get("")
def list_applications(
    stage: str = None,
    direction: str = None,
    batch: str = None,
    q: str = None,
    sort: str = "default",
    active: str = None,
    due_within: int = None,
    overdue: str = None,
    ws: str = Depends(workspace_dir),
):
    rows = tracker.read_rows(ws)
    if stage:
        rows = [r for r in rows if r.get("当前阶段") == stage]
    if direction:
        rows = [r for r in rows if r.get("方向") == direction]
    if batch:
        rows = [r for r in rows if r.get("批次") == batch]
    if q and q.strip():
        rows = [r for r in rows if _match_keyword(r, q)]

    # 看板下钻用的三种筛选。与 dashboard 的统计口径保持一致：
    # active = 非终态；overdue = 待投且已过截止日；due_within = 未来 N 天内到期
    if active and active.lower() in ("1", "true"):
        rows = [r for r in rows if r.get("当前阶段") not in TERMINAL]
    if overdue and overdue.lower() in ("1", "true"):
        today = date.today()
        rows = [r for r in rows
                if r.get("当前阶段") == "待投"
                and tracker.parse_iso_date(r.get("截止日期"))
                and tracker.parse_iso_date(r.get("截止日期")) < today]
    if due_within is not None and due_within >= 0:
        today = date.today()
        limit = today + timedelta(days=due_within)
        kept = []
        for r in rows:
            for field in ("下次动作日期", "截止日期"):
                when = tracker.parse_iso_date(r.get(field))
                if when and today <= when <= limit:
                    kept.append(r)
                    break
        rows = kept

    items = _with_stage_days(rows, ws)
    # 未知排序键回退默认，不报错——前端传参可能来自 URL，容错比严格更好
    items = _sort_items(items, sort if sort in SORTS else "default")
    return {"items": items, "total": len(items)}


@router.get("/{app_id}/history")
def application_history(app_id: str, limit: int = 50,
                        ws: str = Depends(workspace_dir)):
    """某条记录的变更时间线，倒序返回（最新在前）。"""
    rows = tracker.read_rows(ws)
    if _find(rows, app_id) is None:
        raise ApiError(404, "app.recordNotFound", "找不到 id 为 %s 的记录" % app_id, id=app_id)

    entries = tracker.read_history(ws, app_id=app_id)
    entries = list(reversed(entries))
    if limit and limit > 0:
        entries = entries[:limit]
    return {"id": app_id, "items": entries, "total": len(entries)}


# ---------------------------------------------------------------------------
# CSV 批量导入（第一批）：两阶段 —— preview 只读预校验，commit 才写入。
# 解析与校验全部复用 tracker 的共用函数（CLI import 子命令同一套），
# 此处只做 HTTP 编排与文件锁。提交持锁并基于锁内最新数据重校验，
# 任何冲突整批拒绝，绝不半批写入。
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    csv: str
    mode: str = "preview"  # preview | commit


@router.post("/import")
def import_applications(item: ImportRequest, ws: str = Depends(workspace_dir)):
    try:
        csv_rows, unknown = tracker.parse_import_csv(item.csv)
    except ValueError as exc:
        raise ApiError(422, "app.importParseFailed", str(exc))
    if not csv_rows:
        raise ApiError(422, "app.importNoRows", "CSV 里没有数据行")

    preview = tracker.preview_import(csv_rows, workspace=ws)
    counts = {k: len(v) for k, v in preview.items()}

    if item.mode != "commit":
        # preview：不动数据，把差异表交回前端分色展示
        return {"mode": "preview", "unknown": unknown, "counts": counts, **preview}

    if preview["error"]:
        raise ApiError(422, "app.importHasErrors",
                       "存在 %d 个错误行，修正后才能提交" % counts["error"],
                       count=counts["error"])

    lock_path = os.path.join(ws, DIR_TRACKING)
    os.makedirs(lock_path, exist_ok=True)
    lock_path = os.path.join(lock_path, "tracker.lock")

    with file_lock(lock_path):
        written = tracker.commit_import(preview, workspace=ws)
    if written < 0:
        # 预览后主表又变了（比如用户在别的标签页加过记录）：整批拒绝，重新预览
        raise ApiError(409, "app.importPreviewStale",
                       "预览后追踪表有变化，出现新的重复；请重新预览后再提交")
    return {"mode": "commit", "written": written, "skipped": counts["duplicate"]}


@router.post("")
def add_application(app: NewApplication, ws: str = Depends(workspace_dir)):
    _validate_dates(app)

    errs = tracker.check_direction(app.方向, ws)
    if errs:
        raise ApiError(422, "app.directionInvalid", errs[0], direction=app.方向)

    lock_path = os.path.join(ws, DIR_TRACKING)
    os.makedirs(lock_path, exist_ok=True)
    lock_path = os.path.join(lock_path, "tracker.lock")

    # 公司与岗位只有一处来源：给了目录名就由后端拆（与前端「一键投递」同源），
    # 否则按字面值用。**不接受「目录名和字面值都给」时两边不一致还照字面值写**，
    # 那样又会写出匹配不上的记录。
    if (app.岗位目录 or "").strip():
        company, role = jobs_router._split_dir(app.岗位目录)
        if not (company and role):
            # 面向用户的文案不写内部口径（「按首个下划线拆分」是实现细节，
            # 会被 humanizeError 原样直出到界面上）
            raise ApiError(
                422, "app.dirSplitFailed",
                "目录名 `%s` 拆不出公司与岗位，目录名须为「公司_岗位」形式" % app.岗位目录,
                dir=app.岗位目录)
    else:
        company, role = app.公司.strip(), app.岗位.strip()

    with file_lock(lock_path):
        rows = tracker.read_rows(ws)

        # canonical 去重：同公司+岗位且既有记录非终态则拒绝（409 并回传既有 id）
        dup, dup_terminal = tracker.find_duplicate(rows, company, role)
        if dup and not dup_terminal:
            raise ApiError(
                409, "app.duplicate",
                "已存在相同公司+岗位的记录 `%s`（当前阶段：%s），请勿重复录入"
                % (dup.get("id", ""), dup.get("当前阶段", "")),
                id=dup.get("id", ""), stage=dup.get("当前阶段", ""))

        row = {f: "" for f in tracker.FIELDS}
        row.update({
            "id": tracker.next_id(rows),
            "公司": company,
            "岗位": role,
            "方向": app.方向,
            "批次": app.批次,
            "来源": app.来源,
            "截止日期": app.截止日期,
            "投递日期": app.投递日期,
            "当前阶段": app.当前阶段,
            "状态原因": app.状态原因,
            "下次动作": app.下次动作,
            "下次动作日期": app.下次动作日期,
            "简历版本": app.简历版本,
            # 取整在这里做：追踪表这一列是整数，且只有一处写入点，
            # 让客户端各自取整等于把同一个规则复制到每个调用方。
            # 用 floor(x + 0.5) 而不是内置 round()：后者是**银行家舍入**，
            # round(86.5) 得 86——用户预期的是四舍五入，不是「取最近的偶数」。
            "评分": "" if app.评分 is None else str(math.floor(app.评分 + 0.5)),
            "备注": app.备注,
        })
        rows.append(row)
        tracker.write_rows(rows, ws)
        # 与 CLI 的 add 保持一致：新建也入账，作为停留天数与首次活动的基准
        tracker.append_history([{
            "id": row["id"], "字段": "创建", "原值": "",
            "新值": "%s %s（%s）" % (row["公司"], row["岗位"], row["当前阶段"]),
        }], ws)

    return {"id": row["id"], "item": row}


@router.patch("/{app_id}")
def update_application(app_id: str, patch: PatchApplication, ws: str = Depends(workspace_dir)):
    if patch.评分 is not None and not (0 <= patch.评分 <= 100):
        raise ApiError(422, "app.scoreRange", "评分必须在 0–100 之间")
    if patch.当前阶段 and patch.当前阶段 not in STAGES + TERMINAL:
        raise ApiError(422, "app.stageInvalid",
                       "当前阶段必须是 %s 之一" % "/".join(STAGES + TERMINAL),
                       stages="/".join(STAGES + TERMINAL))
    for field, label in ((patch.下次动作日期, "下次动作日期"),
                         (patch.投递日期, "投递日期"), (patch.截止日期, "截止日期")):
        if field is not None and field:
            errs = tracker.check_date(field, label)
            if errs:
                raise ApiError(422, "app.dateFormat", errs[0], label=label, value=field)

    updates = {k: v for k, v in patch.model_dump().items() if v is not None and k in UPDATABLE}
    if not updates:
        raise ApiError(422, "app.noFieldsToUpdate", "没有提供任何要更新的字段")

    lock_path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    with file_lock(lock_path):
        rows = tracker.read_rows(ws)
        target = _find(rows, app_id)
        if target is None:
            raise ApiError(404, "app.recordNotFound", "找不到 id 为 %s 的记录" % app_id,
                           id=app_id)

        # 终态不回退：原阶段已是终态时禁止改阶段（基于锁内最新阶段判定）
        new_stage = updates.get("当前阶段")
        if new_stage is not None:
            errs = tracker.check_terminal_transition(target.get("当前阶段", ""), str(new_stage))
            if errs:
                raise ApiError(422, "app.terminalLocked", errs[0],
                               stage=target.get("当前阶段", ""))

        # 终态必填原因：按更新后的最终阶段与最终原因判定
        final_stage = str(new_stage) if new_stage is not None else target.get("当前阶段", "")
        final_reason = updates.get("状态原因")
        if final_reason is None:
            final_reason = target.get("状态原因", "")
        errs = tracker.check_reason_required(final_stage, str(final_reason))
        if errs:
            raise ApiError(422, "app.reasonRequired", errs[0], stage=final_stage)

        before = dict(target)
        for k, v in updates.items():
            target[k] = str(v)
        tracker.write_rows(rows, ws)
        tracker.append_history(tracker.diff_entries(app_id, before, target), ws)

    return {"item": target}


# ---------------------------------------------------------------------------
# 投递状态建议（B11 轻量版）：原文 → 建议（只读）→ 用户逐条确认 → 写回。
#
# 判断全部在 tools/status_parse.py（纯函数、零 IO），这里只做 HTTP 编排：
#   suggest 只读、不持锁——write_rows 是原子替换（tmp + os.replace），读到的
#     要么是旧快照要么是新快照，不会读到半截；预览也本就不该跟写操作抢锁；
#   apply 才持锁，并在锁内用**最新数据重算**并发前提与单调性——前端传来的
#     判断一律不信（它可能来自几分钟前的旧快照，也可能被改过）。
# ---------------------------------------------------------------------------

class SuggestRequest(BaseModel):
    原文: str
    # 用 Optional 而不是「str = None」：pydantic v2 下后者只表示默认值是 None，
    # 但**显式传 null 仍会校验失败**——而前端把「没选记录」序列化成 null 是最
    # 自然的写法（端到端验证时就这么踩了一次，返回 422「Input should be a
    # valid string」，界面上一脸懵）。
    id: Optional[str] = None      # 未匹配到记录时由用户手动指定


class ApplySuggestionRequest(BaseModel):
    id: str
    阶段: str
    # 必填：这是乐观并发的唯一依据，**不该能被省略**。此前用 Optional，
    # 调用方不传就静默跳过校验——等于把「别照旧快照写」这道保护变成可选项。
    原阶段: str
    状态原因: Optional[str] = None
    下次动作: Optional[str] = None
    下次动作日期: Optional[str] = None
    依据: str = ""                 # 命中的原文句子，写进时间线


@router.post("/suggest-status")
def suggest_status(item: SuggestRequest, ws: str = Depends(workspace_dir)):
    """原文 → 建议。**只读**：不动追踪表、不写时间线、不碰任何文件。"""
    text = (item.原文 or "").strip()
    if not text:
        raise ApiError(422, "status.textRequired", "请先粘贴要解析的原文")
    rows = tracker.read_rows(ws)
    return status_parse.suggest(text, rows, focus_id=item.id)


@router.post("/apply-status-suggestion")
def apply_status_suggestion(item: ApplySuggestionRequest,
                            ws: str = Depends(workspace_dir)):
    """把用户确认过的一条建议写回。**只有用户点了确认才会走到这里。**

    三道服务端复核，缺一不可：

    1. 阶段枚举合法；
    2. **乐观并发**：库里的当前阶段必须与用户确认时看到的一致，否则 409 让
       用户重新解析——建议是在旧快照上算出来的，期间记录可能已被别处改动
       （另一个标签页、CLI、或一次批量导入），照着旧快照写会把别人的改动抹掉；
    3. **单调性**：用规则层 `can_override` 重算——终态不回退、拒信不把 offer 打回。
       用户若确实要任意改阶段，走表格里的 PATCH（那是手工修表的入口），
       这条端点只负责「应用建议」这一种语义。
    """
    stage = (item.阶段 or "").strip()
    if stage not in STAGES + TERMINAL:
        raise ApiError(422, "status.stageInvalid",
                       "阶段必须是 %s 之一" % "/".join(STAGES + TERMINAL),
                       stages="/".join(STAGES + TERMINAL))
    if item.下次动作日期:
        errs = tracker.check_date(item.下次动作日期, "下次动作日期")
        if errs:
            raise ApiError(422, "status.dateFormat", errs[0],
                           label="下次动作日期", value=item.下次动作日期)

    lock_path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    with file_lock(lock_path):
        rows = tracker.read_rows(ws)
        target = _find(rows, item.id)
        if target is None:
            raise ApiError(404, "app.recordNotFound", "找不到 id 为 %s 的记录" % item.id,
                           id=item.id)

        current = (target.get("当前阶段") or "").strip()
        seen = (item.原阶段 or "").strip()
        if current != seen:
            raise ApiError(
                409, "status.stale",
                "这条记录的当前阶段已变为 `%s`（你确认时是 `%s`）——请重新解析原文"
                % (current, seen),
                current=current, seen=seen)

        ok, why = status_parse.can_override(current, stage)
        if not ok:
            raise ApiError(422, "status.notAllowed", why,
                           current=current, next=stage)

        before = dict(target)
        target["当前阶段"] = stage
        for field in ("状态原因", "下次动作", "下次动作日期"):
            value = getattr(item, field)
            if value is not None:
                target[field] = value
        # 终态必填原因：按更新后的最终值判定（PATCH 同一口径）
        errs = tracker.check_reason_required(stage, target.get("状态原因", ""))
        if errs:
            raise ApiError(422, "status.reasonRequired", errs[0], stage=stage)

        tracker.write_rows(rows, ws)
        entries = tracker.diff_entries(item.id, before, target)
        if (item.依据 or "").strip():
            # 审计留痕：这条改动是根据哪句原文落下来的。没有它，半年后没人说得清
            # 「这条为什么从一面变成已挂」——那正是这个功能最该自证的地方。
            entries.append({"id": item.id, "字段": "状态来源", "原值": "",
                            "新值": "原文解析：%s" % item.依据.strip()})
        tracker.append_history(entries, ws)

    return {"item": target}
