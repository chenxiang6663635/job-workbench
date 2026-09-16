# -*- coding: utf-8 -*-
"""投递后的进展：面试 CRUD + ICS 导出、联系人、Offer 事实、版本谱系。

复用 tools/jobws.py track 的读写函数（read_interviews/read_contacts/
read_offers/next_*_id/append_history），Web 层只做 HTTP 编排。
写操作与主表共用 tracker.lock——面试与 offer 的 add 会向 history.csv
追加时间线，与主表写并发时必须互斥。

Offer 端点的伦理边界：只透出用户录入的已知事实，不做任何加权、
排名或推荐——多目标决策由用户自己做。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

import tracker
# 别名导入：本文件已有 `def question_bank`（"被问过"的聚合端点），同名导入会被
# 后定义的函数覆盖——写成别名，两个名字各归各位。
import question_bank as question_store
import icsutil
import mail_link
from apierror import ApiError
from deps import DIR_TRACKING, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/progress")

VALID_ROUNDS = tracker.INTERVIEW_ROUNDS
VALID_FORMS = tracker.INTERVIEW_FORMS
VALID_RESULTS = tracker.INTERVIEW_RESULTS
VALID_TALK_FORMS = tracker.TALK_FORMS
VALID_TALK_ATTEND = tracker.TALK_ATTEND
VALID_MAIL_DIRECTIONS = tracker.MAIL_DIRECTIONS
VALID_MAIL_TAGS = tracker.MAIL_TAGS


def _lock_path(ws: str) -> str:
    path = os.path.join(ws, DIR_TRACKING, "tracker.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


class NewInterview(BaseModel):
    关联记录: str = ""
    公司: str = ""
    岗位: str = ""
    轮次: str = "一面"
    面试时间: str = ""
    形式: str = ""
    链接: str = ""
    面试官: str = ""
    问题记录: str = ""
    我的回答要点: str = ""
    复盘与改进: str = ""
    结果: str = "待定"


class PatchInterview(BaseModel):
    轮次: str = None
    面试时间: str = None
    形式: str = None
    链接: str = None
    面试官: str = None
    问题记录: str = None
    我的回答要点: str = None
    复盘与改进: str = None
    结果: str = None


class NewTalk(BaseModel):
    公司: str = ""
    时间: str = ""
    形式: str = ""
    地点或链接: str = ""
    关联记录: str = ""
    是否参加: str = "待定"
    收获: str = ""
    备注: str = ""


class PatchTalk(BaseModel):
    时间: str = None
    形式: str = None
    地点或链接: str = None
    关联记录: str = None
    是否参加: str = None
    收获: str = None
    备注: str = None


def _validate_enum(轮次=None, 形式=None, 结果=None):
    """枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 轮次 is not None and 轮次 not in VALID_ROUNDS:
        raise ApiError(422, "progress.roundInvalid",
                       "轮次必须是 %s 之一" % "/".join(VALID_ROUNDS),
                       values="/".join(VALID_ROUNDS))
    if 形式 is not None and 形式 and 形式 not in VALID_FORMS:
        raise ApiError(422, "progress.formInvalid",
                       "形式必须是 %s 之一" % "/".join(VALID_FORMS),
                       values="/".join(VALID_FORMS))
    if 结果 is not None and 结果 not in VALID_RESULTS:
        raise ApiError(422, "progress.resultInvalid",
                       "结果必须是 %s 之一" % "/".join(VALID_RESULTS),
                       values="/".join(VALID_RESULTS))


def _sort_rows(rows):
    """时间倒序，空时间排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("面试时间") or ""), reverse=True)


@router.get("/interviews")
def list_interviews(
    ws: str = Depends(workspace_dir),
    app: str = None,
    result: str = None,
):
    rows = tracker.read_interviews(ws, app_id=(app or "").strip() or None)
    if result:
        rows = [r for r in rows if (r.get("结果") or "").strip() == result]
    return {"rows": _sort_rows(rows), "total": len(rows)}


@router.post("/interviews", status_code=201)
def create_interview(item: NewInterview, ws: str = Depends(workspace_dir)):
    _validate_enum(item.轮次, item.形式, item.结果)

    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()
    role = (item.岗位 or "").strip()

    with file_lock(_lock_path(ws)):
        main_rows = tracker.read_rows(ws)
        if link:
            src = next(
                (r for r in main_rows if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            # 未指定公司/岗位时从主表带出，保证列表可读
            company = company or src.get("公司", "")
            role = role or src.get("岗位", "")
        elif not company:
            raise ApiError(422, "progress.companyRequired", "未关联记录时必须提供公司")

        rows = tracker.read_interviews(ws)
        row = {field: "" for field in tracker.INTERVIEW_FIELDS}
        row["面试id"] = tracker.next_interview_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = role
        row["轮次"] = item.轮次
        row["面试时间"] = (item.面试时间 or "").strip()
        row["形式"] = item.形式
        row["链接"] = (item.链接 or "").strip()
        row["面试官"] = (item.面试官 or "").strip()
        row["问题记录"] = (item.问题记录 or "").strip()
        row["我的回答要点"] = (item.我的回答要点 or "").strip()
        row["复盘与改进"] = (item.复盘与改进 or "").strip()
        row["结果"] = item.结果

        rows.append(row)
        tracker.write_interviews(rows, ws)

        # 面试入账主表时间线：岗位推进历史要能回溯到每一次面试
        if link:
            tracker.append_history([{
                "id": link,
                "字段": "面试",
                "原值": "",
                "新值": "%s %s（%s）" % (row["轮次"], row["面试时间"] or "时间待定",
                                     row["面试id"]),
            }], ws)

    return row


@router.patch("/interviews/{interview_id}")
def update_interview(
    interview_id: str, item: PatchInterview, ws: str = Depends(workspace_dir)
):
    _validate_enum(item.轮次, item.形式, item.结果)

    updates = {k: v for k, v in item.dict().items() if v is not None}
    # 「链接」与新增路径同一口径：落盘前 strip（否则变更比较也会被空白搅乱）
    if "链接" in updates:
        updates["链接"] = (updates["链接"] or "").strip()
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_interviews(ws)
        row = tracker.find_interview(rows, interview_id)
        if row is None:
            raise ApiError(404, "progress.interviewNotFound",
                           "找不到面试 %s" % interview_id, id=interview_id)

        changed = []
        for field, value in updates.items():
            if field in tracker.INTERVIEW_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row

        tracker.write_interviews(rows, ws)

    return dict(row, _changed=changed)


@router.get("/interviews.ics")
def export_ics(ws: str = Depends(workspace_dir), app: str = None):
    """导出面试日程为 .ics（RFC 5545），可直接导入日历应用。"""
    rows = tracker.read_interviews(ws, app_id=(app or "").strip() or None)
    events = icsutil.events_from_interviews(rows)
    if not events:
        raise ApiError(404, "progress.icsEmpty",
                       "没有可导出的面试日程（面试时间均为空）")

    ics_text = icsutil.build_ics(events)
    return Response(
        content=ics_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="interviews.ics"',
        },
    )


# ---------------------------------------------------------------------------
# 宣讲会 / 招聘会（v0.4.0-A）：独立表 talks.csv，与投递记录用「关联记录」相连。
# 读写在 tracker 的 read_talks / write_talks；本层只做 HTTP 编排与枚举校验。
# 写操作与主表共用 tracker.lock——虽然不入主表时间线（宣讲会不是投递推进节点），
# 但同一把锁保证「读最新 → 校验 → 写」整段互斥，避免与主表写并发时丢更新。
# ---------------------------------------------------------------------------


def _validate_talk(形式=None, 是否参加=None):
    """宣讲会枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 形式 is not None and 形式 and 形式 not in VALID_TALK_FORMS:
        raise ApiError(422, "progress.talkFormInvalid",
                       "形式必须是 %s 之一" % "/".join(VALID_TALK_FORMS),
                       values="/".join(VALID_TALK_FORMS))
    if 是否参加 is not None and 是否参加 not in VALID_TALK_ATTEND:
        raise ApiError(422, "progress.talkAttendInvalid",
                       "是否参加必须是 %s 之一" % "/".join(VALID_TALK_ATTEND),
                       values="/".join(VALID_TALK_ATTEND))


def _sort_talks(rows):
    """时间倒序，空时间排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("时间") or ""), reverse=True)


@router.get("/talks")
def list_talks(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_talks(ws, app_id=(app or "").strip() or None)
    return {"rows": _sort_talks(rows), "total": len(rows)}


@router.post("/talks", status_code=201)
def create_talk(item: NewTalk, ws: str = Depends(workspace_dir)):
    _validate_talk(item.形式, item.是否参加)

    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            src = next(
                (r for r in main_rows if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise ApiError(404, "progress.talkLinkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            # 未指定公司时从主表带出，保证列表可读（与面试记录同一条纪律）
            company = company or src.get("公司", "")
        elif not company:
            raise ApiError(422, "progress.talkCompanyRequired",
                           "未关联记录时必须提供公司")

        rows = tracker.read_talks(ws)
        row = {field: "" for field in tracker.TALK_FIELDS}
        row["宣讲会id"] = tracker.next_talk_id(rows)
        row["公司"] = company
        row["时间"] = (item.时间 or "").strip()
        row["形式"] = item.形式
        row["地点或链接"] = (item.地点或链接 or "").strip()
        row["关联记录"] = link
        row["是否参加"] = item.是否参加
        row["收获"] = (item.收获 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_talks(rows, ws)
    return row


@router.patch("/talks/{talk_id}")
def update_talk(talk_id: str, item: PatchTalk, ws: str = Depends(workspace_dir)):
    _validate_talk(item.形式, item.是否参加)

    updates = {k: v for k, v in item.model_dump().items() if v is not None}
    # 「地点或链接」与链接列的同一口径：落盘前 strip
    if "地点或链接" in updates:
        updates["地点或链接"] = (updates["地点或链接"] or "").strip()
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_talks(ws)
        row = tracker.find_talk(rows, talk_id)
        if row is None:
            raise ApiError(404, "progress.talkNotFound",
                           "找不到宣讲会 %s" % talk_id, id=talk_id)

        # 关联记录给出时必须指向存在的投递记录（空串表示解除关联）
        if "关联记录" in updates:
            link = (updates["关联记录"] or "").strip()
            if link:
                main_rows = tracker.read_rows(ws)
                if not any((r.get("id") or "").strip() == link for r in main_rows):
                    raise ApiError(404, "progress.talkLinkNotFound",
                                   "找不到关联记录 %s" % link, id=link)
            updates["关联记录"] = link

        changed = []
        for field, value in updates.items():
            if field in tracker.TALK_FIELDS and (row.get(field, "") or "") != (value or ""):
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_talks(rows, ws)

    return dict(row, _changed=changed)


@router.get("/talks.ics")
def export_talks_ics(ws: str = Depends(workspace_dir), app: str = None):
    """导出宣讲会日程为 .ics（RFC 5545），可直接导入日历应用。"""
    rows = tracker.read_talks(ws, app_id=(app or "").strip() or None)
    events = icsutil.events_from_talks(rows)
    if not events:
        raise ApiError(404, "progress.talksIcsEmpty",
                       "没有可导出的宣讲会日程（时间均为空）")

    ics_text = icsutil.build_ics(events, calendar_name="宣讲会 / 招聘会日程")
    return Response(
        content=ics_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="talks.ics"',
        },
    )


# ---------------------------------------------------------------------------
# 邮件（批 4.5）：独立表 mails.csv，与投递记录用「关联记录」相连。
# 与 talks 同一把锁、同一条纪律：邮件只驱动「记录产生」，**不自动改阶段**。
# 「打开原邮件」链接随行附带（_openLink 计算字段）：自粘链接优先，Gmail 由
# Message-ID 构造，其余邮箱 kind=none——前端诚实降级为「打开邮箱 + 复制主题
# 搜索」提示，不显示可能失效的假链接。
# ---------------------------------------------------------------------------


def _validate_mail(方向=None, 标签=None):
    """邮件枚举字段在模型层拦住，避免脏值落进 CSV。"""
    if 方向 is not None and 方向 and 方向 not in VALID_MAIL_DIRECTIONS:
        raise ApiError(422, "progress.mailDirectionInvalid",
                       "方向必须是 %s 之一" % "/".join(VALID_MAIL_DIRECTIONS),
                       values="/".join(VALID_MAIL_DIRECTIONS))
    if 标签 is not None and 标签 and 标签 not in VALID_MAIL_TAGS:
        raise ApiError(422, "progress.mailTagInvalid",
                       "标签必须是 %s 之一" % "/".join(VALID_MAIL_TAGS),
                       values="/".join(VALID_MAIL_TAGS))


def _sort_mails(rows):
    """日期倒序，空日期排最后。与 CLI 的 list 一致。"""
    return sorted(rows, key=lambda r: (r.get("日期") or ""), reverse=True)


def _with_open_link(row):
    """随行附带「打开原邮件」链接（计算字段；前缀下划线与 _changed 同规矩）。"""
    link = mail_link.build_open_link(row.get("消息id", ""),
                                     row.get("webmail链接", ""))
    return dict(row, _openLink=link)


class NewMail(BaseModel):
    消息id: str = ""
    关联记录: str = ""
    方向: str = "收"
    主题: str = ""
    发件人: str = ""
    日期: str = ""
    webmail链接: str = ""
    标签: str = "其他"


@router.get("/mails")
def list_mails(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_mails(ws, app_id=(app or "").strip() or None)
    rows = _sort_mails(rows)
    return {"rows": [_with_open_link(r) for r in rows], "total": len(rows)}


@router.post("/mails", status_code=201)
def create_mail(item: NewMail, ws: str = Depends(workspace_dir)):
    _validate_mail(item.方向, item.标签)

    link = (item.关联记录 or "").strip()
    subject = (item.主题 or "").strip()
    message_id = tracker.normalize_message_id(item.消息id)
    if not subject:
        raise ApiError(422, "progress.mailSubjectRequired", "邮件主题必填")

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                raise ApiError(404, "progress.mailLinkNotFound",
                               "找不到关联记录 %s" % link, id=link)
        rows = tracker.read_mails(ws)
        # 同一封邮件不许导两遍：列表会长出一模一样的行，且深链指向同一封
        if message_id and any(tracker.normalize_message_id(r.get("消息id")) == message_id
                              for r in rows):
            raise ApiError(422, "progress.mailDuplicate",
                           "这封邮件（消息id %s）已记录过" % message_id,
                           id=message_id)
        row = {field: "" for field in tracker.MAIL_FIELDS}
        row["邮件id"] = tracker.next_mail_id(rows)
        row["消息id"] = message_id
        row["关联记录"] = link
        row["方向"] = item.方向
        row["主题"] = subject
        row["发件人"] = (item.发件人 or "").strip()
        row["日期"] = (item.日期 or "").strip()
        row["webmail链接"] = (item.webmail链接 or "").strip()
        row["标签"] = item.标签
        rows.append(row)
        tracker.write_mails(rows, ws)
    return _with_open_link(row)


class PatchMail(BaseModel):
    关联记录: str = None
    方向: str = None
    主题: str = None
    发件人: str = None
    日期: str = None
    webmail链接: str = None
    标签: str = None


@router.patch("/mails/{mail_id}")
def update_mail(mail_id: str, item: PatchMail, ws: str = Depends(workspace_dir)):
    _validate_mail(item.方向, item.标签)

    updates = {k: v for k, v in item.model_dump().items() if v is not None}
    for field in ("主题", "发件人", "日期", "webmail链接"):
        if field in updates:
            updates[field] = (updates[field] or "").strip()
    if "主题" in updates and not updates["主题"]:
        raise ApiError(422, "progress.mailSubjectRequired", "邮件主题必填")
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_mails(ws)
        row = tracker.find_mail(rows, mail_id)
        if row is None:
            raise ApiError(404, "progress.mailNotFound",
                           "找不到邮件 %s" % mail_id, id=mail_id)

        # 关联记录给出时必须指向存在的投递记录（空串表示解除关联）
        if "关联记录" in updates:
            link = (updates["关联记录"] or "").strip()
            if link:
                main_rows = tracker.read_rows(ws)
                if not any((r.get("id") or "").strip() == link for r in main_rows):
                    raise ApiError(404, "progress.mailLinkNotFound",
                                   "找不到关联记录 %s" % link, id=link)
            updates["关联记录"] = link

        changed = []
        for field, value in updates.items():
            if field in tracker.MAIL_FIELDS and (row.get(field, "") or "") != (value or ""):
                changed.append(field)
                row[field] = value
        if not changed:
            return _with_open_link(row)
        tracker.write_mails(rows, ws)

    return _with_open_link(dict(row, _changed=changed))


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


# ---------------------------------------------------------------------------
# 联系人
# ---------------------------------------------------------------------------

class NewContact(BaseModel):
    关联记录: str = ""
    姓名: str
    角色: str = ""
    公司: str = ""
    联系方式: str = ""
    来源: str = ""
    最近联系: str = ""
    下次跟进: str = ""
    备注: str = ""


class PatchContact(BaseModel):
    角色: str = None
    联系方式: str = None
    来源: str = None
    最近联系: str = None
    下次跟进: str = None
    备注: str = None


@router.get("/contacts")
def list_contacts(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_contacts(ws, app_id=(app or "").strip() or None)
    # 有下次跟进的置顶（最该跟进的在前），与 CLI 一致
    rows.sort(key=lambda r: ((r.get("下次跟进") or "9999-99-99"),
                             r.get("姓名", "")))
    return {"rows": rows, "total": len(rows)}


@router.post("/contacts", status_code=201)
def create_contact(item: NewContact, ws: str = Depends(workspace_dir)):
    link = (item.关联记录 or "").strip()
    if not item.姓名.strip():
        raise ApiError(422, "progress.nameRequired", "姓名必填")

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)

        rows = tracker.read_contacts(ws)
        row = {field: "" for field in tracker.CONTACT_FIELDS}
        row["联系人id"] = tracker.next_contact_id(rows)
        row["关联记录"] = link
        row["姓名"] = item.姓名.strip()
        row["角色"] = (item.角色 or "").strip()
        row["公司"] = (item.公司 or "").strip()
        row["联系方式"] = (item.联系方式 or "").strip()
        row["来源"] = (item.来源 or "").strip()
        row["最近联系"] = (item.最近联系 or "").strip()
        row["下次跟进"] = (item.下次跟进 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_contacts(rows, ws)

    return row


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: str, item: PatchContact,
                   ws: str = Depends(workspace_dir)):
    updates = {k: v for k, v in item.dict().items() if v is not None}
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_contacts(ws)
        row = tracker.find_contact(rows, contact_id)
        if row is None:
            raise ApiError(404, "progress.contactNotFound",
                           "找不到联系人 %s" % contact_id, id=contact_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.CONTACT_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_contacts(rows, ws)

    return dict(row, _changed=changed)


# ---------------------------------------------------------------------------
# Offer 事实（只并排展示，不推荐）
# ---------------------------------------------------------------------------

class NewOffer(BaseModel):
    关联记录: str = ""
    公司: str = ""
    岗位: str = ""
    薪资构成: str = ""
    月薪: str = ""
    年终: str = ""
    签字费: str = ""
    股票期权: str = ""
    工作地点: str = ""
    答复截止日: str = ""
    其他条件: str = ""
    备注: str = ""


class PatchOffer(BaseModel):
    薪资构成: str = None
    月薪: str = None
    年终: str = None
    签字费: str = None
    股票期权: str = None
    工作地点: str = None
    答复截止日: str = None
    其他条件: str = None
    备注: str = None


@router.get("/offers")
def list_offers(ws: str = Depends(workspace_dir), app: str = None):
    rows = tracker.read_offers(ws, app_id=(app or "").strip() or None)
    # 按答复截止日升序：越先要答复的越靠前。不做任何其他排序或评分
    rows.sort(key=lambda r: (r.get("答复截止日") or "9999-99-99"))
    return {"rows": rows, "total": len(rows)}


@router.post("/offers", status_code=201)
def create_offer(item: NewOffer, ws: str = Depends(workspace_dir)):
    link = (item.关联记录 or "").strip()
    company = (item.公司 or "").strip()

    with file_lock(_lock_path(ws)):
        if link:
            main_rows = tracker.read_rows(ws)
            src = next((r for r in main_rows
                        if (r.get("id") or "").strip() == link), None)
            if src is None:
                raise ApiError(404, "progress.linkNotFound",
                               "找不到关联记录 %s" % link, id=link)
            company = company or src.get("公司", "")
        elif not company:
            raise ApiError(422, "progress.companyRequired", "未关联记录时必须提供公司")

        rows = tracker.read_offers(ws)
        row = {field: "" for field in tracker.OFFER_FIELDS}
        row["offer_id"] = tracker.next_offer_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = (item.岗位 or "").strip()
        row["薪资构成"] = (item.薪资构成 or "").strip()
        row["月薪"] = (item.月薪 or "").strip()
        row["年终"] = (item.年终 or "").strip()
        row["签字费"] = (item.签字费 or "").strip()
        row["股票期权"] = (item.股票期权 or "").strip()
        row["工作地点"] = (item.工作地点 or "").strip()
        row["答复截止日"] = (item.答复截止日 or "").strip()
        row["其他条件"] = (item.其他条件 or "").strip()
        row["备注"] = (item.备注 or "").strip()
        rows.append(row)
        tracker.write_offers(rows, ws)

        # 拿到 offer 是关键里程碑，入账时间线
        if link:
            tracker.append_history([{
                "id": link,
                "字段": "offer",
                "原值": "",
                "新值": "%s（%s）" % (row["offer_id"],
                                     row["答复截止日"] or "答复截止待定"),
            }], ws)

    return row


@router.patch("/offers/{offer_id}")
def update_offer(offer_id: str, item: PatchOffer,
                 ws: str = Depends(workspace_dir)):
    updates = {k: v for k, v in item.dict().items() if v is not None}
    if not updates:
        raise ApiError(422, "progress.noFieldsToUpdate", "没有提供任何要更新的字段")

    with file_lock(_lock_path(ws)):
        rows = tracker.read_offers(ws)
        row = tracker.find_offer(rows, offer_id)
        if row is None:
            raise ApiError(404, "progress.offerNotFound",
                           "找不到 offer %s" % offer_id, id=offer_id)
        changed = []
        for field, value in updates.items():
            if field in tracker.OFFER_FIELDS and row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            return row
        tracker.write_offers(rows, ws)

    return dict(row, _changed=changed)


# ---------------------------------------------------------------------------
# 版本谱系：每个简历版本投了哪些岗位、各处于什么阶段（只读展示层）
# ---------------------------------------------------------------------------

@router.get("/lineage")
def version_lineage(ws: str = Depends(workspace_dir)):
    """按简历版本聚合投递记录：母版 → 按岗派生 → 哪版投了哪家。

    数据源就是 tracker.csv 的「简历版本」列，纯只读聚合，无新数据文件。
    """
    rows = tracker.read_rows(ws)
    groups = {}
    for row in rows:
        version = (row.get("简历版本") or "").strip() or "（未填版本）"
        groups.setdefault(version, []).append({
            "id": row.get("id", ""),
            "公司": row.get("公司", ""),
            "岗位": row.get("岗位", ""),
            "当前阶段": row.get("当前阶段", ""),
            "投递日期": row.get("投递日期", ""),
        })

    items = [
        {"version": v, "applications": apps, "total": len(apps)}
        for v, apps in sorted(groups.items())
    ]
    return {"items": items, "total": len(items)}
