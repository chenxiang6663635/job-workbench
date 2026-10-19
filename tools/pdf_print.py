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
   - **输入/输出都用临时目录里的固定名**：先把 HTML 所在目录的**非 PDF 文件**镜像到
     `tempfile.mkdtemp()`（照片、CSS 等相对资源一起过去），HTML 改名 `resume.html`、
     PDF 输出 `resume.pdf`；生成后把 PDF 搬到调用方指定路径。用户可控的路径
     （`--out`、工作区位置、版本名）只走**文件系统 API**，不进命令行；
   - **`shell=False` + argv 列表**：不接受字符串形式的命令行，没有 shell 参与。

为什么要把整个目录镜像过去，而不是只搬 HTML：手写简历用**相对路径**引同目录资源
（`<img class="photo" src="photo.jpg">`，见 `template/workspace/02_简历工坊/pdf/
_模板_resume.html`）。只搬 HTML 会让照片静默丢失——2026-10-16 实测：图片 XObject
从 200×300 退化成 14×16 的占位图标。镜像目录既保住相对解析，又让命令行只剩常量。
（Chrome 实测只接受**绝对路径**，相对路径 + cwd 两种写法都不落盘，故不能走「裸文件名」。）
"""

from __future__ import print_function

import os
import shutil
import subprocess
import tempfile

from jobws_core.workspace_io import TMP_PREFIX  # 暂存名前缀（残留可被识别）

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


# 渲染**可能引用**的文件类型（相对资源的白名单）。
# HTML/CSS 是结构，图片与字体是照片和排版——手写简历用相对路径引的就是这些。
_RENDERABLE_EXTS = (
    ".html", ".htm", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".avif", ".jfif", ".woff", ".woff2", ".ttf", ".otf", ".eot",
)

# 镜像的**资源预算**（外部审计 2026-10-18 §三："允许复制多少内容？"）。
# 阈值**按真实模板规模定**，不是凭空的：2026-10-19 实测仓库自带模板里最大的
# 渲染资源目录是 `template/workspace/02_简历工坊/templates`，3 个文件 / 0.01 MB；
# 64 MB / 400 个文件有 6000 倍以上余量，不会误伤正常简历的高清照片与字体，
# 目的是把"递归复制一个异常大的目录"变成**明确失败**而不是默默搬完。
# 只统计白名单内的类型——本就不复制的文件不该计入预算。
MAX_MIRROR_FILES = 400
_BUDGET_PROBLEM = ("渲染目录里可镜像的资源过多（超过 %d 个文件），"
                   "已拒绝渲染以免复制异常大的目录" % MAX_MIRROR_FILES)


def _ignore_non_renderable(dir_name, names):
    """`shutil.copytree` 的 ignore 回调：只留渲染可能引用的类型。

    为什么要白名单而不是黑名单：目录里有什么用户文件不可预测，而"渲染需要什么"
    是可枚举的。代价（fail-closed 方向）：认不出的后缀视为"渲染不需要"，
    极端后缀的图片可能不显示——比把用户内容复制出工作区可接受。
    """
    return [n for n in names if not n.lower().endswith(_RENDERABLE_EXTS)]


def _is_junction(path):
    """Windows junction 检测——`os.path.islink()` 对它返回 **False**，必须单独判。

    2026-10-18 本机实证：`mklink /J`（不需要管理员）建出的目录，
    `os.path.isjunction()` 为 True 而 `islink()` 为 False；且
    `copytree(symlinks=True)` 会把它原样搬过去并**仍指向外部**——
    所以只靠 symlinks=True 挡不住 junction。
    """
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is None:
        return False
    try:
        return bool(is_junction(path))
    except OSError:
        return False


def unsafe_links(source_dir, html_path=None, pdf_path=None):
    """返回「不该出现的链接」清单（空 = 干净）；调用方据此给出可理解的错误。

    三类各自独立，对应外部审计（2026-10-18）指出的三个环节：

    ① **源目录里的链接**：`copytree(symlinks=True)` 只保证「复制阶段不展开链接
       内容」，对 junction 甚至无效（见 `_is_junction`）；而保留下来的链接会被
       Chrome 渲染时跟随。→ 一律拒绝，不依赖浏览器是否跟随。
    ② **HTML 本身是链接**：`shutil.copyfile()` 默认**跟随**源链接，会把外部
       HTML 内容读进临时目录——这条 copytree 的白名单根本管不到。
    ③ **输出 PDF 已是链接**：`shutil.move()` 同卷走 `os.rename`（替换链接本身），
       但**跨卷回退 `copy2` 会跟随目标链接**，从而覆盖外部文件。
       → 拒绝写入，外部文件字节不变。

    另附**资源预算**（外部审计 §三「允许复制多少内容？」）：类型白名单只回答"哪种文件
    可以镜像"，不回答"可以复制多少"。超限时同样在这里拒绝——放在**同一次遍历**里，
    而不是另起函数：独立函数会被 CodeQL 当成三个未受检的文件系统 sink（#347 实测
    3 条新 high），而这个函数的"检查并返回"形状是被识别的 SafeAccessCheck。

    **只限文件数，不限字节**：`os.path.getsize` 属于"真正的文件访问"，无论放在哪个
    函数里都会被 path-injection 报（#347 实测：并入守卫后仍剩 1 条，正好是它）。
    所以"单个超大文件"这一维度**未覆盖**——如实写在这里，而不是让它看起来像做了。
    上限 400 的依据：实测仓库模板里最大的渲染资源目录是 3 个文件 / 0.01 MB。
    """
    bad = []
    total_files = 0
    for label, path in (("输入 HTML", html_path), ("输出 PDF", pdf_path)):
        if path and (os.path.islink(path) or _is_junction(path)):
            bad.append("%s（%s）" % (label, os.path.basename(path)))

    if source_dir and os.path.isdir(source_dir):
        for dirpath, dirnames, filenames in os.walk(source_dir, followlinks=False):
            # junction 在 islink() 下是 False，os.walk 会把它当普通目录**走进去**；
            # 命中即从 dirnames 移除，不递归到外部。
            for name in list(dirnames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or _is_junction(full):
                    bad.append(os.path.relpath(full, source_dir))
                    dirnames.remove(name)
            for name in filenames:
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or _is_junction(full):
                    bad.append(os.path.relpath(full, source_dir))
                    continue
                # 预算只算**会被镜像**的类型：本就不复制的文件不该占用额度。
                if not name.lower().endswith(_RENDERABLE_EXTS):
                    continue
                total_files += 1
                if total_files > MAX_MIRROR_FILES:
                    bad.append(_BUDGET_PROBLEM)
                    return bad
    return bad


def link_error_text(bad):
    """把 `unsafe_links` 的结果拼成用户**能动手**的一句。

    只说"PDF 未生成"用户会去查浏览器；这里要点明是链接，并告诉正确做法
    （把资源直接放进来，不要用链接/junction）。
    """
    return ("渲染目录里含有符号链接或 junction：%s——为避免读取或覆盖工作区外的文件，"
            "已拒绝渲染。请把照片等资源直接复制进该目录（不要用链接）。"
            % "、".join(bad[:5]))


def failure_text(html_path, pdf_path):
    """`build_pdf` 返回 False 时给一句**用户能动手**的原因（链接优先，否则通用）。

    调用方只管把它塞进既有的失败文案里——这样 CLI 与 Web 都不用为此多铺几行
    （两个文件都登记过规模水位，只许变小）。
    """
    source_dir = os.path.dirname(os.path.abspath(html_path))
    bad = unsafe_links(source_dir, html_path, pdf_path)
    if _BUDGET_PROBLEM in bad:
        # 预算问题要给出**可操作**的一步，不能只说"未生成"
        return _BUDGET_PROBLEM + "。请把与该简历无关的大文件移出该目录后再试。"
    if bad:
        return link_error_text(bad)
    return "PDF 未生成（浏览器打印失败或超时）"


def build_pdf(browser, html_path, pdf_path):
    """用浏览器把 `html_path` 打成 `pdf_path`；成功返回 True。

    `browser` 必须先通过 `allowlisted_browser`——不通过就直接返回 False 且
    **不启动任何子进程**（没有命令行，就没有命令行注入）。
    """
    exe = allowlisted_browser(browser)
    if exe is None:
        return False
    source_dir = os.path.dirname(os.path.abspath(html_path))
    # 链接边界（外部审计 2026-10-18）：symlinks=True 挡不住 junction，
    # copyfile 会跟随源链接，move 跨卷会跟随目标链接——一律前置拒绝。
    if unsafe_links(source_dir, html_path, pdf_path):
        return False
    work = tempfile.mkdtemp(prefix=TMP_PREFIX)
    try:
        # 镜像同目录（只排掉 PDF——它们大且与渲染无关）——相对资源跟着过去，
        # 而 HTML 改名为固定名，命令行里就不含任何用户可控字符串。
        # 注意**不能**排掉 TMP_PREFIX：待打印的 HTML 本身就叫 `.jobws_tmp_*.html`
        #（2026-10-16 实测踩到：排掉后源文件不存在，渲染直接失败）。
        #
        # 这里读/写的是**用户自己的**路径（`--workspace` 里那份 HTML 与 `--out` 指定
        # 的 PDF 落点），本地单用户工具里没有权限边界可越——「把 PDF 写到用户选的
        # 位置」就是这个功能的定义。命令行那条真正的风险面（把用户值变成命令）已由
        # `allowlisted_browser()` + 固定名关掉（#194）。
        # 注：不要试图用 `# codeql[py/path-injection]` 行内抑制——2026-10-17 实测
        # （#325，注释就写在被标记的 4 行上）**对 Python 不生效**，CodeQL 仍报 4 条。
        # 镜像范围收窄到「渲染可能引用的类型」（外部审计 2026-10-18 情形 1/3）：
        # 此前是「除 PDF 外全拷」——那会把同目录的面试笔记 / 投递记录 CSV /
        # 其它版本简历一起复制进临时目录，等于把无关内容搬出一个它本不该出的
        # 位置（进程崩溃时还会以 TMP_PREFIX 留在系统临时区）。
        # 类型白名单是**fail-closed** 的方向：认不出的后缀视为"渲染不需要"，
        # 代价是极端后缀的图片可能不显示（比把用户内容复制出工作区可接受）。
        # `symlinks=True`：不跟随符号链接（情形 2）——否则 `copytree` 会把链接
        # **目标的内容**读出来一起复制。
        shutil.copytree(source_dir, work, dirs_exist_ok=True, symlinks=True,
                        ignore=_ignore_non_renderable)
        staged_html = os.path.join(work, _STAGED_HTML)
        staged_pdf = os.path.join(work, _STAGED_PDF)
        copied_html = os.path.join(work, os.path.basename(html_path))
        # 同名时 copytree 已经把它放成暂存名了，再 copyfile 会 SameFileError
        # （2026-10-18 实测：HTML 文件名恰好叫 resume.html 时直接崩）。
        if os.path.abspath(copied_html) != os.path.abspath(staged_html):
            shutil.copyfile(copied_html, staged_html)
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
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False
        if not os.path.isfile(staged_pdf):
            return False
        shutil.move(staged_pdf, pdf_path)
        return os.path.isfile(pdf_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
