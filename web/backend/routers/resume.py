# -*- coding: utf-8 -*-
"""简历工坊：标准版式的数据读写、预览与生成。

路线 A：数据驱动只服务一份「标准版式」，现有手写 HTML 的精排版本
（高级模板）不由此接管，仍在素材库里只读浏览、由 CLI 生成。

复用 tools/resume_build.py 的 render_block / build_pdf / verify_pdf，
此处只做 HTTP 编排与文件锁，不重写渲染与校验逻辑。
"""

from __future__ import annotations

import io
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import resume_build
from deps import DIR_RESUME, safe_join, workspace_dir
from filelock import file_lock

router = APIRouter(prefix="/api/resume")

# 数据驱动文件所在子目录；PDF 输出沿用现有 pdf/ 目录
DIR_SOURCE = "source"
DIR_PDF = "pdf"


class ResumeData(BaseModel):
    """JSON schema 的宽松容器：结构由 resume_<版本>.json 定义，
    此处不做逐字段校验——逐字段校验会随 schema 演进反复改动，
    交给 render_block 在渲染时按字段有无驱动区块。
    """
    data: dict


def _source_dir(ws):
    return safe_join(ws, DIR_RESUME, DIR_SOURCE)


def _pdf_dir(ws):
    return safe_join(ws, DIR_RESUME, DIR_PDF)


def _data_path(ws, version):
    return safe_join(ws, DIR_RESUME, DIR_SOURCE, "resume_%s.json" % version)


def _lock_path(ws):
    lock_dir = os.path.join(ws, DIR_RESUME)
    if not os.path.isdir(lock_dir):
        os.makedirs(lock_dir)
    return os.path.join(lock_dir, "resume.lock")


def _check_version(version):
    # 只允许安全字符，避免用版本名拼路径时穿越目录
    if not version or not all(c.isalnum() or c in "-_" for c in version):
        raise HTTPException(status_code=400, detail="版本名只能含字母、数字、-、_")


@router.get("")
def list_versions(ws: str = Depends(workspace_dir)):
    """列出标准版式可用的数据版本（source/resume_*.json）。"""
    source_dir = _source_dir(ws)
    if not os.path.isdir(source_dir):
        return {"items": [], "total": 0}
    items = []
    for name in sorted(os.listdir(source_dir)):
        if name.startswith("resume_") and name.endswith(".json"):
            stem = name[len("resume_"):-len(".json")]
            full = os.path.join(source_dir, name)
            pdf_path = os.path.join(_pdf_dir(ws), "简历_%s.pdf" % stem)
            items.append({
                "version": stem,
                "size": os.path.getsize(full),
                "mtime": int(os.path.getmtime(full)),
                "hasPdf": os.path.isfile(pdf_path),
            })
    return {"items": items, "total": len(items)}


@router.get("/{version}")
def get_resume(version: str, ws: str = Depends(workspace_dir)):
    _check_version(version)
    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="找不到简历数据: resume_%s.json" % version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="JSON 解析失败：%s" % exc)
    return {"version": version, "data": data}


@router.put("/{version}")
def save_resume(version: str, body: ResumeData, ws: str = Depends(workspace_dir)):
    _check_version(version)
    path = _data_path(ws, version)
    source_dir = os.path.dirname(path)
    with file_lock(_lock_path(ws)):
        if not os.path.isdir(source_dir):
            os.makedirs(source_dir)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(body.data, f, ensure_ascii=False, indent=2)
    return {"version": version, "saved": True}


@router.get("/{version}/html")
def preview_html(version: str, ws: str = Depends(workspace_dir)):
    """返回渲染后的完整 HTML，供前端 iframe 预览（不落盘）。"""
    _check_version(version)
    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="找不到简历数据: resume_%s.json" % version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="JSON 解析失败：%s" % exc)
    try:
        tpl = resume_build.load_template()
        return {"version": version, "html": resume_build.render_block(tpl, data)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="渲染失败：%s" % exc)


@router.post("/{version}/build")
def build_resume(version: str, ws: str = Depends(workspace_dir)):
    """生成 PDF 并做 ATS 三项校验 + A4 纸型校验。"""
    _check_version(version)
    browser = resume_build.find_browser()
    if not browser:
        raise HTTPException(status_code=500, detail="未找到 Chrome 或 Edge，无法生成 PDF")

    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="找不到简历数据: resume_%s.json" % version)

    with file_lock(_lock_path(ws)):
        try:
            with io.open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="JSON 解析失败：%s" % exc)

        pdf_dir = _pdf_dir(ws)
        if not os.path.isdir(pdf_dir):
            os.makedirs(pdf_dir)
        pdf_path = os.path.join(pdf_dir, "简历_%s.pdf" % version)
        tmp_html = os.path.join(pdf_dir, "__preview_%s.html" % version)

        try:
            tpl = resume_build.load_template()
            with io.open(tmp_html, "w", encoding="utf-8") as f:
                f.write(resume_build.render_block(tpl, data))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="渲染失败：%s" % exc)

        try:
            ok = resume_build.build_pdf(browser, tmp_html, pdf_path)
        finally:
            if os.path.isfile(tmp_html):
                try:
                    os.remove(tmp_html)
                except OSError:
                    pass

        if not ok:
            raise HTTPException(status_code=500, detail="PDF 未生成（浏览器打印失败或超时）")

        a4_ok, a4_msg = resume_build.check_a4_mediabox(pdf_path)
        # 显式传 facts_file：模块级 VERIFY_FACTS_FILE 在并发下会互相覆盖
        facts_file = os.path.join(ws, "config", "ats_required_facts.txt")
        passed, details = resume_build.verify_pdf(pdf_path, facts_file=facts_file)

        return {
            "version": version,
            "pdf": os.path.relpath(pdf_path, ws).replace("\\", "/"),
            "size": os.path.getsize(pdf_path),
            "a4": {"ok": a4_ok, "message": a4_msg},
            "checks": [{"label": l, "value": v, "ok": o} for l, v, o in details],
            "passed": bool(passed and a4_ok),
        }
