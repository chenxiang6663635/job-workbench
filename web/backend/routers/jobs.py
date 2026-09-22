# -*- coding: utf-8 -*-
"""岗位池：列表、新建、详情。

岗位目录结构（与 CLI 的 jd 工作流一致）：
    01_岗位池/<公司>_<岗位>/
    ├── JD原文.md
    └── 解析卡.md

解析卡的评分小节由 tools/jobws.py jd 的解析函数读取——评分由 AI CLI
完成写入，Web 只做查看与展示，不做评分决策。
"""

from __future__ import annotations

import io
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import atomicio
from jobws_core import job_dirs
from jobws_core import job_rename
from jobws_core import jd_score
import tls_http
from jobws_core import tracker
from apierror import ApiError
from deps import DIR_JOBS, safe_join, workspace_dir
from jobws_core.filelock import file_lock
from routers.progress._shared import delete_preview_response

router = APIRouter(prefix="/api/jobs")

JD_FILE = "JD原文.md"
CARD_FILE = "解析卡.md"

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
    """薄包装：生成与校验在领域层（job_dirs.build_dir_name，单一事实源——
    改名预览与创建必须同一份口径）；错误码按消息分派，维持既有契约不变。"""
    name, error = job_dirs.build_dir_name(company, role)
    if error:
        code = "job.nameEmpty" if "不能为空" in error else "job.nameInvalid"
        raise ApiError(422, code, error)
    return name


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
    给人看的详细描述（如「示例集团（空调事业部＝…）」），当键会与追踪表系统性失配。
    """
    return (_card_basic_info(workspace, os.path.join(DIR_JOBS, name))
            or job_dirs.split_dir_name(name))


def _link_fields(workspace: str, name: str, app_index: dict = None):
    """岗位与追踪表记录的关联字段——列表与详情共用，保证两处口径一致。

    **匹配键只取目录名拆分**（`job_dirs.split_dir_name`）：追踪表里的 (公司, 岗位) 是按
    目录名口径录的，两边同源才匹配得上；解析卡「基本信息」里的名值往往更
    详细（真实数据里就与追踪表不一致），拿它当键会系统性失配。

    没有记录时后三个字段全为空，前端据此显示「未投递」。
    """
    company, role = _job_company_role(workspace, name)   # 展示名：卡片优先
    match_company, match_role = job_dirs.split_dir_name(name)  # 匹配键：目录名口径
    if app_index is None:
        app_index = job_dirs.applications_by_key(workspace)
    row = app_index.get(tracker.dedup_key(match_company, match_role))
    return {
        "company": company,
        "role": role,
        "applyState": job_dirs.apply_state(row),
        "stage": (row or {}).get("当前阶段") or None,
        "applicationId": (row or {}).get("id") or None,
    }


def _summary(workspace: str, name: str, app_index: dict = None):
    """单个岗位的列表条目。

    列表端点一次建好索引整批传入（`job_dirs.applications_by_key`）；单条调用
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

    状态排序的档位在逆序时手工取反（`-state_order[x]`，对任意档数天然成立），
    而不是用 `reverse=True`：后者会把整个 key 元组一起翻，
    未评分的沉底与目录名升序也就跟着翻了。
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
            state_order[i["applyState"]] if not desc else -state_order[i["applyState"]],
            0 if i["score"] is not None else 1,
            -(i["score"] or 0) if not desc else (i["score"] or 0),
            i["dir"]))
    if sort == "recent":
        # mtime=0 理论上会落「无时间」桶；真实文件系统给不出 0，不另设防
        return sorted(items, key=lambda i: (
            0 if i["mtime"] else 1,
            -(i["mtime"] or 0) if desc else (i["mtime"] or 0),
            i["dir"]))
    return sorted(items, key=lambda i: i["dir"], reverse=desc)


@router.get("")
def list_jobs(sort: str = "dir", order: str = None, status: str = None,
              q: str = None, ws: str = Depends(workspace_dir)):
    base = safe_join(ws, DIR_JOBS)
    if not os.path.isdir(base):
        return {"items": [], "total": 0}

    index = job_dirs.applications_by_key(ws)
    items = []
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not (os.path.isdir(d) and not name.startswith("_")):
            continue
        items.append(_summary(ws, name, index))

    if status in JOB_STATUS:
        want = JOB_STATUS[status]
        items = [i for i in items if i["applyState"] == want]
    # 关键词在 _summary 之后过滤：公司 / 岗位来自目录名拆分与解析卡，只有条目里有。
    # 匹配口径在领域层（job_dirs.match_keyword），与追踪表的搜索同源。
    if q and q.strip():
        items = [i for i in items if job_dirs.match_keyword(i, q)]
    items = _sort_jobs(items, sort if sort in JOB_SORTS else "dir", order)
    return {"items": items, "total": len(items)}


@router.post("")
def create_job(job: NewJob, ws: str = Depends(workspace_dir)):
    if not job.公司.strip() or not job.岗位.strip():
        raise ApiError(422, "job.companyRoleRequired", "公司与岗位不能为空")
    if not job.JD文本.strip():
        raise ApiError(422, "job.jdRequired", "JD 文本不能为空")

    name = _dir_name(job.公司, job.岗位)
    job_dir = safe_join(ws, DIR_JOBS, name)

    if os.path.exists(job_dir):
        raise ApiError(409, "job.exists", "岗位已存在: %s" % name, name=name)

    lock_path = safe_join(ws, DIR_JOBS, ".jobs.lock")
    os.makedirs(safe_join(ws, DIR_JOBS), exist_ok=True)

    with file_lock(lock_path):
        if os.path.exists(job_dir):  # 双检：并发下同名
            raise ApiError(409, "job.exists", "岗位已存在: %s" % name, name=name)
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
        raise ApiError(422, "job.companyRoleRequired", "公司与岗位不能为空")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ApiError(422, "job.urlInvalid", "请填写 http(s) 开头的完整链接")

    req = urllib.request.Request(url, headers={
        # 部分站点对默认 UA 直接返回 403，伪装成普通浏览器
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        # 出网统一走 tls_http（策略唯一实现在 jobws_core.tls_policy，见 issue #59）
        with tls_http.open_url(req, timeout=FETCH_TIMEOUT,
                               purpose="抓取 JD 链接") as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(FETCH_MAX_BYTES)
    except ApiError:
        # tls_http 已翻译过的证书类错误（sys.certStoreUnavailable /
        # sys.certUntrusted）必须原样上抛：下面的 `except Exception` 会把它兜成
        # 「抓取失败：…」，用户就又看不到"修证书库"这一步了。
        raise
    except urllib.error.HTTPError as exc:
        raise ApiError(502, "job.fetchHttpError",
                       "页面返回 %s（可能需要登录或有反爬），请手动粘贴 JD" % exc.code,
                       status=str(exc.code))
    except urllib.error.URLError as exc:
        raise ApiError(502, "job.fetchUnreachable",
                       "抓不到这个链接：%s，请手动粘贴 JD" % exc.reason,
                       reason=str(exc.reason))
    except Exception as exc:  # noqa: BLE001 - 网络异常种类太多，统一降级
        raise ApiError(502, "job.fetchFailed",
                       "抓取失败：%s，请手动粘贴 JD" % exc, error=str(exc))

    text = _html_to_text(_decode(raw, content_type))
    if len(text) < JD_MIN_CHARS:
        raise ApiError(
            422, "job.fetchTooShort",
            "只抓到 %d 字（可能需登录或由 JS 渲染），不足以当作 JD，请手动粘贴" % len(text),
            # 参数名别用 count：那是 i18next 的保留插值名，会触发复数解析
            # （去查 err.xxx_other），文案得靠回落才显示得出来——改了名才是稳的
            chars=len(text))

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


# 2026-09-21 批 D：删除 / 改名的预览端点。**必须注册在 `/{job_id}` 之前**——
# FastAPI 按注册顺序匹配，否则 "preview-delete" 会被当成一个岗位名（404）。
@router.get("/preview-delete")
def preview_delete_job(name: str = "", ws: str = Depends(workspace_dir)):
    """预览删除一个岗位目录（**不落盘**）：列目录内全部文件 + 关联投递提示。

    确认后凭令牌走 `/api/approvals/apply` 落盘；落盘前**整个目录**复制到快照区
    （工作区之外），恢复 = 拷回 `01_岗位池/`。
    """
    errors, plan = job_dirs.preview_delete_job(name, ws)
    return delete_preview_response("job.delete", errors, plan,
                                   "job.deleteFailed", "岗位删除预览失败", ws)


@router.get("/preview-rename")
def preview_rename_job(name: str = "", company: str = "", role: str = "",
                       ws: str = Depends(workspace_dir)):
    """预览岗位改名（**不落盘**）：目录名 `旧 → 新`；JD 首行标题可同步时一并列出。

    改名 = os.rename（可逆，不做目录快照）；只在 JD 首行确实是 `# 标题` 时
    同步改写，其余内容一字不动。
    """
    errors, plan = job_rename.preview_rename_job(name, company, role, ws)
    return delete_preview_response("job.rename", errors, plan,
                                   "job.renameFailed", "岗位改名预览失败", ws)


@router.get("/{job_id}")
def job_detail(job_id: str, ws: str = Depends(workspace_dir)):
    job_dir = safe_join(ws, DIR_JOBS, job_id)
    if not os.path.isdir(job_dir):
        raise ApiError(404, "job.notFound", "岗位不存在: %s" % job_id, id=job_id)

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
        raise ApiError(404, "job.notFound", "岗位不存在: %s" % job_id, id=job_id)

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
            raise ApiError(404, "job.resumeVersionMissing",
                           "简历工坊里还没有任何版本，先在简历工坊创建一个")
        version = versions[-1]

    result, errors = jd_score.gap_analysis(ws, card, version)
    if result is None:
        raise ApiError(422, "job.gapFailed", "；".join(errors), errors="；".join(errors))
    return dict(result, resumeVersion=version, warnings=errors)
