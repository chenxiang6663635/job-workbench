# -*- coding: utf-8 -*-
"""简历一键导入：文本抽取 + 导入提示词 + 可溯源校验。

与「AI 改写」的场景有根本差别：导入是**抽取**而不是生成——模型只允许把
文件里已经存在的文字搬进字段，缺失的一律留空，绝不补全、推测或美化数字。
这套约束由三样东西保证：

1. IMPORT_CLAUSE 条款（本文件），由 tests/test_prompt_guardrails.py 锁死
2. traceable_issues 可溯源校验：每个字段值都必须能在原文里找到
3. 前端核对页：未抽取到的字段标黄、疑似补全的字段标红，确认后才允许落盘

抽取只用标准库与已有的 pypdf，不引入新依赖；上传文件只在本机临时目录
短暂驻留，用完即删，绝不写进工作区（也就不会进快照和 git）。
"""

from __future__ import annotations

import io
import os
import re
import zipfile

# 允许上传的扩展名白名单（图片/扫描件不做 OCR）
ALLOWED_EXT = {".pdf", ".docx", ".md", ".markdown", ".txt"}
# 上传大小上限：防超大文件打爆内存
MAX_BYTES = 10 * 1024 * 1024

# 导入专用反编造条款。改这段文字 = 改产品伦理，测试会拦。
IMPORT_CLAUSE = (
    "【诚实红线（最高优先级，违反即整份结果作废）】\n"
    "你只能从简历原文中**抽取**已有的文字，填入对应的结构化字段。\n"
    "具体规则：\n"
    "1. 每个字段的值必须原样来自原文，不得改写措辞、不得合并润色；\n"
    "2. 原文没有的信息一律留空字符串，不得补全、不得推测、不得常识性填充；\n"
    "3. 不得新增、修改或美化任何数字、百分比、金额、人数、时长；\n"
    "4. 不得生成原文没有的项目、经历、技能或成果；\n"
    "5. 一段原文可以拆成多条要点，但每条要点本身必须是原文的子串。\n"
    "记不住就记这一句：你是在做「搬运」，不是在做「写作」。"
)

# 归一化用：全角标点 → 半角，便于「标点差异」不被误判为编造
_PUNCT_MAP = {
    "：": ":", "，": ",", "。": ".", "；": ";", "、": ",",
    "（": "(", "）": ")", "【": "[", "】": "]", "％": "%",
    "－": "-", "—": "-", "～": "~", "　": " ",
}
_WS_RE = re.compile(r"\s+")
# 数字 token（含小数与百分号），用于「数字必须来自原文」判定
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def normalize(text):
    """归一化：去空白差异 + 全角标点转半角。仅用于比对，不改变原值。"""
    if not text:
        return ""
    out = "".join(_PUNCT_MAP.get(ch, ch) for ch in text)
    return _WS_RE.sub("", out).strip()


def extract_text(path, ext):
    """从文件中抽取纯文本。ext 需带点（如 .pdf）。

    PDF 走 pypdf（项目已有依赖）；docx 是 zip + XML，标准库解析；
    md/txt 直接读，编码失败依次回退 utf-8-sig / gbk。
    """
    ext = (ext or "").lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("不支持的文件类型：%s（支持 %s）"
                         % (ext, "/".join(sorted(ALLOWED_EXT))))

    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    return _read_text_file(path)


def _extract_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("缺少 pypdf，无法解析 PDF：pip install pypdf")

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - 单页解析失败不应中断整份抽取
            pages.append("")
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("PDF 里没有可提取的文字（可能是扫描件或图片版，"
                         "本工具不做 OCR，请改用文本版简历）")
    return text


def _extract_docx(path):
    """docx = zip 包，正文在 word/document.xml，按 w:p 分段、取 w:t 文本。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ValueError("docx 解析失败（文件损坏或不是 Word 文档）：%s" % exc)

    paragraphs = []
    for para in re.findall(r"<w:p\b[^>]*>(.*?)</w:p>", xml, re.S):
        runs = re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", para, re.S)
        line = "".join(runs).strip()
        if line:
            paragraphs.append(line)
    text = "\n".join(paragraphs).strip()
    if not text:
        raise ValueError("docx 中没有可提取的文字")
    return text


def _read_text_file(path):
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with io.open(path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("文本解码失败，请存为 UTF-8 后重试")


def build_import_prompt(text):
    """拼装导入提示词：条款在最前（优先级最高），后面是原文与输出要求。"""
    import json

    schema_hint = json.dumps({
        "basics": {"name": "", "phone": "", "email": "", "location": ""},
        "education": [{"school": "", "major": "", "degree": "",
                       "period": "", "note": ""}],
        "projects": [{"title": "", "tag": "", "points": []}],
        "work": [{"org": "", "role": "", "period": "", "points": []}],
        "skills": [{"group": "", "items": ""}],
        "extras": {"research": [], "awards": "", "certificates": ""},
    }, ensure_ascii=False, indent=2)

    return (
        IMPORT_CLAUSE
        + "\n\n---\n\n"
        + "下面是简历原文。请按上面的红线把它抽取成指定 JSON 结构：\n"
        + "只输出 JSON，不要任何解释；找不到的一律留空字符串或空数组。\n\n"
        + "【目标结构】\n" + schema_hint + "\n\n"
        + "【简历原文】\n" + text
    )


def _walk_strings(node, path, out):
    """收集所有叶子字符串，带上便于用户定位的路径。"""
    if isinstance(node, str):
        if node.strip():
            out.append((path, node))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_strings(item, "%s[%d]" % (path, i), out)
    elif isinstance(node, dict):
        for key, value in node.items():
            _walk_strings(value, ("%s.%s" % (path, key)).lstrip("."), out)


def traceable_issues(text, data):
    """可溯源校验：字段值必须能在原文里找到，数字必须来自原文。

    返回问题列表（每项是可直接展示给用户的人话），空列表表示全部可溯源。
    这是「导入=抽取而非生成」这条红线的执行者。
    """
    issues = []
    source = normalize(text)
    source_numbers = _NUMBER_RE.findall(normalize(text))

    leaves = []
    _walk_strings(data, "", leaves)

    for path, value in leaves:
        norm_value = normalize(value)
        if not norm_value:
            continue
        if norm_value in source:
            # 值本身可溯源，再单独核对数字（"效率提升 30%" 这种局部改写）
            for num in _NUMBER_RE.findall(norm_value):
                if num not in source_numbers:
                    issues.append(
                        "%s：数字「%s」在简历原文中找不到（疑似改写，请核对）"
                        % (path, num))
                    break
            continue
        issues.append(
            "%s：「%s」未在简历原文中找到（疑似模型补全，请核对原文后修改或清空）"
            % (path, value[:40]))

    return issues


def unfilled_fields(data):
    """列出未抽取到的关键字段，供核对页标黄提示（留空是合规的，只是要提醒）。"""
    required = [
        ("basics.name", "姓名"),
        ("basics.phone", "电话"),
        ("basics.email", "邮箱"),
    ]
    basics = (data or {}).get("basics") or {}
    missing = []
    for key, label in required:
        if not (basics.get(key.split(".")[-1]) or "").strip():
            missing.append(label)
    # 结构类字段一条都没有也要提醒
    for key, label in (("education", "教育经历"), ("projects", "项目经历"),
                       ("work", "实习/工作经历")):
        if not (data or {}).get(key):
            missing.append(label)
    return missing


def save_upload(upload_bytes, filename, tmp_dir):
    """把上传内容落到临时目录（不进工作区），返回 (路径, 扩展名)。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("不支持的文件类型：%s（支持 %s）"
                         % (ext or "（无扩展名）", "/".join(sorted(ALLOWED_EXT))))
    if len(upload_bytes) > MAX_BYTES:
        raise ValueError("文件超过 %d MB，请先压缩或换文本版" % (MAX_BYTES // 1024 // 1024))

    if not os.path.isdir(tmp_dir):
        os.makedirs(tmp_dir)
    path = os.path.join(tmp_dir, "upload_%d%s" % (os.getpid(), ext))
    with open(path, "wb") as f:
        f.write(upload_bytes)
    return path, ext
