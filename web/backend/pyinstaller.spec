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
    # tools/ 下被后端 import 的脚本
    "tracker",
    "jd_score",
]

a = Analysis(
    ["main.py"],
    pathex=[BACKEND_DIR],
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
