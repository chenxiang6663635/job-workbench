# -*- coding: utf-8 -*-
"""测试入口的解释器护栏：基线 3.12（2026-09-14 从 3.8 升上来）。

为什么护栏放在**测试**而不是 CLI：技术要求其实只有 ≥3.9（用到了 `imaplib` 的
`timeout=` 参数），但**支持**基线是 3.12——CI 与打包只验证这一个版本。CLI 在
3.10/3.11 上通常照样能跑，给一个硬拦截等于谎报要求；而测试不同：解释器错了会
以另一套语义跑（或收集期就炸成一堆看不懂的错误），结论是**静默不可信**的。

本机最常见的坑是 `python` 落到别的项目在用的 conda 环境（3.8）。那种失败看起来
像"代码坏了"——所以在收集之前就把话说清楚，并给出可照做的修法。

实现上的两个细节（都是实测踩出来的）：
* 用 `pytest_configure` 钩子而不是在模块顶层 `pytest.exit()`：顶层调用会被
  pytest 当成"conftest 加载失败"，报成一个 ImportError 并给退出码 4；钩子里退出
  是干净的一条消息 + 约定的退出码 2（本仓库"用法/配置错误"的码）。
* 消息走 `sys.stderr`（Python 自己的输出链）而不是交给 pytest 的终端写入器：
  后者在本机的 3.8 环境里会把中文写成乱码，护栏就白设了。
"""

import os
import sys

import pytest

# ---- 注入应用根（pathres）----
#
# pathres 自 2026-09-19（批 6 第二批）起**不再从 `__file__` 推断根目录**：它搬进了
# 可安装包，那套推断会静默指向 site-packages 的上层、把数据根悄悄改指（论证见
# tests/test_domain_root.py 的模块 docstring）。所以每个入口显式告诉它「我在哪」。
#
# 放在 conftest 的**模块顶层**，是为了早于所有测试模块的导入：不少测试在模块顶层
# 就 `import deps`（deps 在顶层调 resolve_root），晚一步就是收集期报错。
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.join(_ROOT_DIR, "web", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from jobws_core import pathres  # noqa: E402

pathres.set_app_root(_ROOT_DIR)

BASELINE = (3, 12)


def _force_utf8(stream):
    """把流切到 UTF-8——与 `tools/jobws.py` 同款处理。

    Windows 控制台默认 GBK，输出被管道接走时按 locale 编码，中文会变乱码
    （护栏消息乱码就等于护栏失效）。CI 的 Linux 环境本就是 UTF-8，无行为变化。
    """
    if stream is None or not getattr(stream, "encoding", None):
        return
    if stream.encoding.lower() == "utf-8":
        return
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception as exc:  # 只影响显示层：说一声，不阻断（禁静默吞错）
        sys.stderr.write("注意：stderr 切换 UTF-8 失败（%s），提示可能乱码\n" % exc)


def pytest_configure(config):
    if sys.version_info >= BASELINE:
        return
    _force_utf8(sys.stderr)
    sys.stderr.write(
        "解释器基线不对：本仓库要求 Python %d.%d+，当前是 %s（%s）。\n"
        "请换 3.12 的解释器重跑，例如：\n"
        "  <venv>\\Scripts\\python.exe -m pytest tests/ -q\n"
        "约定与维护者环境见 CONTRIBUTING「解释器基线」一节；"
        "`python` 可能落到别项目在用的 conda 环境（那会得出错误的结论）。\n"
        % (BASELINE[0], BASELINE[1],
           ".".join(str(part) for part in sys.version_info[:3]), sys.executable))
    pytest.exit("解释器基线不对（详见上一条消息）", returncode=2)
