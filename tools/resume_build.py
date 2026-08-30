# -*- coding: utf-8 -*-
"""简历 PDF 生成与 ATS 校验。

取代旧的 build_resume_pdf.ps1（已移入 99_归档/）。沿用其 Chrome/Edge 探测路径与
HTML→PDF 映射，把 PDF 生成与校验合并为一条流水线，使 /apply 能自动调用。

当前基线为 v1.2 色块版：由 02_简历工坊/pdf/resume_*.html 生成。

用法：
    python tools/resume_build.py                       # 生成两版并校验
    python tools/resume_build.py --version hvac        # 只生成 HVAC 版
    python tools/resume_build.py --out 某目录           # 指定输出目录
    python tools/resume_build.py --no-verify           # 只生成不校验

ATS 校验三项，全部通过才算成功：
    1. PDF 页数为 1
    2. pypdf 可提取文本，且长度 >= 800 字符
    3. 若 config/ats_required_facts.txt 存在，逐行检查其关键词是否出现在文本中
       该文件不存在时跳过第三项并提示，不视为失败

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import io
import os
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

# 由 main() 在解析 --workspace 后赋值
VERIFY_FACTS_FILE = ""


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
        # Chrome 会向 stderr 输出无关噪音，捕获但不据此判失败
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
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


def verify_pdf(pdf_path, min_text_length=MIN_TEXT_LENGTH):
    """返回 (是否通过, 明细列表)。"""
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

    facts = load_required_facts(VERIFY_FACTS_FILE)
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
    parser = argparse.ArgumentParser(description="生成简历 PDF 并做 ATS 校验")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    parser.add_argument("--version", default="all",
                        help="只生成指定的版本（resume_<版本>.html 的版本名），默认全部")
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
