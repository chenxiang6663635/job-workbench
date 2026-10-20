# -*- coding: utf-8 -*-
"""首次使用初始化：把**随包模板**铺成一个空工作区（2026-10-19）。

**为什么需要它**（真机实测的阻塞级缺口）：只装 DSH 插件时，`<data_root>/personal`
不存在 → `server.main()` 在 `resolve_workspace(must_exist=True)` 处直接 `return 2`，
**17 个工具一个都不注册**；而 npm 包里没有 init 入口（`install.ps1` 只做 pnpm + 装包）。
材料其实是齐的——`template/workspace` 被打进 exe 的 `_internal` 里——缺的只是入口。

**策略（避免静默兜底，与仓库一贯立场一致）**：

- **默认根**（未设 `JOBWS_DATA_DIR` / `JOBWS_WORKSPACE`）+ 工作区缺失 → 自动建空骨架，
  并在 stderr 说明（零配置即可用）；
- **显式**配置（设了上述环境变量，或命令行给了 `--workspace`）+ 缺失 → **仍然报错**，
  不自动创建：把写错的路径悄悄建成工作区，比报错更难发现；
- 任何路径下都**不覆盖**已有文件（幂等）。
"""

import os
import shutil
import sys

from . import paths

# 与 `tools/init_workspace.py` 的 MODULES 保持一致（同一套骨架；改一处要改两处，
# 由 `tests/test_init_workspace.py` 的骨架断言兜底——它是从模板实际拷出来验证的）
MODULES = ("00_事实库", "01_岗位池", "02_简历工坊",
           "03_面试准备", "04_知识库", "05_投递追踪")

ENV_DATA_DIR = "JOBWS_DATA_DIR"


def template_root():
    """随包模板根（`.../template`）：打包取 exe 同级或其 `_internal`，源码取仓库根。

    PyInstaller onedir 把 data 放在 `_internal/`（`bin/jobws-mcp.exe` 的兄弟目录），
    而应用根在 MCP 形态下被 `paths.py` 注入成**数据根**——所以这里不能复用
    `pathres.resolve_root()`，必须自己按可执行文件定位。
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
        candidates = [os.path.join(base, "template"),
                      os.path.join(base, "_internal", "template")]
    else:
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [os.path.join(repo, "template")]
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "workspace")):
            return candidate
    raise RuntimeError("随包模板缺失：%s" % "、".join(candidates))


def init_workspace(target):
    """把模板铺到 `target`；**不覆盖**已有文件。返回本次创建的文件绝对路径清单。"""
    template = template_root()
    source = os.path.join(template, "workspace")
    os.makedirs(target, exist_ok=True)
    created = []

    for module in MODULES:
        module_src = os.path.join(source, module)
        if not os.path.isdir(module_src):
            continue
        module_dst = os.path.join(target, module)
        os.makedirs(module_dst, exist_ok=True)
        for dirpath, _dirnames, filenames in os.walk(module_src):
            rel = os.path.relpath(dirpath, module_src)
            out_dir = module_dst if rel == "." else os.path.join(module_dst, rel)
            os.makedirs(out_dir, exist_ok=True)
            for name in filenames:
                dst = os.path.join(out_dir, name)
                if os.path.exists(dst):
                    continue
                shutil.copy2(os.path.join(dirpath, name), dst)
                created.append(dst)

    # 根级说明文件：与 `tools/init_workspace.py` 同口径（缺则补，有则不动）
    for src_name, dst_name in (("README.md", "README.md"),):
        src = os.path.join(source, src_name)
        dst = os.path.join(target, dst_name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            created.append(dst)

    agents_src = os.path.join(template, "AGENTS.example.md")
    agents_dst = os.path.join(target, "AGENTS.md")
    if os.path.isfile(agents_src) and not os.path.exists(agents_dst):
        shutil.copy2(agents_src, agents_dst)
        created.append(agents_dst)

    return created


def _is_explicit(explicit_workspace):
    """是否属于「用户显式指定了位置」——那种情况不自动建。"""
    return bool(explicit_workspace) or bool(
        os.environ.get(ENV_DATA_DIR) or os.environ.get(paths.ENV_WORKSPACE))


def ensure_workspace(explicit_workspace=None):
    """解析工作区；仅在「默认根 + 缺失」时自动初始化。

    返回 `(工作区绝对路径, 说明文本或 None)`；显式配置下缺失会抛
    `paths.WorkspaceError`（由入口转成退出码 2，行为与改动前一致）。
    """
    if _is_explicit(explicit_workspace):
        return paths.resolve_workspace(explicit_workspace, must_exist=True), None

    default = paths.resolve_default_workspace()
    if os.path.isdir(default):
        return default, None

    created = init_workspace(default)
    notice = ("jobws-mcp: 首次使用，已自动初始化空工作区：%s（%d 个文件）。"
              "如需样例数据或领域插件，请用桌面端初始化，或运行 `jobws init`。"
              % (default, len(created)))
    return default, notice
