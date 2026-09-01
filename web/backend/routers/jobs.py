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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import jd_score
from deps import DIR_JOBS, safe_join, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/jobs")

JD_FILE = "JD原文.md"
CARD_FILE = "解析卡.md"
INVALID_DIR_CHARS = set('\\/:*?"<>|')


def _dir_name(company: str, role: str) -> str:
    name = ("%s_%s" % (company.strip(), role.strip())).strip()
    bad = [c for c in name if c in INVALID_DIR_CHARS or ord(c) < 32]
    if bad:
        raise HTTPException(status_code=422,
                            detail="公司或岗位名含非法字符: %s" % "".join(sorted(set(bad))))
    if not name or name.strip(". ") in ("", ".", ".."):
        raise HTTPException(status_code=422, detail="目录名不能为空或纯点号")
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


def _summary(workspace: str, name: str):
    d = safe_join(workspace, DIR_JOBS, name)
    # 与 job_detail 调用方式相同，传带 DIR_JOBS 前缀的相对路径
    card = _parse_card(workspace, os.path.join(DIR_JOBS, name))
    # 以解析成功为基准，而非文件存在——存在但不通过的卡片不算"已评分"
    has_card = card is not None and card.get("consistent") and card.get("total") is not None
    return {
        "dir": name,
        "hasJD": _read(os.path.join(d, JD_FILE)) is not None,
        "hasCard": has_card,
        "score": card["total"] if has_card else None,
        "level": card["level"] if card else None,
        "mtime": int(os.path.getmtime(d)) if os.path.isdir(d) else None,
    }


class NewJob(BaseModel):
    公司: str
    岗位: str
    JD文本: str


@router.get("")
def list_jobs(ws: str = Depends(workspace_dir)):
    base = safe_join(ws, DIR_JOBS)
    if not os.path.isdir(base):
        return {"items": [], "total": 0}

    items = []
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if os.path.isdir(d) and not name.startswith("_"):
            items.append(_summary(ws, name))
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


@router.get("/{job_id}")
def job_detail(job_id: str, ws: str = Depends(workspace_dir)):
    job_dir = safe_join(ws, DIR_JOBS, job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail="岗位不存在: %s" % job_id)

    jd = _read(os.path.join(job_dir, JD_FILE))
    card_raw = _read(os.path.join(job_dir, CARD_FILE))
    return {
        "dir": job_id,
        "jd": jd,
        "cardRaw": card_raw,
        "card": _parse_card(ws, os.path.join(DIR_JOBS, job_id)),
    }
