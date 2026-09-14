# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

为什么用 onedir 而非 onefile：
- onefile 每次启动都要解压到临时目录（慢）
- onefile 更易被杀软误报（Windows Defender/360/火绒），UPX 压缩会加剧
- onedir 资源放 exe 同级，规避 sys._MEIPASS 路径定位坑

打包后目录布局（exe 同级）：
  dist/job-workbench-backend/
    job-workbench-backend.exe   后端入口
    tools/                      tools/ 脚本（后端 import 用）
    dist/                       前端静态产物（由构建脚本拷入）
    personal/                   用户工作区（便携模式，可写时）

用法：pyinstaller --clean --noconfirm pyinstaller.spec
（修好 spec 后始终这样重编，不要重新生成 spec 覆盖 datas/hiddenimports）
"""

import os
import sys

block_cipher = None

# 在本文件所在目录（web/backend）执行 pyinstaller，cwd 即 web/backend
BACKEND_DIR = os.path.abspath(os.getcwd())
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))

# tools/ 作为数据文件放到 exe 同级（后端 import tools 脚本用）
tools_datas = []
_tools_src = os.path.join(REPO_ROOT, "tools")
if os.path.isdir(_tools_src):
    for name in sorted(os.listdir(_tools_src)):
        src = os.path.join(_tools_src, name)
        if os.path.isfile(src):
            tools_datas.append((src, "tools"))

# tools/ 下的模块名清单（喂给 hiddenimports，理由见下方 project_hidden）。
# 后端对这些模块用**裸名导入**（`import tracker`、`from report import …`、`import imap_fetch`）：
# tools/ 不在 pathex 里时 PyInstaller 找不到它们 → 跳过、不进依赖图 → 它们自己 import 的库
# 不会被收集。v0.2.2 就是这么丢的 `imaplib`（打包版后端一启动就 ModuleNotFoundError）；
# 而 CI 只构建不运行产物，所以全绿。手写模块名治不了本（曾只写 tracker/jd_score，
# 新加的 imap_fetch 照样漏），因此这里**自动枚举**：新增 tools 模块自动进分析图。
tools_modules = []
if os.path.isdir(_tools_src):
    tools_modules = sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(_tools_src)
        if name.endswith(".py") and name != "__init__.py"
    )

# uvicorn 的动态导入必须显式声明，否则打包后启动即失败（业界公认的坑）
uvicorn_hidden = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

# 本项目模块（routers 与后端内部模块被动态/间接导入）
project_hidden = [
    "pathres",
    "deps",
    "filelock",
    "py_runtime",
    "routers",
    "routers.applications",
    "routers.dashboard",
    "routers.jobs",
    "routers.library",
    "routers.provider",
    "routers.workspace",
] + tools_modules  # tools/ 下全部模块（自动枚举，理由见上方 tools_modules）

a = Analysis(
    ["main.py"],
    # tools/ 也必须在 pathex 里：否则上面那些裸名模块 PyInstaller 根本找不到，
    # hiddenimports 里写了等于没写（v0.2.2 的实证：tracker/jd_score 也没进 PYZ）
    pathex=[BACKEND_DIR] + ([_tools_src] if os.path.isdir(_tools_src) else []),
    binaries=[],
    datas=tools_datas,
    hiddenimports=uvicorn_hidden + project_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除用不到的大依赖，减小体积
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir：二进制分离，配合下面的 COLLECT
    name="job-workbench-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 不压缩：UPX 会显著加剧杀软误报
    console=True,  # 保留控制台便于排障；稳定后可改 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="job-workbench-backend",
)
