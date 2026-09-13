# -*- coding: utf-8 -*-
"""简历工坊：标准版式编辑 + 高级模板只读浏览。

双职责（2026-09-03 信息架构调整，简历相关能力全部收拢到此路由）：
- 标准版式：resume_<版本>.json 的读写、预览与生成（数据驱动）
- 高级模板：手写 HTML 精排版的文件浏览（只读）与生成——原在素材库，
  现迁入此处；编辑仍走手写 HTML / CLI，Web 不提供编辑。

复用 tools/resume_build.py 的 render_block / build_pdf / verify_pdf，
此处只做 HTTP 编排与文件锁，不重写渲染与校验逻辑。
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import tempfile
import urllib.parse

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

import atomicio
import resume_build
from apierror import ApiError
import resume_import
from deps import DIR_RESUME, safe_join, workspace_dir
from filelock import file_lock
from routers import provider

router = APIRouter(prefix="/api/resume")

# 数据驱动文件所在子目录；PDF 输出沿用现有 pdf/ 目录
DIR_SOURCE = "source"
DIR_PDF = "pdf"

# 高级模板浏览：md/html 之外按二进制（PDF/图片）处理
TEMPLATE_TEXT_EXT = {".md", ".txt", ".html"}


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
        raise ApiError(400, "resume.versionInvalid", "版本名只能含字母、数字、-、_")


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


# ---------------------------------------------------------------------------
# 高级模板（手写 HTML 精排版）：只读浏览 + 生成。
# 原为素材库的「简历工坊」分类，2026-09-03 收拢到简历域（/api/resume/templates）。
# 编辑仍走手写 HTML / CLI，Web 不提供编辑入口。
# 注意：这些具体路由必须注册在 /{version} 之前，否则 GET /templates 会被
# 动态参数路由抢先匹配成 version="templates"。
# ---------------------------------------------------------------------------


def _resume_dir(ws):
    return safe_join(ws, DIR_RESUME)


def _list_template_files(base):
    if not os.path.isdir(base):
        return []
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith("__")]
        for name in sorted(files):
            if name.startswith("."):
                continue
            # source/ 是标准版式的数据（编辑器管），不进高级模板浏览
            rel = os.path.relpath(os.path.join(root, name), base)
            if rel.split(os.sep)[0] == DIR_SOURCE or name.endswith(".lock"):
                continue
            full = os.path.join(root, name)
            out.append({
                "rel": rel.replace("\\", "/"),
                "name": name,
                "size": os.path.getsize(full),
                "mtime": int(os.path.getmtime(full)),
                "kind": "text" if os.path.splitext(name)[1].lower() in TEMPLATE_TEXT_EXT else "binary",
            })
    out.sort(key=lambda x: x["rel"])
    return out


@router.get("/templates")
def list_templates(ws: str = Depends(workspace_dir)):
    items = _list_template_files(_resume_dir(ws))
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# 简历一键导入（第一批）
#
# 上传 PDF/docx/MD/TXT → 抽取文本 → BYOK 结构化 → 可溯源校验 → 返回核对数据。
# 本端点**绝不落盘**：结果必须经前端核对页逐段确认后，再走既有 PUT 保存。
# 上传文件只在本机临时目录短暂驻留，用完即删，不进工作区（也就不会进快照/git）。
# 注意：具体路由必须注册在 /{version} 之前，否则会被动态参数路由抢先匹配。
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    """简历导入请求。文件以 base64 随 JSON 提交（避免引入 multipart 依赖）。"""
    filename: str
    content_base64: str
    model: str = ""


@router.post("/import")
def import_resume(item: ImportRequest, ws: str = Depends(workspace_dir)):
    cfg = provider.read_config(ws)
    if not cfg.get("base_url") or not cfg.get("api_key"):
        raise ApiError(400, "resume.providerMissing",
                       "先在「设置」配置 Provider（BYOK）：base_url 与 api_key")
    if not (item.model or "").strip():
        raise ApiError(422, "resume.modelRequired", "请填写模型名（如 deepseek-chat）")

    # 前端把文件读成 base64 随 JSON 提交——multipart 需要额外依赖
    # python-multipart，而本项目不引入任何新运行时依赖
    try:
        content = base64.b64decode(item.content_base64 or "", validate=True)
    except (ValueError, TypeError):
        raise ApiError(422, "resume.fileDecodeFailed", "文件内容解码失败")

    filename = item.filename or ""
    tmp_dir = tempfile.mkdtemp(prefix="jobws_import_")
    try:
        try:
            path, ext = resume_import.save_upload(content, filename, tmp_dir)
            text = resume_import.extract_text(path, ext)
        except ValueError as exc:
            raise ApiError(422, "resume.extractFailed", str(exc), error=str(exc))

        prompt = resume_import.build_import_prompt(text)
        try:
            raw = _call_llm(cfg, prompt, item.model.strip())
            data = _extract_json(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:200]
            raise ApiError(502, "resume.modelHttpError",
                           "模型端点返回 %s：%s" % (exc.code, body),
                           status=str(exc.code), body=body)
        except urllib.error.URLError as exc:
            # 连不上端点（被墙/DNS/端口错），不要 500，降级成可理解的错误
            raise ApiError(502, "resume.modelUnreachable",
                           "连不上模型端点：%s" % exc.reason,
                           reason=str(exc.reason))
        except (ValueError, KeyError, OSError) as exc:
            raise ApiError(502, "resume.modelCallFailed",
                           "模型调用失败：%s" % exc, error=str(exc))

        if not isinstance(data, dict):
            raise ApiError(502, "resume.modelNotJson",
                           "模型返回不是 JSON 对象，请重试或换个模型")

        return {
            "file": filename,
            "characters": len(text),
            "text": text,
            "data": data,
            # 可溯源校验：值/数字对不上原文的要标红，由用户核对
            "issues": resume_import.traceable_issues(text, data),
            # 未抽取到的关键字段标黄，提示补填（留空本身合规）
            "unfilled": resume_import.unfilled_fields(data),
            "model": item.model.strip(),
        }
    finally:
        # 上传内容用完即删：不留在磁盘上
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/templates/content")
def template_content(rel: str, ws: str = Depends(workspace_dir)):
    full = safe_join(ws, DIR_RESUME, rel)
    if not os.path.isfile(full):
        raise ApiError(404, "resume.fileNotFound",
                           "文件不存在: %s" % rel, rel=rel)
    if os.path.splitext(rel)[1].lower() not in TEMPLATE_TEXT_EXT:
        return {"rel": rel, "type": "binary"}
    with io.open(full, "r", encoding="utf-8") as f:
        return {"rel": rel, "type": "text", "content": f.read()}


@router.get("/templates/file/{rel:path}")
def template_file(rel: str, ws: str = Depends(workspace_dir)):
    """文件原始字节。用路径参数而非 query——iframe 里 HTML 的相对资源
    （如 photo.jpg）由浏览器按同路径解析，路径式端点才能命中。
    """
    full = safe_join(ws, DIR_RESUME, rel)
    if not os.path.isfile(full):
        raise ApiError(404, "resume.fileNotFound",
                           "文件不存在: %s" % rel, rel=rel)

    ext = os.path.splitext(rel)[1].lower()
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_type = "image/%s" % ext.lstrip(".")
    elif ext == ".html":
        media_type = "text/html"
    else:
        media_type = "application/octet-stream"

    with open(full, "rb") as f:
        data = f.read()
    # 不设 Content-Disposition：中文文件名放 header 会触发 latin-1 编码异常，
    # 这里是内联预览（iframe / img），浏览器用 URL 定位即可
    return Response(content=data, media_type=media_type)


@router.post("/templates/{version}/build")
def build_template(version: str, ws: str = Depends(workspace_dir)):
    """手写 HTML 高级模板 → PDF + ATS 校验（与 CLI 无子命令路径同源）。"""
    _check_version(version)
    browser = resume_build.find_browser()
    if not browser:
        raise ApiError(500, "resume.chromeMissing", "未找到 Chrome 或 Edge，无法生成 PDF")

    pdf_dir = _pdf_dir(ws)
    html_path = os.path.join(pdf_dir, "resume_%s.html" % version)
    if not os.path.isfile(html_path):
        raise ApiError(404, "resume.templateNotFound",
                       "找不到手写模板: resume_%s.html" % version, version=version)

    with file_lock(_lock_path(ws)):
        pdf_path = os.path.join(pdf_dir, "简历_%s.pdf" % version)
        ok = resume_build.build_pdf(browser, html_path, pdf_path)
        if not ok:
            raise ApiError(500, "resume.pdfFailed", "PDF 未生成（浏览器打印失败或超时）")

        a4_ok, a4_msg = resume_build.check_a4_mediabox(pdf_path)
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


@router.get("/{version}")
def get_resume(version: str, ws: str = Depends(workspace_dir)):
    _check_version(version)
    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise ApiError(404, "resume.dataNotFound",
                       "找不到简历数据: resume_%s.json" % version, version=version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise ApiError(422, "resume.jsonInvalid",
                               "JSON 解析失败：%s" % exc, error=str(exc))
    return {"version": version, "data": data}


@router.put("/{version}")
def save_resume(version: str, body: ResumeData, ws: str = Depends(workspace_dir)):
    _check_version(version)
    path = _data_path(ws, version)
    source_dir = os.path.dirname(path)
    with file_lock(_lock_path(ws)):
        if not os.path.isdir(source_dir):
            os.makedirs(source_dir)
        # 原子写：简历 JSON 是用户唯一的数据源，写到一半被中断会留下半截文件。
        # 注意必须先序列化再落盘——若边序列化边写，序列化中途异常会写出残缺 JSON。
        content = json.dumps(body.data, ensure_ascii=False, indent=2)
        atomicio.atomic_write_text(path, content, encoding="utf-8")
    return {"version": version, "saved": True}


@router.get("/{version}/html")
def preview_html(version: str, ws: str = Depends(workspace_dir)):
    """返回渲染后的完整 HTML，供前端 iframe 预览（不落盘）。"""
    _check_version(version)
    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise ApiError(404, "resume.dataNotFound",
                       "找不到简历数据: resume_%s.json" % version, version=version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise ApiError(422, "resume.jsonInvalid",
                               "JSON 解析失败：%s" % exc, error=str(exc))
    try:
        tpl = resume_build.load_template()
        return {"version": version, "html": resume_build.render_block(tpl, data)}
    except Exception as exc:  # noqa: BLE001
        raise ApiError(500, "resume.renderFailed",
                       "渲染失败：%s" % exc, error=str(exc))


@router.get("/{version}/doc")
def export_doc(version: str, ws: str = Depends(workspace_dir)):
    """零依赖导出 Word（.doc）：复用 PDF 同一条渲染链路产出 HTML，
    补 Word 能识别的 HTML 头后以 application/msword 返回。

    定位是「文本搬运」：网申系统要求粘贴文本时从 Word 里复制最方便。
    排版以 PDF 为准——HTML 另存 .doc 的格式还原度有限，这一点必须
    在前端按钮旁向用户明示，绝不让用户误以为 .doc 是正式交付物。
    """
    _check_version(version)
    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise ApiError(404, "resume.dataNotFound",
                       "找不到简历数据: resume_%s.json" % version, version=version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise ApiError(422, "resume.jsonInvalid",
                               "JSON 解析失败：%s" % exc, error=str(exc))
    try:
        tpl = resume_build.load_template()
        body = resume_build.render_block(tpl, data)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(500, "resume.renderFailed",
                       "渲染失败：%s" % exc, error=str(exc))

    # Word 的 HTML 兼容头：显式 charset（否则中文按系统默认码页解码会乱码）
    doc_html = (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word">'
        '<head><meta charset="utf-8">'
        '<title>resume_%s</title></head>'
        "<body>%s</body></html>" % (version, body)
    )

    # Content-Disposition 的文件名含中文：header 只允许 latin-1，
    # 用 RFC 5987 的 filename* 携带 UTF-8 名字，ASCII 名做降级兜底
    quoted = urllib.parse.quote("简历_%s.doc" % version)
    headers = {
        "Content-Disposition": 'attachment; filename="resume_%s.doc"; '
                               "filename*=UTF-8''%s" % (version, quoted)
    }
    return Response(content=doc_html.encode("utf-8"),
                    media_type="application/msword", headers=headers)


@router.post("/{version}/build")
def build_resume(version: str, ws: str = Depends(workspace_dir)):
    """生成 PDF 并做 ATS 三项校验 + A4 纸型校验。"""
    _check_version(version)
    browser = resume_build.find_browser()
    if not browser:
        raise ApiError(500, "resume.chromeMissing", "未找到 Chrome 或 Edge，无法生成 PDF")

    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise ApiError(404, "resume.dataNotFound",
                       "找不到简历数据: resume_%s.json" % version, version=version)

    with file_lock(_lock_path(ws)):
        try:
            with io.open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except ValueError as exc:
            raise ApiError(422, "resume.jsonInvalid",
                               "JSON 解析失败：%s" % exc, error=str(exc))

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
            raise ApiError(500, "resume.renderFailed",
                       "渲染失败：%s" % exc, error=str(exc))

        try:
            ok = resume_build.build_pdf(browser, tmp_html, pdf_path)
        finally:
            if os.path.isfile(tmp_html):
                try:
                    os.remove(tmp_html)
                except OSError:
                    pass

        if not ok:
            raise ApiError(500, "resume.pdfFailed", "PDF 未生成（浏览器打印失败或超时）")

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


# ---------------------------------------------------------------------------
# diff 式改写建议（BYOK）+ 反编造护栏
#
# 流程：读简历 JSON → 拼带反编造条款的提示词 → 调 OpenAI 兼容端点 →
# 解析回 JSON → 本地校验器五项检查 → 返回建议与检查结果。
# 关键约束：本端点绝不落盘。建议必须由用户看过 diff 并显式确认后，
# 才通过既有的 PUT /{version} 保存——校验未通过的改动不允许静默接受。
# 条款与校验器被 tests/test_prompt_guardrails.py 锁死，删句即测试失败。
# ---------------------------------------------------------------------------

import re  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import resume_guard  # noqa: E402
from routers import provider  # noqa: E402

LLM_TIMEOUT = 90


class SuggestRequest(BaseModel):
    instruction: str
    model: str = ""


def _extract_json(content):
    """从模型回复中抠出 JSON。兼容 ```json 包裹与前后废话。"""
    text = (content or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("回复中没有 JSON 对象")
    return json.loads(text[start:end + 1])


def _call_llm(cfg, prompt, model):
    """调 OpenAI 兼容 /chat/completions。标准库 urllib，不引入依赖。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # 低温度：改写事实表述不是创意写作，越稳越好
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
    })
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("模型响应格式异常")


@router.post("/{version}/suggest")
def suggest_rewrite(version: str, item: SuggestRequest,
                    ws: str = Depends(workspace_dir)):
    _check_version(version)
    if not item.instruction.strip():
        raise ApiError(422, "resume.instructionRequired", "改写方向不能为空")

    cfg = provider.read_config(ws)
    if not cfg.get("base_url") or not cfg.get("api_key"):
        raise ApiError(400, "resume.providerMissing",
                       "先在「设置」配置 Provider（BYOK）：base_url 与 api_key")
    model = (item.model or "").strip()
    if not model:
        raise ApiError(422, "resume.modelRequired", "请填写模型名（如 deepseek-chat）")

    path = _data_path(ws, version)
    if not os.path.isfile(path):
        raise ApiError(404, "resume.dataNotFound",
                       "找不到简历数据: resume_%s.json" % version, version=version)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise ApiError(422, "resume.jsonInvalid",
                       "JSON 解析失败：%s" % exc, error=str(exc))

    prompt = resume_guard.build_rewrite_prompt(data, item.instruction)
    try:
        content = _call_llm(cfg, prompt, model)
        suggestion = _extract_json(content)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise ApiError(502, "resume.modelHttpError",
                       "模型端点返回 %s：%s" % (exc.code, detail),
                       status=str(exc.code), body=detail)
    except (ValueError, KeyError, OSError) as exc:
        raise ApiError(502, "resume.modelCallFailed",
                       "模型调用失败：%s" % exc, error=str(exc))

    # 五项护栏：空改动 / 结构漂移 / 身份字段 / 字数爆炸 / 新增数字
    ok, issues = resume_guard.validate_rewrite(data, suggestion)
    return {
        "version": version,
        "ok": ok,
        "issues": issues,
        "suggestion": suggestion,
        "model": model,
    }
