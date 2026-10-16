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

import os

from . import job_files
from . import paths
from .limits import limit_rows
from .paths import DIR_JOBS

# 全部走领域包（2026-09-19 PR-B）：原先这里靠 `paths.py` 把 tools/ 加进 sys.path，
# 那段硬闸已删——本包现在装在哪都能用。
from jobws_core import containment, jd_score, question_bank, tracker  # noqa: E402

# `dashboard_summary`（#307 搬去 dashboard_sections，本模块 re-export）。
# **必须排在 paths / job_files 之后**：它内部经 `report` 展开的领域链在导入期
# 求值 ROOT——先导本模块（不经 server / paths，如宿主自建脚本与
# `mcp/tests/test_no_repo_required.py`）时，这一手保证注入已发生。
# job_files 内 `from . import paths`、paths 顶层即 `set_app_root`——注入的真身。
from .dashboard_sections import dashboard_summary  # noqa: E402,F401

# 列表默认精简：全字段（17 列）对宿主是噪声，verbose=True 才给全量
CORE_FIELDS = ["id", "公司", "岗位", "方向", "批次", "截止日期", "投递日期",
               "当前阶段", "下次动作", "下次动作日期", "评分"]

# 文件名与 `job_files` 同源（`resources.read_job_text` 用的就是这两个名字）
CARD_FILE = job_files.CARD_FILE
JD_FILE = job_files.JD_FILE


def _split_dir(name):
    """目录名还原 (公司, 岗位)：取**首个**下划线。与 jobs.py:68 同口径
    （公司名带下划线时还原偏左，是刻意选的可预测口径）。"""
    company, _, role = (name or "").partition("_")
    return company.strip(), role.strip()


def _slim(row, verbose=False):
    keys = tracker.FIELDS if verbose else CORE_FIELDS
    return dict((k, (row.get(k) or "").strip()) for k in keys)





def list_applications(workspace, stage=None, keyword=None, limit=20, verbose=False):
    """投递记录列表（只读）。

    stage 精确匹配「当前阶段」；keyword 对公司+岗位做子串包含（大小写不敏感）。
    排序用 `tracker.sort_key`（终态沉底 → 下次动作日期升序 → id），
    与 CLI 的 list、Web 的追踪表同一顺序。

    `05_投递追踪` / `tracker.csv` 经符号链接指向工作区外时返回 ok=false + 可读
    理由（#307）——显式拒绝，不返回空列表（那会把「读不到」误判成「没投过」）。
    """
    rows, error = paths.read_tracker_rows(workspace)
    if error:
        return {"ok": False, "errors": [error]}
    if stage:
        stage = stage.strip()
        rows = [r for r in rows if (r.get("当前阶段") or "").strip() == stage]
    if keyword:
        kw = keyword.strip().lower()
        rows = [r for r in rows
                if kw in ((r.get("公司") or "") + (r.get("岗位") or "")).lower()]
    rows = sorted(rows, key=tracker.sort_key)
    total = len(rows)
    rows = limit_rows(rows, limit)
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


def _applications_by_key(rows):
    """{dedup_key: row} 索引，照抄 jobs.py:164 的 `_applications_by_key`。

    跳过空键；同键多行是合法数据（挂了再投一次），保留**仍在流程中**的那行——
    状态要回答「这一岗现在走到哪了」，历史终态行不该盖住它。入参由调用方读好：
    读 + 归属转译在 `paths.read_tracker_rows`（#307），越界在 `list_jobs` 显式
    拒绝——不再自读（自读就不会有转译那一层）。
    """
    index = {}
    for row in rows:
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
    # 归属先判（2026-10-16 审计 P1-A）：`01_岗位池` 本身若是指向工作区外的
    # junction，`os.listdir` 一次就把**外部目录的条目名**列出来。越界按「没有
    # 岗位池」给——与目录不存在同一形态，不透露外面有东西。
    if not paths.is_in_workspace(workspace, DIR_JOBS) or not os.path.isdir(base):
        return {"workspace": workspace, "total": 0, "returned": 0, "items": []}

    # 主表先读（#307：读 + 归属转译在 `paths.read_tracker_rows`）：越界显式拒绝，
    # 不静默回退「全部未投递」——那会把读不到误判成没投过
    rows, error = paths.read_tracker_rows(workspace)
    if error:
        return {"ok": False, "errors": [error]}

    applied = _applications_by_key(rows)
    items = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if name.startswith("_") or not os.path.isdir(full):
            continue
        card = job_files.read(workspace, name)                            # 只读一次
        company, role = job_files.basic_info(card) or _split_dir(name)     # 展示名
        match_company, match_role = _split_dir(name)                      # 匹配键
        row = applied.get(tracker.dedup_key(match_company, match_role))
        items.append({
            "目录": name, "公司": company, "岗位": role,
            "状态": _apply_state(row), "阶段": (row or {}).get("当前阶段", "").strip(),
            "评分": job_files.score(card),
            "有JD原文": job_files.has_jd(workspace, name),
            "有解析卡": job_files.has_card(workspace, name),
        })

    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items
                 if kw in ((i["公司"] or "") + (i["岗位"] or "")).lower()]
    total = len(items)
    items = limit_rows(items, limit)
    return {"workspace": workspace, "total": total, "returned": len(items), "items": items}


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
    rows = limit_rows(rows, limit)
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
    rows = limit_rows(rows, limit)
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
    # 归属判定统一在 `jobws_core.containment`（2026-10-02 收编批；此前这里是自持的
    # realpath + startswith）：`01_岗位池/<名>` 可能是指向**工作区外**的符号链接 /
    # junction——拼路径时看不出来，读穿出去就晚了。判据下沉在这里，让 score_jd 与
    # 资源正文读取（resources.read_job_text）共享同一强度（原语义含「等于工作区」，
    # 对应 is_within_or_equal）。
    if not containment.is_within_or_equal(job_dir, workspace):
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

    card = job_files.read(workspace, job_id)                             # 只读一次
    basic = job_files.basic_info(card)
    company, role = basic if basic else _split_dir(job_id)
    data = {
        "ok": True,
        "workspace": workspace,
        "目录": job_id,
        "公司": company,
        "岗位": role,
        "评分": job_files.score(card),
        "有解析卡": job_files.has_card(workspace, job_id),
        "有JD原文": job_files.has_jd(workspace, job_id),
    }
    if resume_version:
        # `gap_analysis` 返回 (result, errors)——与后端同款解包（routers/jobs.py）。
        # 直接赋元组会让宿主收到 `差距: [null, [...]]`（2026-09-19 审查 MINOR 抓到）。
        # 它内部读的全部输入（JD / 简历 JSON / 词典 / 母版 / 事实库）已由 #307 在
        # `jd_gap.gap_analysis` 入口做锚点预检（`_input_anchor_errors`），越界进
        # `errors` 而不是抛给宿主。此处对卡与 JD 的预判是防御性的：卡越界时评分
        # 已为 None，差距分析没有可比对象。
        inputs = (CARD_FILE, JD_FILE)
        if all(paths.is_in_workspace(workspace, DIR_JOBS, job_id, f) for f in inputs):
            gap, gap_errors = jd_score.gap_analysis(
                workspace, os.path.join(job_dir, CARD_FILE), resume_version)
            data["差距"] = gap
            if gap_errors:
                data["差距错误"] = gap_errors
        else:
            data["差距"] = None
            data["差距错误"] = ["差距分析已跳过：解析卡或 JD 原文越出工作区"]
    return data
