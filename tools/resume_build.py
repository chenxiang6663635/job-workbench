# -*- coding: utf-8 -*-
"""简历 PDF 生成与 ATS 校验。

取代旧的 build_resume_pdf.ps1（已移入 99_归档/）。沿用其 Chrome/Edge 探测路径与
HTML→PDF 映射，把 PDF 生成与校验合并为一条流水线，使 /apply 能自动调用。

两条路径并存：
- 高级模板（手写 HTML，如 personal 的 v1.2 色彩精排版）：
      python tools/jobws.py resume --version hvac        # 无子命令，直接打 resume_hvac.html
- 标准版式（数据驱动，JSON + 内置模板，面向普通用户）：
      python tools/jobws.py resume render --version hvac # 读 source/resume_hvac.json 渲染

用法（命令行在 tools/_cli_resume.py；唯一入口）：
    python tools/jobws.py resume                       # 生成所有手写 HTML 版并校验
    python tools/jobws.py resume --version hvac        # 只生成 HVAC 手写 HTML 版
    python tools/jobws.py resume --out 某目录           # 指定输出目录
    python tools/jobws.py resume --no-verify           # 只生成不校验
    python tools/jobws.py resume render [--version hvac]  # 数据驱动标准版式（略 --version 扫全部）

ATS 校验三项，全部通过才算成功：
    1. PDF 页数为 1
    2. pypdf 可提取文本，且长度 >= 阈值（默认 300）
    3. 若 config/ats_required_facts.txt 存在，逐行检查其关键词是否出现在文本中
       该文件不存在时跳过第三项并提示，不视为失败

render 子命令额外校验 mediabox 为 A4：数据模板必须显式声明 @page size:A4，
否则 Chrome 默认 Letter(612×792) 会破坏一页判定（实测无 @page = Letter）。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import html
import io
import json
import os
import re
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORKSPACE = os.path.join(ROOT, "personal")

BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 可提取文本的字符数下限。
#
# 目的不是评判「简历内容够不够丰富」，而是检测 PDF 文本层是否可正常提取
# （图片型 PDF、空白 PDF、字体未嵌入等异常）。因此阈值应设在「明显异常」
# 与「正常但简短」之间，而不是按内容密度设定。
#
# 实测参照：空白或仅标题的 PDF 约 0–50 字符；内容正常的中英文一页简历
# 常见 300–1900 字符。默认取 300：既能捕获文本层异常，又不误判正常简历。
#
# 阈值曾设为 800（从单一用户的密集简历倒推），实测会误判内容正常但偏简的
# 中文简历，故下调并改为可配置。
MIN_TEXT_LENGTH = 300

# 标准版式（数据驱动）的模板目录（批 4.5）：每个 *.html 即一套版式——
# 版式共享同一套占位符契约（tests/test_resume_templates.py 锁定），差异只在
# 密度与强调层（对 RenderCV「主题只改默认值、底层模板同一套」结论的落地）：
# 新增版式 = 新增一个 HTML 文件，零代码改动。
TEMPLATES_DIR = os.path.join(ROOT, "template", "workspace", "02_简历工坊",
                             "templates")
DEFAULT_TEMPLATE = "std_resume"

# 简历强调色（风格轴，与版式正交）：预设名 → #hex。--resume-accent 与偏好
# resume_style 都接受「预设名」或任意 #hex；改色只改模板里的 --resume-accent。
RESUME_ACCENTS = {
    "石墨灰": "#3f4650",
    "商务蓝": "#2c5f8d",
    "深墨绿": "#1f5c4a",
    "酒红": "#7a2e3a",
}

# 由 main() 在解析 --workspace 后赋值
VERIFY_FACTS_FILE = ""

# A4 与 Letter 的 mediabox 上下界（pt）。Chrome headless 默认 Letter 612×792，
# 只有模板显式 @page{size:A4} 才产出 A4(约 594.96×841.92)。
A4_WIDTH_MAX = 596.0
A4_HEIGHT_MIN = 840.0
A4_HEIGHT_MAX = 844.0


def esc(value):
    """HTML 转义，防止简历内容里的 < > & 破坏结构。"""
    return html.escape(value if value is not None else "")


def _template_id_ok(template_id):
    """版式名白名单：与 routers/resume.py 的版本名同一约定（拒绝路径穿越）。"""
    return bool(re.match(r"^[A-Za-z0-9_-]+$", template_id or ""))


def list_templates():
    """扫描模板目录，返回可用版式 id 列表（排序）。"""
    if not os.path.isdir(TEMPLATES_DIR):
        return []
    return sorted(name[:-len(".html")] for name in os.listdir(TEMPLATES_DIR)
                  if name.lower().endswith(".html"))


def load_template(template_id=None):
    """读取指定版式的 HTML；template_id 缺省用 DEFAULT_TEMPLATE。

    版式名经白名单校验；找不到时抛 ValueError，消息里列出可用版式——
    调用方（CLI 与 routers/resume.py）原样打印即可。
    """
    tid = (template_id or DEFAULT_TEMPLATE).strip()
    if not _template_id_ok(tid):
        raise ValueError("版式名 `%s` 不合法（只允许字母、数字、-、_）" % template_id)
    path = os.path.join(TEMPLATES_DIR, tid + ".html")
    if not os.path.isfile(path):
        available = list_templates()
        raise ValueError("找不到版式 `%s`。可用版式：%s"
                         % (tid, "、".join(available) if available else "（模板目录为空）"))
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def resolve_accent(value):
    """把「预设名 / #hex / 空」解析为合法的 CSS 颜色串；非法返回 None。

    空值返回 None 表示「不覆盖」（保留模板默认色）。
    """
    text = (value or "").strip()
    if not text:
        return None
    if text in RESUME_ACCENTS:
        return RESUME_ACCENTS[text]
    if re.match(r"^#[0-9a-fA-F]{3,8}$", text):
        return text
    return None


def apply_accent(template_html, accent):
    """把模板里的 --resume-accent 变量替换为指定颜色；accent 为 None 时原样返回。"""
    if not accent:
        return template_html
    return re.sub(r"--resume-accent\s*:\s*[^;]+;",
                  "--resume-accent: %s;" % accent, template_html)


def render_block(template_html, data):
    """把 JSON 数据填充进模板的占位符。

    JSON Resume 精简子集 + 逐区块 HTML 字符串拼接。这里分两步：
    profile/education 等复杂区块用 {{name}} 占位符替换为已拼好的 HTML，
    简单标量用 {{basics.name}} 直接替换。
    """
    out = template_html
    basics = data.get("basics") or {}
    for key in ("name", "phone", "email", "location"):
        out = out.replace("{{basics.%s}}" % key, esc(basics.get(key, "")))

    # 求职意向
    intent = (data.get("meta") or {}).get("intent", "")
    out = out.replace("{{intent_block}}",
                      '<div class="intent">%s</div>' % esc(intent) if intent else "")
    # 联系方式分隔符
    parts = [p for p in [
        (data.get("basics") or {}).get("phone", ""),
        (data.get("basics") or {}).get("email", ""),
    ] if p]
    out = out.replace("{{contact_sep}}", " ｜ " if parts and parts[0] else "")
    out = out.replace("{{contact_sep2}}",
                      " ｜ " if (data.get("basics") or {}).get("location") and parts else "")
    out = out.replace("{{basics.location}}",
                      esc((data.get("basics") or {}).get("location", "")))

    # profile
    profile = (data.get("meta") or {}).get("profile", "")
    out = out.replace("{{profile_block}}",
                      _profile_block(profile) if profile else "")

    # 教育
    out = out.replace("{{education_block}}",
                      _education_block(data.get("education", [])))
    # 项目
    out = out.replace("{{projects_block}}",
                      _projects_block(data.get("projects", [])))
    # 实习/工作
    out = out.replace("{{work_block}}",
                      _work_block(data.get("work", [])))
    # 技能
    out = out.replace("{{skills_block}}",
                      _skills_block(data.get("skills", [])))
    # 额外（科研成果/奖项/证书）
    out = out.replace("{{extras_block}}",
                      _extras_block(data.get("extras") or {}))
    # 兜底：清掉任何未替换的占位符。残留的 {{xxx}} 会原样进 PDF 文本层被
    # ATS 抓到，比留空更糟。模板新增区块而此处漏替换时也不会污染输出。
    out = re.sub(r"\{\{\s*[\w.]+\s*\}\}", "", out)
    return out


def _profile_block(profile):
    return '<h2>专业概况</h2><p class="profile">%s</p>' % esc(profile)


def _education_block(educations):
    if not educations:
        return ""
    items = []
    for e in educations:
        head = '<span>%s</span>' % esc(e.get("school", ""))
        if e.get("major") or e.get("degree"):
            head = '<span>%s · %s%s</span>' % (
                esc(e.get("school", "")),
                esc(e.get("major", "")),
                (" · " + esc(e.get("degree", ""))) if e.get("degree") else "")
        item = '<div class="item"><div class="item-head">%s<span class="period">%s</span></div>' % (
            head, esc(e.get("period", "")))
        if e.get("note"):
            item += '<div class="meta">%s</div>' % esc(e.get("note"))
        item += "</div>"
        items.append(item)
    return '<h2>教育经历</h2>' + "".join(items)


def _projects_block(projects):
    if not projects:
        return ""
    items = []
    for p in projects:
        head = '<h3><span>%s</span>%s</h3>' % (
            esc(p.get("title", "")),
            (' <span class="role">%s</span>' % esc(p.get("tag", ""))) if p.get("tag") else "")
        lis = "".join('<li>%s</li>' % esc(x) for x in p.get("points", []))
        items.append('<div class="item">%s<ul>%s</ul></div>' % (head, lis))
    return '<h2>项目经历</h2>' + "".join(items)


def _work_block(works):
    if not works:
        return ""
    items = []
    for w in works:
        head = '<div class="item-head"><span>%s%s</span><span class="period">%s</span></div>' % (
            esc(w.get("org", "")),
            (" · " + esc(w.get("role", ""))) if w.get("role") else "",
            esc(w.get("period", "")))
        lis = "".join('<li>%s</li>' % esc(x) for x in w.get("points", []))
        items.append('<div class="item">%s<ul>%s</ul></div>' % (head, lis))
    return '<h2>实习经历</h2>' + "".join(items)


def _skills_block(skills):
    if not skills:
        return ""
    rows = []
    for s in skills:
        rows.append('<div><span class="label">%s：</span>%s</div>' % (
            esc(s.get("group", "")), esc(s.get("items", ""))))
    return '<h2>专业技能</h2><div class="skills">%s</div>' % "".join(rows)


def _extras_block(extras):
    out = ""
    research = extras.get("research", [])
    if research:
        lis = "".join('<li>%s</li>' % esc(x) for x in research)
        out += '<h2>科研成果</h2><ul>%s</ul>' % lis
    sections = []
    if extras.get("awards"):
        sections.append('<div><span class="label">奖项：</span>%s</div>' % esc(extras.get("awards")))
    if extras.get("certificates"):
        sections.append('<div><span class="label">证书：</span>%s</div>' % esc(extras.get("certificates")))
    if sections:
        out += '<h2>奖项 / 证书</h2><div class="awards">%s</div>' % "".join(sections)
    return out


def discover_source_json(source_dir):
    """扫描 source/ 下的 resume_*.json，返回 [(html暂存名, pdf名, slug)]。"""
    if not os.path.isdir(source_dir):
        return []
    jobs = []
    for name in sorted(os.listdir(source_dir)):
        if name.startswith("resume_") and name.endswith(".json"):
            stem = name[len("resume_"):-len(".json")]
            jobs.append(("__std_%s.html" % stem, "简历_%s.pdf" % stem, stem))
    return jobs


def check_a4_mediabox(pdf_path):
    """render 子命令独有：断言第一页为 A4，避免模板漏 @page 导致 Letter。"""
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf_path)
        mb = r.pages[0].mediabox
        w, h = float(mb.width), float(mb.height)
    except Exception:  # noqa: BLE001
        return False, "无法读取 PDF 纸型（可能未安装 pypdf 或文件损坏）"
    if w <= A4_WIDTH_MAX and A4_HEIGHT_MIN <= h <= A4_HEIGHT_MAX:
        return True, "A4（%.1f×%.1fpt）" % (w, h)
    return False, "非 A4（%.1f×%.1fpt）——模板可能漏了 @page{size:A4}，Chrome 默认 Letter" % (w, h)


def _resolve_render_accent(args, workspace):
    """风格轴（批 4.5）：--resume-accent 优先，缺省回落工作区偏好 resume_style。

    该 key 一直存在（prefs 的 KNOWN_KEYS），批 4.5 起成为真实消费方。两者都
    接受预设名或 #hex；非法值明确报错而不是静默忽略。返回 (accent, 来源描述)；
    非法时打印错误并返回 (None, None)。
    """
    accent_choice = getattr(args, "resume_accent", None)
    accent_source = "--resume-accent"
    if not accent_choice:
        try:
            import prefs as prefs_mod
            accent_choice = (prefs_mod.read_prefs(workspace).get("resume_style") or "")
            accent_source = "偏好 resume_style"
        except Exception:  # noqa: BLE001 - 偏好读取失败不应挡住生成
            accent_choice = ""
    accent = resolve_accent(accent_choice)
    if accent_choice and not accent:
        print("错误：风格 `%s` 无法识别。可用预设：%s；或直接给 #hex 颜色（如 #3f4650）。"
              % (accent_choice, " / ".join(RESUME_ACCENTS)))
        return None, None
    return accent, accent_source


def _render_one(job, ctx):
    """渲染单份简历：JSON → HTML → PDF → A4 纸型与 ATS 校验。返回是否通过。"""
    tmp_name, pdf_name, slug = job
    json_path = os.path.join(ctx["source_dir"], "resume_%s.json" % slug)
    pdf_path = os.path.join(ctx["out_dir"], pdf_name)
    tmp_html = os.path.join(ctx["pdf_dir"], tmp_name)

    try:
        with io.open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print("跳过 %s：JSON 解析失败：%s" % (json_path, exc))
        return False

    try:
        full_html = render_block(ctx["template_html"], data)
    except Exception as exc:  # noqa: BLE001
        print("跳过 %s：渲染失败：%s" % (slug, exc))
        return False

    with io.open(tmp_html, "w", encoding="utf-8") as f:
        f.write(full_html)

    print("生成（数据驱动）：%s" % pdf_name)
    if not build_pdf(ctx["browser"], tmp_html, pdf_path):
        print("  失败：PDF 未生成")
        return False

    print("  已生成（%.1f KB）" % (os.path.getsize(pdf_path) / 1024.0))
    ok = True
    # render 独有：断言 A4 纸型（模板须显式 @page size:A4）
    a4_ok, a4_msg = check_a4_mediabox(pdf_path)
    print("  纸型：%s [%s]" % (a4_msg, "通过" if a4_ok else "不通过"))
    if not a4_ok:
        ok = False

    if ctx["args"].no_verify:
        return ok
    passed, details = verify_pdf(pdf_path, ctx["args"].min_text_length)
    print("  ATS 校验：")
    for label, value, flag in details:
        if flag is None:
            print("    - %s：%s" % (label, value))
        else:
            print("    - %s：%s  [%s]" % (label, value, "通过" if flag else "不通过"))
    if not passed:
        ok = False
    print("")
    return ok


def cmd_render(args, browser, verify_facts):
    """数据驱动渲染：JSON → 内置模板 → 临时 HTML → 打印 → 校验。"""
    global VERIFY_FACTS_FILE
    VERIFY_FACTS_FILE = verify_facts
    workspace = os.path.abspath(args.workspace)
    if not os.path.isdir(workspace):
        print("错误：工作区不存在 %s" % workspace)
        return 1

    source_dir = os.path.join(workspace, "02_简历工坊", "source")
    jobs = discover_source_json(source_dir)
    if not jobs:
        print("错误：%s 下没有找到 resume_*.json 简历数据" % source_dir)
        print("先在 02_简历工坊/source/ 放一份 resume_<版本>.json，见 template 同名目录。")
        return 1

    if args.version and args.version != "all":
        selected = [j for j in jobs if j[2] == args.version]
        if not selected:
            print("错误：找不到版本 `%s`" % args.version)
            print("可用版本：%s" % "、".join(j[2] for j in jobs))
            return 1
    else:
        selected = jobs

    accent, accent_source = _resolve_render_accent(args, workspace)
    if accent_source is None:
        return 1

    try:
        template_html = load_template(getattr(args, "template", None))
    except Exception as exc:  # noqa: BLE001
        print("错误：读取标准模板失败：%s" % exc)
        return 1
    template_html = apply_accent(template_html, accent)
    print("版式：%s；风格：%s" % (
        getattr(args, "template", None) or DEFAULT_TEMPLATE,
        ("%s（%s）" % (accent, accent_source)) if accent else "模板默认"))

    out_dir = os.path.abspath(args.out) if args.out else os.path.join(workspace, "02_简历工坊", "pdf")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    pdf_dir = os.path.join(workspace, "02_简历工坊", "pdf")
    if not os.path.isdir(pdf_dir):
        os.makedirs(pdf_dir)

    ctx = {"source_dir": source_dir, "out_dir": out_dir, "pdf_dir": pdf_dir,
           "template_html": template_html, "browser": browser, "args": args}
    all_passed = True
    for job in selected:
        if not _render_one(job, ctx):
            all_passed = False

    # 清理临时 HTML
    for tmp_name, _, _ in selected:
        tmp_html = os.path.join(pdf_dir, tmp_name)
        if os.path.isfile(tmp_html):
            try:
                os.remove(tmp_html)
            except OSError:
                pass
    if not all_passed:
        print("## 校验未全部通过，不要归档投递。")
        return 1
    return 0


def find_browser():
    for path in BROWSER_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def build_pdf(browser, html_path, pdf_path):
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--virtual-time-budget=4000",
        "--print-to-pdf=%s" % pdf_path,
        html_path,
    ]
    try:
        # Chrome 会向 stderr 输出无关噪音，丢弃而非捕获——Windows 下读它的
        # stdout/stderr 会用 locale 编码(GBK)解码，Chrome 的非 GBK 输出会导致
        # 后台线程 UnicodeDecodeError。只以 PDF 是否生成判成败。
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=120)
    except subprocess.TimeoutExpired:
        return False
    return os.path.isfile(pdf_path)


def discover_jobs(pdf_dir):
    """扫描 pdf 目录下的 resume_*.html。

    不硬编码文件名——不同用户的简历版本命名不同，脚本只约定前缀 resume_。
    输出名由 HTML 名推导：resume_hvac.html -> 简历_hvac.pdf，
    若同目录已存在同名 PDF 则沿用它（保持历史版本命名）。
    """
    if not os.path.isdir(pdf_dir):
        return []
    jobs = []
    for name in sorted(os.listdir(pdf_dir)):
        if name.startswith("resume_") and name.lower().endswith(".html"):
            stem = name[len("resume_"):-len(".html")]
            pdf = "简历_%s.pdf" % stem
            jobs.append((name, pdf, stem))
    return jobs


def load_required_facts(facts_file):
    if not os.path.isfile(facts_file):
        return None
    facts = []
    with io.open(facts_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                facts.append(line)
    return facts


def verify_pdf(pdf_path, min_text_length=MIN_TEXT_LENGTH, facts_file=None):
    """返回 (是否通过, 明细列表)。

    facts_file 显式传入优先，缺省回退模块级 VERIFY_FACTS_FILE。
    Web 并发场景必须显式传：模块级全局在并发请求下会互相覆盖。
    """
    details = []
    try:
        from pypdf import PdfReader
    except ImportError:
        return False, ["未安装 pypdf，无法校验"]

    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:  # noqa: BLE001 - 向用户报告具体错误比崩溃更有用
        return False, ["PDF 解析失败：%s" % exc]

    pages = len(reader.pages)
    ok_pages = pages == 1
    details.append(("页数", "1 页" if ok_pages else "%d 页" % pages, ok_pages))

    text = ""
    for page in reader.pages:
        try:
            text += page.extract_text() or ""
        except Exception:  # noqa: BLE001 - 单页提取失败不应中断整体校验
            pass
    text = text.strip()

    ok_text = len(text) >= min_text_length
    details.append(("可提取文本", "%d 字符（阈值 %d）" % (len(text), min_text_length), ok_text))

    facts = load_required_facts(facts_file or VERIFY_FACTS_FILE)
    if facts is None:
        details.append(("关键事实", "跳过：config/ats_required_facts.txt 不存在", None))
    else:
        missing = [f for f in facts if f not in text]
        if missing:
            details.append(("关键事实", "缺 %d 项：%s" % (len(missing), "、".join(missing)), False))
        else:
            details.append(("关键事实", "%d 项全部命中" % len(facts), True))

    passed = all(ok for _, _, ok in details if ok is not None)
    return passed, details

if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py resume ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
