# -*- coding: utf-8 -*-
"""岗位池：列表、新建、详情。

岗位目录结构（与 CLI 的 jd 工作流一致）：
    01_岗位池/<公司>_<岗位>/
    ├── JD原文.md
    └── 解析卡.md

解析卡的评分小节由 tools/jd_score.py 的解析函数读取——评分由 AI CLI
完成写入，Web 只做查看与展示，不做评分决策。
"""

from __future__ import annotations

import io
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import atomicio
import jd_score
import tracker
from deps import DIR_JOBS, DIR_TRACKING, safe_join, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/jobs")

JD_FILE = "JD原文.md"
CARD_FILE = "解析卡.md"
INVALID_DIR_CHARS = set('\\/:*?"<>|')

# 四排序。未知键静默回退——前端传参可能来自 URL，容错比严格更好
# （与 applications.py 的 SORTS 同一策略，避免两页同一类控件的容忍度不一致）
JOB_SORTS = ["dir", "score", "state", "recent"]
# 每个维度的自然方向：目录名 A→Z、状态「未投递在前」是 asc；评分高分在前、
# 最近更新新在前是 desc。前端切换维度时回到该维度的默认，请求缺 order 时后端照它兜底。
JOB_DEFAULT_ORDER = {"dir": "asc", "score": "desc", "state": "asc", "recent": "desc"}
JOB_ORDERS = ("asc", "desc")
# 状态筛选白名单：未知值视为「全部」，同样静默容错
JOB_STATUS = {"unapplied": "未投递", "active": "流程中", "terminal": "已终态"}

# JD 抓取（第三批）：正文短于此字数视为没抓到（多为需登录或纯 JS 渲染），
# 明确降级让用户手动粘贴——绝不假装成功把空壳存进 JD原文.md
JD_MIN_CHARS = 80
FETCH_TIMEOUT = 15
FETCH_MAX_BYTES = 3 * 1024 * 1024


def _dir_name(company: str, role: str) -> str:
    name = ("%s_%s" % (company.strip(), role.strip())).strip()
    bad = [c for c in name if c in INVALID_DIR_CHARS or ord(c) < 32]
    if bad:
        raise HTTPException(status_code=422,
                            detail="公司或岗位名含非法字符: %s" % "".join(sorted(set(bad))))
    if not name or name.strip(". ") in ("", ".", ".."):
        raise HTTPException(status_code=422, detail="目录名不能为空或纯点号")
    return name


def _split_dir(name: str):
    """反向还原目录名里的 (公司, 岗位)，与 `_dir_name` 互为逆运算。

    取**首个**下划线切分。公司名自带下划线时会还原偏左——这是刻意选的可预测口径：
    宁可显示「未投递」让用户补一张解析卡，也不要自作聪明地猜哪一刀是公司的边界。
    """
    company, _, role = (name or "").partition("_")
    return company.strip(), role.strip()


def _read(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_card(workspace: str, job_dir: str):
    """解析解析卡的评分小节、硬门槛与分维度明细。

    缺失或格式错误时返回空结构而非报错——卡片是渐进填写的。返回结构：
    - dimensions/total/level/action/consistent：四维加权评分（原有）
    - hardGates：资格硬门槛（前置差异化），含 items/conclusion/reason/details
    - dimensionsDetail：每维的词典命中（含证据标签）与逐条说明 raw
    """
    card = _read(safe_join(workspace, job_dir, CARD_FILE))
    if card is None:
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
        dims.append({"name": name, "score": num, "max": maximum})

    total_raw = fields.get("总分", "")
    try:
        total = float(total_raw)
    except (TypeError, ValueError):
        ok = False
        total = None

    level = action = None
    if ok and total is not None and abs(sum(d["score"] for d in dims) - total) < 1e-6:
        level, action = jd_score.verdict(total)
        ok = True
    else:
        ok = False

    hard_gates = jd_score.parse_hard_gates(card)
    dim_names = [n for n, _ in jd_score.DIMENSIONS]
    dim_detail = jd_score.parse_dimension_detail(card, dim_names)

    return {
        "dimensions": dims, "total": total, "level": level,
        "action": action, "consistent": ok,
        "hardGates": hard_gates,
        "dimensionsDetail": dim_detail,
    }


def _card_basic_info(workspace: str, job_dir: str):
    """读解析卡「基本信息」段的公司/岗位；没填、缺文件或缺该段时返回 None。

    解析卡是渐进填写的（可能只写到硬门槛就停了），所以「读不到」是常态而非异常。
    """
    card = _read(safe_join(workspace, job_dir, CARD_FILE))
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


def _job_company_role(workspace: str, name: str):
    """(公司, 岗位) 的**展示名**：解析卡「基本信息」优先，读不到回退目录名拆分。

    只用于展示。关联键一律用目录名（见 `_link_fields`）——卡片里填的常是
    给人看的详细描述（如「奥克斯集团（空调事业部＝…）」），当键会与追踪表系统性失配。
    """
    return (_card_basic_info(workspace, os.path.join(DIR_JOBS, name))
            or _split_dir(name))


def _applications_by_key(ws: str):
    """{dedup_key: row} 索引，供岗位池按 (公司, 岗位) 查出投递状态。

    一次性建索引：对每个岗位各查一次会退化成 O(n²)。追踪表还不存在时
    （工作区刚初始化）返回空字典，此时所有岗位一律「未投递」。
    """
    if not os.path.isdir(os.path.join(ws, DIR_TRACKING)):
        return {}
    index = {}
    for row in tracker.read_rows(ws):
        key = tracker.dedup_key(row.get("公司"), row.get("岗位"))
        if not (key[0] and key[1]):
            continue
        old = index.get(key)
        # 同键多行是合法数据（挂了再投一次）：保留仍在流程中的那行——
        # 状态展示要回答「这一岗现在走到哪了」，历史终态行不该盖住它
        if old is not None and _apply_state(old) != "已终态" and _apply_state(row) == "已终态":
            continue
        index[key] = row
    return index


def _apply_state(row) -> str:
    """未投递 / 流程中 / 已终态——终态口径直接复用 tracker，不另立清单。"""
    if not row:
        return "未投递"
    stage = (row.get("当前阶段") or "").strip()
    if not stage:
        return "未投递"
    return "已终态" if stage in tracker.TERMINAL_STAGES else "流程中"


def _link_fields(workspace: str, name: str, app_index: dict = None):
    """岗位与追踪表记录的关联字段——列表与详情共用，保证两处口径一致。

    **匹配键只取目录名拆分**（`_split_dir`）：追踪表里的 (公司, 岗位) 是按
    目录名口径录的，两边同源才匹配得上；解析卡「基本信息」里的名值往往更
    详细（真实数据里就与追踪表不一致），拿它当键会系统性失配。

    没有记录时后三个字段全为空，前端据此显示「未投递」。
    """
    company, role = _job_company_role(workspace, name)   # 展示名：卡片优先
    match_company, match_role = _split_dir(name)         # 匹配键：目录名口径
    if app_index is None:
        app_index = _applications_by_key(workspace)
    row = app_index.get(tracker.dedup_key(match_company, match_role))
    return {
        "company": company,
        "role": role,
        "applyState": _apply_state(row),
        "stage": (row or {}).get("当前阶段") or None,
        "applicationId": (row or {}).get("id") or None,
    }


def _summary(workspace: str, name: str, app_index: dict = None):
    """单个岗位的列表条目。

    列表端点一次建好索引整批传入（`_applications_by_key`）；单条调用
    （新建、抓取 JD）不传时就地建一次——避免调用方忘传后静默滑成「未投递」。
    """
    d = safe_join(workspace, DIR_JOBS, name)
    # 与 job_detail 调用方式相同，传带 DIR_JOBS 前缀的相对路径
    card = _parse_card(workspace, os.path.join(DIR_JOBS, name))
    # 以解析成功为基准，而非文件存在——存在但不通过的卡片不算"已评分"
    has_card = card is not None and card.get("consistent") and card.get("total") is not None
    return dict({
        "dir": name,
        "hasJD": _read(os.path.join(d, JD_FILE)) is not None,
        "hasCard": has_card,
        "score": card["total"] if has_card else None,
        "level": card["level"] if card else None,
        "mtime": int(os.path.getmtime(d)) if os.path.isdir(d) else None,
    }, **_link_fields(workspace, name, app_index))


class NewJob(BaseModel):
    公司: str
    岗位: str
    JD文本: str


def _sort_jobs(items, sort: str, order: str = None):
    """四排序 × 方向。

    三条口径**不随方向反转**（跟着翻只会误导）：

    - **未评分 / 没有更新时间的恒沉底**——没有数据就不参与竞争，
      逆序时把它们翻到最上面，用户会以为"这些最该看"；
    - **次要键（目录名）恒升序**——方向只作用于用户选的那个维度；
    - 未知 sort / order 静默回退默认（前端传参可能来自 URL，容错比严格更好）。

    状态排序的档位在逆序时手工取反（`2 - x`），而不是用 `reverse=True`：
    后者会把整个 key 元组一起翻，未评分的沉底与目录名升序也就跟着翻了。
    """
    desc = (order if order in JOB_ORDERS
            else JOB_DEFAULT_ORDER.get(sort, "asc")) == "desc"

    if sort == "score":
        return sorted(items, key=lambda i: (
            0 if i["score"] is not None else 1,
            -(i["score"] or 0) if desc else (i["score"] or 0),
            i["dir"]))
    if sort == "state":
        # 未投递 → 流程中 → 已终态；同状态内按评分降序、未评分沉底。
        # 注意组内评分的默认就是**降序**（与 score / recent 的整体降序同一语义），
        # 所以逆序时它反而是升序——「逆序」翻的是整个排序，不是每个键各自取反。
        state_order = {"未投递": 0, "流程中": 1, "已终态": 2}
        return sorted(items, key=lambda i: (
            state_order[i["applyState"]] if not desc else 2 - state_order[i["applyState"]],
            0 if i["score"] is not None else 1,
            -(i["score"] or 0) if not desc else (i["score"] or 0),
            i["dir"]))
    if sort == "recent":
        return sorted(items, key=lambda i: (
            0 if i["mtime"] else 1,
            -(i["mtime"] or 0) if desc else (i["mtime"] or 0),
            i["dir"]))
    return sorted(items, key=lambda i: i["dir"], reverse=desc)


@router.get("")
def list_jobs(sort: str = "dir", order: str = None, status: str = None,
              ws: str = Depends(workspace_dir)):
    base = safe_join(ws, DIR_JOBS)
    if not os.path.isdir(base):
        return {"items": [], "total": 0}

    index = _applications_by_key(ws)
    items = []
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not (os.path.isdir(d) and not name.startswith("_")):
            continue
        items.append(_summary(ws, name, index))

    if status in JOB_STATUS:
        want = JOB_STATUS[status]
        items = [i for i in items if i["applyState"] == want]
    items = _sort_jobs(items, sort if sort in JOB_SORTS else "dir", order)
    return {"items": items, "total": len(items)}


@router.post("")
def create_job(job: NewJob, ws: str = Depends(workspace_dir)):
    if not job.公司.strip() or not job.岗位.strip():
        raise HTTPException(status_code=422, detail="公司与岗位不能为空")
    if not job.JD文本.strip():
        raise HTTPException(status_code=422, detail="JD 文本不能为空")

    name = _dir_name(job.公司, job.岗位)
    job_dir = safe_join(ws, DIR_JOBS, name)

    if os.path.exists(job_dir):
        raise HTTPException(status_code=409, detail="岗位已存在: %s" % name)

    lock_path = safe_join(ws, DIR_JOBS, ".jobs.lock")
    os.makedirs(safe_join(ws, DIR_JOBS), exist_ok=True)

    with file_lock(lock_path):
        if os.path.exists(job_dir):  # 双检：并发下同名
            raise HTTPException(status_code=409, detail="岗位已存在: %s" % name)
        os.makedirs(job_dir)
        with io.open(os.path.join(job_dir, JD_FILE), "w", encoding="utf-8", newline="") as f:
            f.write("# %s %s\n\n%s\n" % (job.公司.strip(), job.岗位.strip(), job.JD文本.strip()))

    return _summary(ws, name)


# ---------------------------------------------------------------------------
# JD 链接抓取（第三批）：粘贴网页链接 → 抓正文存 JD原文.md
#
# 抓取是「尽力而为」的能力：招聘网站形态各异，大量页面需登录或由 JS 渲染。
# 所以失败与「正文过短」都要**明确降级**提示手动粘贴，绝不把半截内容或
# 空壳当成抓取成功——假装成功比直接说抓不到更浪费用户时间。
# ---------------------------------------------------------------------------

class FetchJdRequest(BaseModel):
    url: str
    公司: str
    岗位: str


def _html_to_text(html: str) -> str:
    """去脚本/样式/标签，把块级标签折成换行，压缩多余空白。"""
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    # 块级标签 → 换行，避免整页糊成一坨
    text = re.sub(r"(?i)</?(p|div|br|li|tr|h[1-6]|section|article)[^>]*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    # 常见实体
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _decode(raw: bytes, content_type: str) -> str:
    """按 Content-Type 或 meta charset 解码，失败回退 utf-8 / gbk。"""
    charset = None
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    else:
        head = raw[:2048].decode("ascii", errors="replace")
        m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
        if m:
            charset = m.group(1)
    for enc in (charset, "utf-8", "gbk"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


@router.post("/fetch-jd")
def fetch_jd(item: FetchJdRequest, ws: str = Depends(workspace_dir)):
    url = (item.url or "").strip()
    company = (item.公司 or "").strip()
    role = (item.岗位 or "").strip()
    if not company or not role:
        raise HTTPException(status_code=422, detail="公司与岗位不能为空")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=422, detail="请填写 http(s) 开头的完整链接")

    req = urllib.request.Request(url, headers={
        # 部分站点对默认 UA 直接返回 403，伪装成普通浏览器
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(FETCH_MAX_BYTES)
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail="页面返回 %s（可能需要登录或有反爬），请手动粘贴 JD" % exc.code)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502,
                            detail="抓不到这个链接：%s，请手动粘贴 JD" % exc.reason)
    except Exception as exc:  # noqa: BLE001 - 网络异常种类太多，统一降级
        raise HTTPException(status_code=502,
                            detail="抓取失败：%s，请手动粘贴 JD" % exc)

    text = _html_to_text(_decode(raw, content_type))
    if len(text) < JD_MIN_CHARS:
        raise HTTPException(
            status_code=422,
            detail="只抓到 %d 字（可能需登录或由 JS 渲染），不足以当作 JD，请手动粘贴" % len(text))

    name = _dir_name(company, role)
    job_dir = safe_join(ws, DIR_JOBS, name)

    lock_path = safe_join(ws, DIR_JOBS, ".jobs.lock")
    os.makedirs(safe_join(ws, DIR_JOBS), exist_ok=True)
    with file_lock(lock_path):
        if not os.path.isdir(job_dir):
            os.makedirs(job_dir)
        content = ("# %s %s\n\n来源：%s\n抓取时间：%s\n\n%s\n"
                   % (company, role, url,
                      datetime.now().strftime("%Y-%m-%d %H:%M"), text))
        # 原子写：JD 原文是后续评分与差距分析的输入，写坏会污染整条链路
        atomicio.atomic_write_text(os.path.join(job_dir, JD_FILE), content,
                                   encoding="utf-8")

    return dict(_summary(ws, name), characters=len(text), url=url)


@router.get("/{job_id}")
def job_detail(job_id: str, ws: str = Depends(workspace_dir)):
    job_dir = safe_join(ws, DIR_JOBS, job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail="岗位不存在: %s" % job_id)

    jd = _read(os.path.join(job_dir, JD_FILE))
    card_raw = _read(os.path.join(job_dir, CARD_FILE))
    card = _parse_card(ws, os.path.join(DIR_JOBS, job_id))
    # 详情也带上列表同款字段（含投递状态）：详情与列表不说两套话
    return dict({
        "dir": job_id,
        "jd": jd,
        "cardRaw": card_raw,
        "card": card,
    }, **_link_fields(ws, job_id))


@router.get("/{job_id}/gap")
def job_gap(job_id: str, ws: str = Depends(workspace_dir), resume: str = None):
    """JD↔简历差距清单（missing / injectable 二分）。

    复用 jd_score.gap_analysis，不重写词典解析与匹配逻辑。
    resume 缺省时取简历工坊里最新的版本（用户通常想看"当前版"的差距）。
    """
    job_dir = safe_join(ws, DIR_JOBS, job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail="岗位不存在: %s" % job_id)

    # 差距分析只依赖 JD 原文（gap_analysis 用其目录定位），解析卡不必须——
    # 新建岗位尚无解析卡时也应能看差距
    card = os.path.join(job_dir, CARD_FILE)

    version = (resume or "").strip()
    if not version:
        source_dir = safe_join(ws, "02_简历工坊", "source")
        versions = [
            f[len("resume_"):-len(".json")]
            for f in sorted(os.listdir(source_dir))
            if f.startswith("resume_") and f.endswith(".json")
        ] if os.path.isdir(source_dir) else []
        if not versions:
            raise HTTPException(
                status_code=404,
                detail="简历工坊里还没有任何版本，先在简历工坊创建一个")
        version = versions[-1]

    result, errors = jd_score.gap_analysis(ws, card, version)
    if result is None:
        raise HTTPException(status_code=422, detail="；".join(errors))
    return dict(result, resumeVersion=version, warnings=errors)
