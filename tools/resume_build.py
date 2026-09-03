# -*- coding: utf-8 -*-
"""简历 PDF 生成与 ATS 校验。

取代旧的 build_resume_pdf.ps1（已移入 99_归档/）。沿用其 Chrome/Edge 探测路径与
HTML→PDF 映射，把 PDF 生成与校验合并为一条流水线，使 /apply 能自动调用。

两条路径并存：
- 高级模板（手写 HTML，如 personal 的 v1.2 色彩精排版）：
      python tools/resume_build.py --version hvac        # 无子命令，直接打 resume_hvac.html
- 标准版式（数据驱动，JSON + 内置模板，面向普通用户）：
      python tools/resume_build.py render --version hvac # 读 source/resume_hvac.json 渲染

用法：
    python tools/resume_build.py                       # 生成所有手写 HTML 版并校验
    python tools/resume_build.py --version hvac        # 只生成 HVAC 手写 HTML 版
    python tools/resume_build.py --out 某目录           # 指定输出目录
    python tools/resume_build.py --no-verify           # 只生成不校验
    python tools/resume_build.py render [--version hvac]  # 数据驱动标准版式（略 --version 扫全部）

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

import argparse
import html
import io
import json
import os
import re
import subprocess
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

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

# 标准版式（数据驱动）的内置 HTML 模板，位于仓库根的 template/ 下
# （工具层引 template 样板是本仓库既定约定；渲染时按需读取）。
TEMPLATE_STD = os.path.join(ROOT, "template", "workspace", "02_简历工坊",
                            "templates", "std_resume.html")

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


def load_template():
    with io.open(TEMPLATE_STD, "r", encoding="utf-8") as f:
        return f.read()


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

    try:
        template_html = load_template()
    except Exception as exc:  # noqa: BLE001
        print("错误：读取标准模板失败：%s" % exc)
        return 1

    out_dir = os.path.abspath(args.out) if args.out else os.path.join(workspace, "02_简历工坊", "pdf")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    pdf_dir = os.path.join(workspace, "02_简历工坊", "pdf")
    if not os.path.isdir(pdf_dir):
        os.makedirs(pdf_dir)

    all_passed = True
    for tmp_name, pdf_name, slug in selected:
        json_path = os.path.join(source_dir, "resume_%s.json" % slug)
        pdf_path = os.path.join(out_dir, pdf_name)
        tmp_html = os.path.join(pdf_dir, tmp_name)

        try:
            with io.open(json_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            print("跳过 %s：JSON 解析失败：%s" % (json_path, exc))
            all_passed = False
            continue

        try:
            full_html = render_block(template_html, data)
        except Exception as exc:  # noqa: BLE001
            print("跳过 %s：渲染失败：%s" % (slug, exc))
            all_passed = False
            continue

        with io.open(tmp_html, "w", encoding="utf-8") as f:
            f.write(full_html)

        print("生成（数据驱动）：%s" % pdf_name)
        ok = build_pdf(browser, tmp_html, pdf_path)
        if not ok:
            print("  失败：PDF 未生成")
            all_passed = False
            continue

        print("  已生成（%.1f KB）" % (os.path.getsize(pdf_path) / 1024.0))
        # render 独有：断言 A4 纸型（模板须显式 @page size:A4）
        a4_ok, a4_msg = check_a4_mediabox(pdf_path)
        print("  纸型：%s [%s]" % (a4_msg, "通过" if a4_ok else "不通过"))
        if not a4_ok:
            all_passed = False

        if args.no_verify:
            continue
        passed, details = verify_pdf(pdf_path, args.min_text_length)
        print("  ATS 校验：")
        for label, value, ok in details:
            if ok is None:
                print("    - %s：%s" % (label, value))
            else:
                print("    - %s：%s  [%s]" % (label, value, "通过" if ok else "不通过"))
        if not passed:
            all_passed = False
        print("")

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


def main():
    parser = argparse.ArgumentParser(
        description="生成简历 PDF 并做 ATS 校验。子命令 render 走数据驱动标准版式；"
                    "无子命令时打手写 HTML（高级模板）。")
    parser.add_argument("command", nargs="?", default=None,
                        help="render：数据驱动标准版式；省略走手写 HTML")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    parser.add_argument("--version", default="all",
                        help="只生成指定版本（手写 resume_<版本>.html / 数据 resume_<版本>.json），默认全部")
    parser.add_argument("--out", help="输出目录，默认工作区下 02_简历工坊/pdf")
    parser.add_argument("--no-verify", action="store_true", help="只生成，不做 ATS 校验")
    parser.add_argument("--min-text-length", type=int, default=MIN_TEXT_LENGTH,
                        help="可提取文本的最少字符数，默认 %d" % MIN_TEXT_LENGTH)
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    if not os.path.isdir(workspace):
        print("错误：工作区不存在 %s" % workspace)
        print("先运行 python tools/init_workspace.py 初始化。")
        return 1

    # 数据驱动子命令
    if args.command == "render":
        browser = find_browser()
        if not browser:
            print("错误：未找到 Chrome 或 Edge，无法生成 PDF。")
            return 1
        return cmd_render(args, browser,
                          os.path.join(workspace, "config", "ats_required_facts.txt"))
    if args.command is not None:
        print("错误：未知子命令 `%s`。可用子命令：render（省略则打手写 HTML）。" % args.command)
        return 1

    pdf_dir = os.path.join(workspace, "02_简历工坊", "pdf")
    out_dir = os.path.abspath(args.out) if args.out else pdf_dir
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    global VERIFY_FACTS_FILE
    VERIFY_FACTS_FILE = os.path.join(workspace, "config", "ats_required_facts.txt")

    all_jobs = discover_jobs(pdf_dir)
    if not all_jobs:
        print("错误：%s 下没有找到 resume_*.html 简历模板" % pdf_dir)
        print("")
        print("新建一份的步骤：")
        print("  1. 复制 template/workspace/02_简历工坊/pdf/_模板_resume.html")
        print("     到本工作区的 02_简历工坊/pdf/ 下")
        print("  2. 重命名为 resume_<版本>.html，例如 resume_backend.html")
        print("  3. 按文件内的注释说明填写内容")
        print("")
        print("脚本按 resume_ 前缀扫描，一个版本对应一个 HTML 文件。")
        return 1

    if args.version == "all":
        selected = all_jobs
    else:
        selected = [j for j in all_jobs if j[2] == args.version]
        if not selected:
            print("错误：找不到版本 `%s`" % args.version)
            print("可用版本：%s" % "、".join(j[2] for j in all_jobs))
            return 1

    browser = find_browser()
    if not browser:
        print("错误：未找到 Chrome 或 Edge，无法生成 PDF。")
        return 1

    all_passed = True
    last_details = []
    for html_name, pdf_name, _ in selected:
        html_path = os.path.join(pdf_dir, html_name)
        pdf_path = os.path.join(out_dir, pdf_name)

        if not os.path.isfile(html_path):
            print("跳过（HTML 不存在）：%s" % html_name)
            continue

        print("生成：%s" % pdf_name)
        ok = build_pdf(browser, html_path, pdf_path)
        if not ok:
            print("  失败：PDF 未生成")
            all_passed = False
            continue

        size_kb = os.path.getsize(pdf_path) / 1024.0
        print("  已生成（%.1f KB）" % size_kb)

        if args.no_verify:
            continue

        passed, details = verify_pdf(pdf_path, args.min_text_length)
        last_details = details
        print("  ATS 校验：")
        for label, value, ok in details:
            if ok is None:
                print("    - %s：%s" % (label, value))
            else:
                print("    - %s：%s  [%s]" % (label, value, "通过" if ok else "不通过"))
        if not passed:
            all_passed = False
        print("")

    if not args.no_verify and not all_passed:
        print("## ATS 校验未全部通过，不要归档投递。")
        print("")
        # 按失败项给出针对性指引。若只有超页才谈删减，
        # 对「文本太少」谈删减是反向误导。
        failed = [label for label, _, ok in last_details if ok is False]
        if "页数" in failed:
            print("**页数超过 1 页**，删除原则：先删装饰性内容，绝不删核心成果与可验证数字。")
            print("具体顺序见工作区 AGENTS.md 的自定义红线；未记录时，按「装饰信息 →")
            print("次要课程/证书 → 排版留白 → 展开的细节描述」的顺序处理。")
        elif "可提取文本" in failed:
            print("**可提取文本不足**：PDF 文本层内容少于 %d 字符，ATS 可能抓不到内容。"
                  % MIN_TEXT_LENGTH)
            print("这与删减无关，方向相反——应检查：")
            print("  1. 简历内容是否过少（信息量不足，需补充经历与成果）")
            print("  2. HTML 是否用了背景图或 canvas 呈现文字（应改为真实文本）")
            print("  3. 字体是否未嵌入导致提取异常（中文字体需可用）")
        if "关键事实" in failed:
            print("**关键事实缺失**：检查简历是否删掉了核心成果，")
            print("或 config/ats_required_facts.txt 中列出的项本就不在简历里。")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
