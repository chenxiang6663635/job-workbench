# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）——jobws-mcp（DSH 随包运行时，#271 P2-2）。

原则与 `web/backend/pyinstaller.spec` 同源：onedir（启动快、少杀软误报）、不 UPX、
`collect_submodules` 按**导入名**收集（领域层/服务层都在 site-packages，装成 wheel
后照样找得到，不硬编码仓库相对路径）。

打包后布局（bin/ 之下）：
  jobws-mcp.exe     MCP 服务入口（stdio；`--workspace <名>` 可选）
  _internal/...     PyInstaller 运行时与全部依赖

用法（cwd = mcp/）：`pyinstaller --clean --noconfirm pyinstaller.spec`
产物由 `scripts/build_mcp_exe.ps1` 复制到
`integrations/dsh/platform/win32-x64/bin/` 并生成 `prebuilds.json`。
"""

import os

# cwd = mcp/；REPO_ROOT 即仓库根
REPO_ROOT = os.path.dirname(os.path.abspath(os.getcwd()))

from PyInstaller.utils.hooks import (  # noqa: E402
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

datas = []

# template/ 必须随包：jobws_core 的 jd_score / resume_build 按 `__file__` 向上定位
# `ROOT/template/...`（与后端打包同一理由——2026-09-13 审查 MAJOR-1 的同款形态：
# 缺了它只在**请求时**才炸，CI 只构建不运行产物发现不了）。
_template_src = os.path.join(REPO_ROOT, "template")
if os.path.isdir(_template_src):
    for name in sorted(os.listdir(_template_src)):
        src = os.path.join(_template_src, name)
        if os.path.isfile(src):
            datas.append((src, "template"))
        elif os.path.isdir(src):
            datas.append((src, os.path.join("template", name)))

# certifi 的随包 CA 清单：出网证书兜底（jobws_core.tls_policy）按 `certifi.where()`
# 读这个文件；PyInstaller 静态分析看不见"运行时读文件"。
datas += collect_data_files("certifi")

# --- 领域包 jobws-core -------------------------------------------------------
try:
    domain_hidden = collect_submodules("jobws_core")
    # 元数据：jobws_core.__version__ 与 info 工具的 coreVersion 走 importlib.metadata，
    # PyInstaller 默认不收集 dist-info——不补的话打包版只能拿到回退值。
    domain_datas = copy_metadata("jobws-core")
except Exception as exc:  # noqa: BLE001 —— 构建环境没装领域包：宁可当场炸
    raise RuntimeError(
        "找不到领域包 jobws_core（%s）。构建前先装："
        "pip install .\\packages\\jobws-core" % exc)
if not domain_hidden:
    raise RuntimeError("collect_submodules('jobws_core') 返回空——领域包没装对")

# --- MCP 服务包 jobws-mcp ----------------------------------------------------
try:
    server_hidden = collect_submodules("jobws_mcp")
    # 元数据：info 工具的 serverVersion 走 importlib.metadata.version('jobws-mcp')。
    server_datas = copy_metadata("jobws-mcp")
except Exception as exc:  # noqa: BLE001
    raise RuntimeError(
        "找不到 jobws_mcp 包（%s）。构建前先装：pip install .\\mcp" % exc)
if not server_hidden:
    raise RuntimeError("collect_submodules('jobws_mcp') 返回空——服务包没装对")

# --- MCP SDK（含顶层 mcp_types，guard.py 直接 import 它） ---------------------
# 只枚举 server / shared 两个分支：`collect_submodules("mcp")` 会 import 到
# `mcp.cli`——它在缺可选 CLI 依赖时**直接 sys.exit(1)**，枚举当场炸（2026-10-07 实证）。
# 静态分析仍会沿 server.py 的 import 链补全其余可达模块。
sdk_hidden = (collect_submodules("mcp.server")
              + collect_submodules("mcp.shared")
              + collect_submodules("mcp_types")
              + ["mcp", "mcp.types"])

a = Analysis(
    # 入口是包外的薄启动器（run_server.py）：直接把 jobws_mcp/server.py 当入口会让
    # 冻结产物按**顶层脚本**执行、相对导入全废（2026-10-07 冒烟实证，见该文件头注）。
    ["run_server.py"],
    pathex=[],
    binaries=[],
    datas=datas + domain_datas + server_datas,
    hiddenimports=domain_hidden + server_hidden + sdk_hidden + ["certifi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除用不到的大依赖，减小体积（与后端 spec 同款）
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
    name="jobws-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 不压缩：UPX 会显著加剧杀软误报
    console=True,
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
    name="jobws-mcp",
)
