# -*- coding: utf-8 -*-
"""`jobws resume` 的命令层：解析参数、调度生成与 ATS 校验。

（2026-09-21 从 `resume_build.py` 拆出：模块此前 717 行、紧贴规模预算；渲染与
校验的领域函数留在 resume_build.py，后端（routers/resume.py）继续直接调用它们。
命令名与参数逐字未变；VERIFY_FACTS_FILE 的模块级赋值一并取消——改为显式传参
（verify_pdf 的注释本就要求 Web 并发场景显式传，CLI 同样照办）。）
退出码：0 成功 / 1 业务失败或环境缺失 / 2 用法错误。
"""

from __future__ import print_function

import argparse
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from resume_build import (DEFAULT_TEMPLATE, DEFAULT_WORKSPACE, MIN_TEXT_LENGTH,  # noqa: E402
                          RESUME_ACCENTS, build_pdf, cmd_render, discover_jobs,
                          find_browser, list_templates, verify_pdf)

def _build_parser():
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
    # 版式与风格（批 4.5，仅 render 使用；省略时给默认值与偏好回退）
    parser.add_argument("--template", default=None,
                        help="render 版式（模板目录下的文件名，缺省 %s；可用：%s）"
                             % (DEFAULT_TEMPLATE,
                                " / ".join(list_templates() or [DEFAULT_TEMPLATE])))
    parser.add_argument("--resume-accent", dest="resume_accent", default=None,
                        help="简历强调色：预设名（%s）或 #hex；缺省读偏好 resume_style"
                             % " / ".join(RESUME_ACCENTS))
    return parser


def _print_no_html_guide(pdf_dir):
    """空态指引：没有 resume_*.html 时告诉用户怎么新建一份。"""
    print("错误：%s 下没有找到 resume_*.html 简历模板" % pdf_dir)
    print("")
    print("新建一份的步骤：")
    print("  1. 复制 template/workspace/02_简历工坊/pdf/_模板_resume.html")
    print("     到本工作区的 02_简历工坊/pdf/ 下")
    print("  2. 重命名为 resume_<版本>.html，例如 resume_backend.html")
    print("  3. 按文件内的注释说明填写内容")
    print("")
    print("脚本按 resume_ 前缀扫描，一个版本对应一个 HTML 文件。")


def _render_manual_html(args, browser, pdf_dir, out_dir, selected, facts_file):
    """手写 HTML 主循环；返回 (all_passed, last_details)。"""
    all_passed = True
    last_details = []
    for html_name, pdf_name, _ in selected:
        html_path = os.path.join(pdf_dir, html_name)
        pdf_path = os.path.join(out_dir, pdf_name)

        if not os.path.isfile(html_path):
            print("跳过（HTML 不存在）：%s" % html_name)
            continue

        print("生成：%s" % pdf_name)
        if not build_pdf(browser, html_path, pdf_path):
            print("  失败：PDF 未生成")
            all_passed = False
            continue

        size_kb = os.path.getsize(pdf_path) / 1024.0
        print("  已生成（%.1f KB）" % size_kb)

        if args.no_verify:
            continue

        passed, details = verify_pdf(pdf_path, args.min_text_length, facts_file)
        last_details = details
        print("  ATS 校验：")
        for label, value, flag in details:
            if flag is None:
                print("    - %s：%s" % (label, value))
            else:
                print("    - %s：%s  [%s]" % (label, value, "通过" if flag else "不通过"))
        if not passed:
            all_passed = False
        print("")
    return all_passed, last_details


def _print_fail_guidance(last_details):
    """按 ATS 失败项给出针对性指引。

    若只有超页才谈删减——对「文本太少」谈删减是反向误导。
    """
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


def main():
    args = _build_parser().parse_args()

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

    facts_file = os.path.join(workspace, "config", "ats_required_facts.txt")

    all_jobs = discover_jobs(pdf_dir)
    if not all_jobs:
        _print_no_html_guide(pdf_dir)
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

    all_passed, last_details = _render_manual_html(args, browser, pdf_dir, out_dir, selected, facts_file)

    if not args.no_verify and not all_passed:
        print("## ATS 校验未全部通过，不要归档投递。")
        print("")
        _print_fail_guidance(last_details)
        return 1

    return 0
if __name__ == "__main__":
    # 入口已统一到 tools/jobws.py：直接运行本文件不再执行功能，
    # 只给一条可复制的迁移命令——不保留旧别名，但也不让人对着静默退出发愣。
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py resume ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
