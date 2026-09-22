# -*- coding: utf-8 -*-
"""只读工具：把 `tools/` 与后端看板的既有口径暴露给 MCP。

三条纪律（改动时请守住）：

1. **只调纯函数，绝不调 `cmd_*`**：那些函数会 print 到 stdout，而 stdio 传输下
   stdout 就是协议通道——一行 print 就是一条畸形报文。
2. **工作区一律显式传参**：`tracker.set_workspace` 改的是模块级全局，
   并发/多宿主调用下会串味（`tracker.py:46` 的注释也这么要求）。
3. **口径照抄而不是另写一套**：漏斗、待办、逾期、静默、健康度全部对齐
   `routers/dashboard.py`；岗位池的公司/岗位与评分对齐 `routers/jobs.py`。
   两套判据迟早给出互相矛盾的结论。

所有函数返回 dict/list（不返回字符串），序列化交给 server.py ——
这样它们能脱离 MCP SDK 单测。
"""

import io
import os
import re
from datetime import date, timedelta

from . import paths
from .paths import DIR_JOBS, DIR_TRACKING

# 全部走领域包（2026-09-19 PR-B）：原先这里靠 `paths.py` 把 tools/ 加进 sys.path，
# 那段硬闸已删——本包现在装在哪都能用。
from jobws_core import jd_score, question_bank, report, tracker  # noqa: E402

# 列表默认精简：全字段（17 列）对宿主是噪声，verbose=True 才给全量
CORE_FIELDS = ["id", "公司", "岗位", "方向", "批次", "截止日期", "投递日期",
               "当前阶段", "下次动作", "下次动作日期", "评分"]

CARD_FILE = "解析卡.md"
JD_FILE = "JD原文.md"


def _read_text(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _split_dir(name):
    """目录名还原 (公司, 岗位)：取**首个**下划线。与 jobs.py:68 同口径
    （公司名带下划线时还原偏左，是刻意选的可预测口径）。"""
    company, _, role = (name or "").partition("_")
    return company.strip(), role.strip()


def _card_basic_info(card_path):
    """读解析卡「基本信息」段的公司/岗位；读不到返回 None。与 jobs.py:134 同口径。"""
    card = _read_text(card_path)
    if not card:
        return None
    seg = re.search(r"^##\s*基本信息\s*$(.*?)(?=^##\s|\Z)", card, re.M | re.S)
    if not seg:
        return None
    values = {}
    for key in ("公司", "岗位"):
        m = re.search(r"^%s\s*[:：]\s*(.*)$" % key, seg.group(1), re.M)
        values[key] = (m.group(1).strip() if m else "")
    if not values["公司"] or not values["岗位"]:
        return None
    return values["公司"], values["岗位"]


def _card_score(card_path):
    """读解析卡的总分与结论，与 jobs.py 的 `_parse_card` 同口径。

    关键一致点：**四维之和必须等于总分**才给档位（level / action）——解析卡是
    渐进填写的，填到一半时给一个算错的分档比不给更糟。总分照常返回，由
    `consistent` 标明是否自洽（后端同样处理）。
    """
    card = _read_text(card_path)
    if not card:
        return None
    fields = jd_score.parse_score_section(card)
    if not fields:
        return None
    dims, ok = [], True
    for name, maximum in jd_score.DIMENSIONS:
        num, errs = jd_score.parse_dimension(fields.get(name, ""), name, maximum)
        if errs or num is None:
            ok = False
            break
        dims.append(num)
    try:
        total = float((fields.get("总分") or "").strip())
    except (TypeError, ValueError):
        total = None
        ok = False
    level = action = None
    if ok and total is not None and abs(sum(dims) - total) < 1e-6:
        level, action = jd_score.verdict(total)
    else:
        ok = False
    return {"total": total, "level": level, "action": action, "consistent": ok}


def _slim(row, verbose=False):
    keys = tracker.FIELDS if verbose else CORE_FIELDS
    return dict((k, (row.get(k) or "").strip()) for k in keys)


def list_applications(workspace, stage=None, keyword=None, limit=20, verbose=False):
    """投递记录列表（只读）。

    stage 精确匹配「当前阶段」；keyword 对公司+岗位做子串包含（大小写不敏感）。
    排序用 `tracker.sort_key`（终态沉底 → 下次动作日期升序 → id），
    与 CLI 的 list、Web 的追踪表同一顺序。
    """
    rows = tracker.read_rows(workspace)
    if stage:
        stage = stage.strip()
        rows = [r for r in rows if (r.get("当前阶段") or "").strip() == stage]
    if keyword:
        kw = keyword.strip().lower()
        rows = [r for r in rows
                if kw in ((r.get("公司") or "") + (r.get("岗位") or "")).lower()]
    rows = sorted(rows, key=tracker.sort_key)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]
    return {
        "workspace": workspace,
        "total": total,
        "returned": len(rows),
        "items": [_slim(r, verbose) for r in rows],
    }


def _apply_state(row):
    """未投递 / 流程中 / 已终态——终态口径复用 tracker，不另立清单（jobs.py:186）。"""
    if not row:
        return "未投递"
    stage = (row.get("当前阶段") or "").strip()
    if not stage:
        return "未投递"
    return "已终态" if stage in tracker.TERMINAL_STAGES else "流程中"


def _applications_by_key(workspace):
    """{dedup_key: row} 索引，照抄 jobs.py:164 的 `_applications_by_key`。

    跳过空键；同键多行是合法数据（挂了再投一次），保留**仍在流程中**的那行——
    状态要回答「这一岗现在走到哪了」，历史终态行不该盖住它。
    """
    if not os.path.isdir(os.path.join(workspace, DIR_TRACKING)):
        return {}
    index = {}
    for row in tracker.read_rows(workspace):
        key = tracker.dedup_key(row.get("公司"), row.get("岗位"))
        if not (key[0] and key[1]):
            continue
        old = index.get(key)
        if old is not None and _apply_state(old) != "已终态" and _apply_state(row) == "已终态":
            continue
        index[key] = row
    return index


def list_jobs(workspace, keyword=None, limit=20):
    """岗位池列表（只读）：公司、岗位、评分与投递状态。

    展示名取解析卡「基本信息」，读不到回退目录名拆分；**匹配键只用目录名**——
    卡片里填的公司名常更详细（真实数据里就与追踪表不一致），拿它当键会与追踪表
    系统性失配，把已投岗位判成「未投递」（jobs.py:196-209 的明确要求）。
    """
    base = os.path.join(workspace, DIR_JOBS)
    if not os.path.isdir(base):
        return {"workspace": workspace, "total": 0, "returned": 0, "items": []}

    applied = _applications_by_key(workspace)
    items = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if name.startswith("_") or not os.path.isdir(full):
            continue
        card_path = os.path.join(full, CARD_FILE)
        company, role = _card_basic_info(card_path) or _split_dir(name)   # 展示名
        match_company, match_role = _split_dir(name)                      # 匹配键
        row = applied.get(tracker.dedup_key(match_company, match_role))
        items.append({
            "目录": name, "公司": company, "岗位": role,
            "状态": _apply_state(row), "阶段": (row or {}).get("当前阶段", "").strip(),
            "评分": _card_score(card_path),
            "有JD原文": os.path.isfile(os.path.join(full, JD_FILE)),
            "有解析卡": os.path.isfile(card_path),
        })

    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items
                 if kw in ((i["公司"] or "") + (i["岗位"] or "")).lower()]
    total = len(items)
    if limit and limit > 0:
        items = items[:limit]
    return {"workspace": workspace, "total": total, "returned": len(items), "items": items}


def dashboard_summary(workspace, today=None, stale_days=None):
    """看板摘要（只读）：漏斗、近 7 天待办、已过截止、静默提醒、待推进与转化率。

    口径全部照抄 `routers/dashboard.py:114-209` 与 `report.retrospective`：
    待办取「下次动作日期」优先于「截止日期」且只取一条；逾期只看「待投」；
    静默用 `tracker.stale_days`；健康度用 `tracker.health_score`；
    转化率用「到达过」而非当前存量（否则早期阶段被高估）。
    """
    rows = tracker.read_rows(workspace)
    history = tracker.read_history(workspace)
    # 索引一次：stale_days / health_score 逐行只收「该 id 的条目」——P 批治理，
    # 与后端 applications / dashboard 同款（此前每行各自全量遍历时间线）
    by_id = tracker.history_by_id(history)
    today = today or date.today()
    if stale_days is None:
        stale_days = tracker.STALE_DAYS
    terminal = tracker.TERMINAL_STAGES

    funnel = [{"stage": k, "count": v}
              for k, v in report.count_by(rows, "当前阶段", report.FUNNEL_ORDER)]
    by_direction = [{"key": k, "count": v} for k, v in report.count_by(rows, "方向")]
    active = sum(1 for r in rows if (r.get("当前阶段") or "").strip() not in terminal)

    limit = today + timedelta(days=7)
    upcoming = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() in terminal:
            continue
        for field, reason in (("下次动作日期", "下次动作"), ("截止日期", "截止")):
            when = tracker.parse_iso_date(row.get(field))
            if when and today <= when <= limit:
                upcoming.append({
                    "id": (row.get("id") or "").strip(),
                    "公司": (row.get("公司") or "").strip(),
                    "岗位": (row.get("岗位") or "").strip(),
                    "date": when.isoformat(), "reason": reason,
                    "说明": (row.get("下次动作") or "").strip(),
                })
                break
    upcoming.sort(key=lambda x: x["date"])

    overdue = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() != "待投":
            continue
        dl = tracker.parse_iso_date(row.get("截止日期"))
        if dl and dl < today:
            overdue.append({
                "id": (row.get("id") or "").strip(),
                "公司": (row.get("公司") or "").strip(),
                "岗位": (row.get("岗位") or "").strip(),
                "截止日期": dl.isoformat(),
            })
    overdue.sort(key=lambda x: x["截止日期"])

    stale = []
    for row in rows:
        if (row.get("当前阶段") or "").strip() in terminal:
            continue
        own = by_id.get((row.get("id") or "").strip(), [])
        days = tracker.stale_days(row, own, today)
        if days is None or days < stale_days:
            continue
        base = tracker.stage_base_date(row, own)
        stale.append({
            "id": (row.get("id") or "").strip(),
            "公司": (row.get("公司") or "").strip(),
            "岗位": (row.get("岗位") or "").strip(),
            "当前阶段": (row.get("当前阶段") or "").strip(),
            "days": days, "since": base.isoformat() if base else "",
            "说明": (row.get("下次动作") or "").strip(),
        })
    stale.sort(key=lambda x: -x["days"])

    pending = []
    for row in rows:
        own = by_id.get((row.get("id") or "").strip(), [])
        health = tracker.health_score(row, own, today)
        if health["level"] in (None, "ok"):
            continue
        pending.append({
            "id": (row.get("id") or "").strip(),
            "公司": (row.get("公司") or "").strip(),
            "岗位": (row.get("岗位") or "").strip(),
            "当前阶段": (row.get("当前阶段") or "").strip(),
            "level": health["level"], "reasons": health["reasons"],
            # hints 与 reasons 一一对应，是英文宿主拼句用的结构化形态（后端同款）
            "hints": health.get("hints", []),
        })
    pending.sort(key=lambda x: tracker.HEALTH_LEVELS.index(x["level"]))

    retro = report.retrospective(rows, history, today, workspace)

    return {
        "workspace": workspace,
        "asOf": today.isoformat(),
        "initialized": paths.workspace_profile(workspace),
        "total": len(rows),
        "active": active,
        "funnel": funnel,
        "byDirection": by_direction,
        "upcoming": upcoming,
        "overdue": overdue,
        "stale": stale,
        "pending": pending,
        "conversion": retro.get("conversion", []),
        "failure": retro.get("failure"),
        "declined": retro.get("declined"),
    }


# --- 批 4.7 主线补口：面试 / 题库 / JD 评分 -----------------------------------
#
# 与既有工具同纪律（见文件头三条）：只调纯函数、工作区显式传参、口径与 CLI 同源。

# 列表默认精简（面试 13 列 / 题目 12 列对宿主是噪声），verbose=True 才给全量
INTERVIEW_CORE = ["面试id", "关联记录", "公司", "岗位", "轮次", "面试时间",
                  "形式", "结果", "面试官"]

QUESTION_CORE = ["题目id", "题目", "领域", "科目", "标签", "难度", "状态",
                 "来源", "关联公司", "关联岗位"]


def list_interviews(workspace, app_id=None, result=None, limit=20, verbose=False):
    """面试记录列表（只读）。

    口径与 CLI 的 `track interview list` 同源：按「面试时间」倒序、空时间排最后；
    app_id 非空时只看关联该投递记录的面试；result 精确匹配「结果」。
    """
    rows = tracker.read_interviews(workspace, app_id=app_id or None)
    if result:
        wanted = result.strip()
        rows = [r for r in rows if (r.get("结果") or "").strip() == wanted]
    rows.sort(key=lambda r: (r.get("面试时间") or ""), reverse=True)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]
    fields = tracker.INTERVIEW_FIELDS if verbose else INTERVIEW_CORE
    return {
        "workspace": workspace,
        "total": total,
        "returned": len(rows),
        "items": [dict((k, (r.get(k) or "").strip()) for k in fields) for r in rows],
    }


def list_questions(workspace, domain=None, subject=None, status=None,
                   keyword=None, limit=20, verbose=False):
    """题库列表（只读）。

    筛选是**同一套口径的唯一实现**：直接走 `question_bank.read_questions`
    （CLI 的 `bank list` 与后端端点也走它），不在这里另写判据。
    """
    rows = question_bank.read_questions(
        workspace, domain=domain or None, subject=subject or None,
        status=status or None, keyword=keyword or None)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]
    fields = question_bank.QUESTION_FIELDS if verbose else QUESTION_CORE
    return {
        "workspace": workspace,
        "total": total,
        "returned": len(rows),
        "items": [dict((k, (r.get(k) or "").strip()) for k in fields) for r in rows],
    }


def _job_dir(workspace, job_id):
    """岗位目录解析：只接受**单个目录名**，越界即拒（宿主可能由模型代传参数）。

    三种越界写法都先拒：绝对路径（会被 os.path.join 当成新根）、含 `..`、
    含路径分隔符（想指到子目录/兄弟目录）。
    """
    name = (job_id or "").strip()
    # 盘符相对路径（如 `C:foo`）不触发 isabs 也不含分隔符，却会在 join 时重置根——
    # 一并拒绝；含 `:` 的合法目录名在本仓命名约定下不存在（公司_岗位）。
    if (not name or os.path.isabs(name) or ":" in name
            or "/" in name or "\\" in name):
        return None, "job_id 必须是岗位池下的单个目录名（如 云帆_后端）"
    if name in (".", ".."):
        return None, "job_id 不能是 . 或 .."
    job_dir = os.path.join(workspace, DIR_JOBS, name)
    if not os.path.isdir(job_dir):
        return None, "岗位不存在：%s" % name
    # realpath 二次校验（独立审查 NIT-5）：`01_岗位池/<名>` 可能是指向**工作区外**
    # 的符号链接 / junction——拼路径时看不出来，读穿出去就晚了。判据下沉在这里，
    # 让 score_jd 与资源正文读取（resources.read_job_text）共享同一强度，不各写一份。
    real = os.path.realpath(job_dir)
    ws_real = os.path.realpath(workspace)
    if not (real == ws_real or real.startswith(ws_real + os.sep)):
        return None, "岗位目录越出工作区：%s" % name
    return job_dir, None


def score_jd(workspace, job_id, resume_version=None):
    """读岗位的 JD 解析卡，给出评分与档位（只读）。

    job_id 是岗位池目录名。解析卡由 AI 或用户写成 Markdown，本工具只做**校验与
    解读**：四维之和必须等于总分才给档位（与 `routers/jobs.py` 同口径）——
    填到一半的卡片给一个算错的分档比不给更糟。resume_version 给了才附差距分析。
    """
    job_dir, error = _job_dir(workspace, job_id)
    if error:
        return {"ok": False, "errors": [error]}

    card_path = os.path.join(job_dir, CARD_FILE)
    basic = _card_basic_info(card_path)
    company, role = basic if basic else _split_dir(job_id)
    data = {
        "ok": True,
        "workspace": workspace,
        "目录": job_id,
        "公司": company,
        "岗位": role,
        "评分": _card_score(card_path),
        "有解析卡": os.path.isfile(card_path),
        "有JD原文": os.path.isfile(os.path.join(job_dir, JD_FILE)),
    }
    if resume_version:
        # `gap_analysis` 返回 (result, errors)——与后端同款解包（routers/jobs.py）。
        # 直接赋元组会让宿主收到 `差距: [null, [...]]`（2026-09-19 审查 MINOR 抓到）。
        gap, gap_errors = jd_score.gap_analysis(workspace, card_path, resume_version)
        data["差距"] = gap
        if gap_errors:
            data["差距错误"] = gap_errors
    return data
