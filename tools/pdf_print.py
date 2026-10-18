# -*- coding: utf-8 -*-
"""把 HTML 打成 PDF：浏览器探测 + 调 Chrome/Edge 命令行。

**全仓唯一的 subprocess 落点**（2026-10-16 从 `resume_build.py` 拆出）。
拆的理由有两条，第二条才是主因：

1. `resume_build.py` 已在规模水位上，「怎么调浏览器」与「简历怎么渲染」是两件事；
2. **命令行纪律要能一眼看全**——CodeQL `py/command-line-injection`（#194）指出的
   正是「命令行依赖用户提供的值」。这里把纪律写死成三条：

   - **可执行文件只能来自 `BROWSER_CANDIDATES`**：`allowlisted_browser()` 比较之后
     返回的是常量表里的**字面量**，不是调用方传来的字符串——即使调用方（或将来某个
     配置项）传了别的路径，也进不了 argv。这就是 CodeQL 建议的「在硬编码字面量里
     选一个」，而不是「把用户输入洗一洗再用」；
   - **输入/输出都用临时固定名**：HTML 与 PDF 先落在 `tempfile.mkdtemp()` 里，
     文件名是 `resume.html` / `resume.pdf`；生成后把 PDF 搬到调用方指定路径。
     用户可控的路径（`--out`、工作区位置、版本名）只走**文件系统 API**，不进命令行；
   - **`shell=False` + argv 列表**：不接受字符串形式的命令行，没有 shell 参与。

输入 HTML 会被复制一份到临时目录：这几 KB 换来的是「argv 里没有任何用户可控字符串」。
"""

from __future__ import print_function

import os
import shutil
import subprocess
import tempfile

from jobws_core.workspace_io import TMP_PREFIX  # 临时目录前缀（残留可被识别）

# 浏览器候选：**硬编码字面量**是本条纪律的锚点，不要改成「从配置/环境变量读」。
BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 临时目录里的固定文件名（不带任何用户输入）。
_STAGED_HTML = "resume.html"
_STAGED_PDF = "resume.pdf"

# Chrome 打印超时（秒）。
TIMEOUT_SECONDS = 120


def find_browser():
    """按候选表顺序找第一个存在的浏览器；都没有返回 None。"""
    for path in BROWSER_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def allowlisted_browser(browser):
    """把入参**映射回候选表里的字面量**；不在表内返回 None。

    返回的是 `BROWSER_CANDIDATES` 的元素本身（同一对象），而不是调用方传进来的
    字符串——这样送进 argv 的第一个参数是编译期常量，与调用方输入无关。
    """
    if not browser:
        return None
    want = os.path.normcase(os.path.abspath(browser))
    for candidate in BROWSER_CANDIDATES:
        if os.path.normcase(os.path.abspath(candidate)) == want \
                and os.path.isfile(candidate):
            return candidate
    return None


def build_pdf(browser, html_path, pdf_path):
    """用浏览器把 `html_path` 打成 `pdf_path`；成功返回 True。

    `browser` 必须先通过 `allowlisted_browser`——不通过就直接返回 False 且
    **不启动任何子进程**（没有命令行，就没有命令行注入）。
    """
    exe = allowlisted_browser(browser)
    if exe is None:
        return False
    work = tempfile.mkdtemp(prefix=TMP_PREFIX)
    try:
        staged_html = os.path.join(work, _STAGED_HTML)
        staged_pdf = os.path.join(work, _STAGED_PDF)
        shutil.copyfile(html_path, staged_html)
        cmd = [
            exe,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=4000",
            "--print-to-pdf=%s" % staged_pdf,
            staged_html,
        ]
        try:
            # Chrome 会向 stderr 输出无关噪音，丢弃而非捕获——Windows 下读它的
            # stdout/stderr 会用 locale 编码(GBK)解码，Chrome 的非 GBK 输出会导致
            # 后台线程 UnicodeDecodeError。只以 PDF 是否生成判成败。
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False
        if not os.path.isfile(staged_pdf):
            return False
        shutil.move(staged_pdf, pdf_path)
        return os.path.isfile(pdf_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
