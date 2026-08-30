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
PDF_DIR = os.path.join(ROOT, "02_简历工坊", "pdf")
FACTS_FILE = os.path.join(ROOT, "config", "ats_required_facts.txt")

# HTML 源 -> 输出 PDF 文件名（v1.2 色块版为当前基线）
JOBS = [
    ("resume_hvac.html", "某用户_简历_空调制冷HVAC_v1.2色块版.pdf", "hvac"),
    ("resume_datacenter.html", "某用户_简历_数据中心冷却_v1.2色块版.pdf", "datacenter"),
]

BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

MIN_TEXT_LENGTH = 800


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


def load_required_facts():
    if not os.path.isfile(FACTS_FILE):
        return None
    facts = []
    with io.open(FACTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                facts.append(line)
    return facts


def verify_pdf(pdf_path):
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

    ok_text = len(text) >= MIN_TEXT_LENGTH
    details.append(("可提取文本", "%d 字符（阈值 %d）" % (len(text), MIN_TEXT_LENGTH), ok_text))

    facts = load_required_facts()
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
    parser.add_argument("--version", choices=["hvac", "datacenter", "all"], default="all",
                        help="生成哪一版，默认两版都生成")
    parser.add_argument("--out", help="输出目录，默认为 02_简历工坊/pdf")
    parser.add_argument("--no-verify", action="store_true", help="只生成，不做 ATS 校验")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out) if args.out else PDF_DIR
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    browser = find_browser()
    if not browser:
        print("错误：未找到 Chrome 或 Edge，无法生成 PDF。")
        return 1

    selected = [j for j in JOBS if args.version == "all" or j[2] == args.version]

    all_passed = True
    for html_name, pdf_name, _ in selected:
        html_path = os.path.join(PDF_DIR, html_name)
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

        passed, details = verify_pdf(pdf_path)
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
        print("若 PDF 超过一页，按既定顺序删减：驾驶证 -> 本科 GPA/部分课程 -> "
              "Profile 压一行 -> 项目1方法细节 -> 标准栏。")
        print("绝不先删：X% 结果、控制贡献、SCI、硕士课程成绩、工程实践。")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
