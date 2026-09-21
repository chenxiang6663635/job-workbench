# -*- coding: utf-8 -*-
"""【已废弃】tools/tracker 包 —— 转发到 `jobws_core.tracker`，并挂回留仓的 CLI 子模块。

2026-09-19 批 6 第二批：领域层（13 个模块）搬进 `packages/jobws-core`。本包不再
有领域实现，只做两件事：

1. **逐子模块别名**：把 `tracker._core` / `tracker.applications` … 注册进
   `sys.modules`（指向 `jobws_core.tracker.*` 的**同一个模块对象**）。为什么必须是
   同一个对象：留仓的 `_cli*.py` 用 `from . import _core` 取名字，测试也用
   `tracker._core.WORKSPACE` 做 monkeypatch——两份副本会让 patch 打到一边、
   被 patch 的副本继续跑，**静默失效**（`tests/test_cli_surface.py` 正是这种 patch）。
2. **合并门面**：属性访问先转真身（`tracker.ROOT` / `set_workspace` / 100+ 个名字），
   再回落到留仓的 CLI 子模块及其名字（`tracker._cli` / `tracker.main` / `cmd_*` …）。
   CLI 子模块按用户拍板**留仓**。

为什么不用 `filelock` shim 那套「整体替换 `sys.modules["tracker"]`」：真身
`jobws_core.tracker` **没有** `_cli*`，整替换会把留仓的 CLI 一起弄丢。

`__name__` 仍是 `tracker`（`tools/` 在 sys.path 上），所以下面的别名键就是
`"tracker.<mod>"`——与旧路径的引用方式一字不差。

下一步：`jobws lint legacy-imports` 统计旧名 import 点数量（只许下降），
全部改完后的**下一版**删除本文件（留仓的 `_cli*.py` 会随之迁到别处）。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings

warnings.warn(
    "import tracker 已废弃：领域层已包化，请改用 `from jobws_core import tracker`"
    "（或 `import jobws_core.tracker`）。领域模块的旧路径将在下一版删除"
    "（留仓的 CLI 子模块不在此列，它们仍属于本包）。",
    DeprecationWarning,
    stacklevel=2,
)

_DOMAIN = ("_core", "_schema", "_check", "applications", "interviews", "talks",
           "mails", "contacts", "offers", "importing", "deletes", "preview_app",
           "preview_interview", "preview_update")
_CLI = ("_cli", "_cli_interview", "_cli_talk", "_cli_mail", "_cli_contact",
        "_cli_offer", "_cli_misc", "_cli_delete")

# 先确保应用根有值：真身的 `_core` 在**模块顶层**就调 `pathres.resolve_root()`，
# 而它已不再从 `__file__` 推断——晚一步这里就是 ImportError。`tools/report.py`
# 这类「直跑只给迁移提示」的脚本会先 import 本包，正是踩点（2026-09-19 实测）。
# 用 if_unset 而不是 set：入口（main.py / jobws.py / mcp）的显式注入是权威值。
_pathres = importlib.import_module("jobws_core.pathres")
_pathres.set_app_root_if_unset(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_real = importlib.import_module("jobws_core.tracker")

# ① 逐子模块别名（同一个模块对象——见模块 docstring 第 1 条）
for _name in _DOMAIN:
    sys.modules[__name__ + "." + _name] = importlib.import_module(
        "jobws_core.tracker." + _name)


def __getattr__(name):
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    # ② 领域侧：真身包的门面
    try:
        return getattr(_real, name)
    except AttributeError:
        pass
    # ③ 留仓 CLI：先是子模块本身，再是它们内部的名字（main / cmd_* / build_parser …）
    if name in _CLI:
        return importlib.import_module("." + name, __name__)
    for mod_name in _CLI:
        mod = importlib.import_module("." + mod_name, __name__)
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(__all__)


__all__ = _real.__all__ + list(_CLI)
