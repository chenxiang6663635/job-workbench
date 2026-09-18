# -*- coding: utf-8 -*-
"""【已废弃】`filelock` 的旧路径 —— 转发到 `jobws_core.filelock`。

2026-09-17 批 6：领域层开始包化（`packages/jobws-core`，import 名 `jobws_core`）。
本文件不再有实现，只做**转发**，让 10 处后端 import、5 处 tracker import 与
54 个自插 sys.path 的测试文件**零改动**继续工作。

为什么直接把 sys.modules 换成真身而不是逐名字转发：
- `from filelock import file_lock` 这类写法在 import 完成后会从
  `sys.modules["filelock"]` 取属性——替换后拿到的就是真身，语义完全一致；
- 逐名字转发（`from jobws_core.filelock import file_lock`）是**值快照**，将来若
  出现可变全局就会静默不跟随（同款教训见 `tools/tracker/__init__.py`）。

下一步：`jobws lint legacy-imports` 统计旧名 import 点数量（只许下降），
全部改完后的**下一版**删除本文件。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings

warnings.warn(
    "import filelock 已废弃：领域层已包化，请改用 `from jobws_core import filelock`"
    "（或 `import jobws_core.filelock`）。旧路径将在下一版删除。",
    DeprecationWarning,
    stacklevel=2,
)


def _import_real():
    """导入真身；未安装时退化为「源码形态」——把包的 src 加进 sys.path 再试。

    为什么要有兜底：开发者与 CI 若没装 `packages/jobws-core`，直接跑 pytest
    会因为找不到 jobws_core 而全红。兜底让源码形态照样能跑，但它**不是**
    目标形态——目标是装上就能用（CI 另有非 editable 的安装冒烟来守这条）。
    """
    try:
        return importlib.import_module("jobws_core.filelock")
    except ImportError:
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "packages",
            "jobws-core",
            "src",
        )
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)
        return importlib.import_module("jobws_core.filelock")


_real = _import_real()
sys.modules[__name__] = _real
# 防御性透传 __path__：真身若是**包**，`import filelock.<子模块>` 就可达；
# 当前真身是模块（不是包），这里拿到的是空列表，属预期（独立审查 NIT-5）。
__path__ = list(getattr(_real, "__path__", []))


def __getattr__(name):  # PEP 562 兜底（sys.modules 已被替换，正常情况下不会走到）
    return getattr(_real, name)
