# -*- coding: utf-8 -*-
"""【已废弃】`pathres` 的旧路径 —— 转发到 `jobws_core.pathres`。

2026-09-19 批 6 第二批：`pathres` 搬进领域包（`packages/jobws-core`，import 名
`jobws_core`）。本文件不再有实现，只做**转发**，让 `main.py` / `deps.py` /
`routers/system.py` / `mcp/jobws_mcp/paths.py` 与 `tests/` 的存量 import 零改动。

搬它的动因：这个模块做的事**必须**跟着领域层走。`resolve_root()` 原本从 `__file__`
推断应用根——住 `web/backend/` 时向上三级正好是仓库根，可一旦代码进了 site-packages，
同一个表达式指向安装目录的上层，数据根静默改指（完整论证见
`tests/test_domain_root.py`）。所以搬家与「改成注入式」是同一笔：入口显式
`set_app_root()`，没注入就报错。

下一步：`jobws lint legacy-imports` 统计旧名 import 点数量（只许下降），
全部改完后的**下一版**删除本文件。

为什么直接把 sys.modules 换成真身而不是逐名字转发：同 `tools/filelock.py` 的论证
——`from pathres import X` 在 import 完成后会从 `sys.modules["pathres"]` 取属性，
替换后拿到的就是真身；逐名字转发是**值快照**，`_APP_ROOT` 这类可变全局会静默不跟随。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings

warnings.warn(
    "import pathres 已废弃：领域层已包化，请改用 `from jobws_core import pathres`"
    "（或 `import jobws_core.pathres`）。旧路径将在下一版删除。",
    DeprecationWarning,
    stacklevel=2,
)


def _import_real():
    """导入真身；未安装时退化为「源码形态」——把包的 src 加进 sys.path 再试。

    为什么要有兜底：开发者与 CI 若没装 `packages/jobws-core`，直接跑 pytest 会
    因为找不到 jobws_core 而全红。兜底让源码形态照样能跑，但它**不是**目标形态
    ——目标是装上就能用（CI 另有非 editable 的安装冒烟来守这条）。
    """
    try:
        return importlib.import_module("jobws_core.pathres")
    except ImportError:
        # 本文件在 web/backend/ → 上溯三级是仓库根（比 tools/ 下的 shim 多一层）
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "packages",
            "jobws-core",
            "src",
        )
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)
        return importlib.import_module("jobws_core.pathres")


_real = _import_real()
sys.modules[__name__] = _real
# 防御性透传 __path__：真身若是**包**，`import pathres.<子模块>` 就可达；
# 当前真身是模块（不是包），这里拿到的是空列表，属预期。
__path__ = list(getattr(_real, "__path__", []))


def __getattr__(name):  # PEP 562 兜底（sys.modules 已被替换，正常情况下不会走到）
    return getattr(_real, name)
