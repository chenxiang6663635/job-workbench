# -*- coding: utf-8 -*-
"""MCP 包**不再需要仓库在侧**的验收（2026-09-19 批 6 第二批 PR-B）。

这是本批的核心承诺：删掉 `paths.py` 里的 sys.path 注入与 `JOBWS_REPO_ROOT` 推导之后，
`jobws-mcp` 应当**装上就能用**——领域层全部在 `jobws_core` 包里。

RED 的形态（本测试第一次跑的预期）：`paths.py` 还在用 `dirname²(__file__)` 推仓库根，
把包**复制到仓库之外**（模拟装进 site-packages）之后 `web/backend` 与 `tools/` 都不存在，
导入直接 `ImportError`——这正是「仓库不在默认位置就用不了」的机器形态。

为什么要复制而不是改 cwd：硬闸推的是**包位置**（不是 cwd），光换 cwd 它照样能找到仓库，
测不出真问题（`test_stdio_smoke.py` 在仓库里跑，永远绿）。
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

_PKG = pathlib.Path(__file__).resolve().parents[1] / "jobws_mcp"


def test_importable_outside_the_repository(tmp_path):
    """包复制到仓库外（无 JOBWS_REPO_ROOT）后，读侧与写侧都能导入。"""
    shutil.copytree(_PKG, tmp_path / "jobws_mcp",
                    ignore=shutil.ignore_patterns("__pycache__"))
    env = {k: v for k, v in os.environ.items() if k != "JOBWS_REPO_ROOT"}
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-c",
         "from jobws_mcp import tools_readonly, tools_writable; "
         "from jobws_mcp import paths; "
         "assert not hasattr(paths, 'REPO_ROOT'), '硬闸还在'; "
         "print('ok')"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, "仓库之外导入失败：\n%s" % (proc.stderr or proc.stdout)


def test_tools_actually_work_outside_the_repository(tmp_path):
    """不只「能 import」：独立安装下**读工具真返回数据、写工具真拿到令牌**。

    2026-09-19 审查 MINOR：初版只断言了导入与「没有 REPO_ROOT」——那两条读代码即可
    推断，而「装上就能用」的承诺落在**调用**上。这里在同一个子进程里真跑一遍：
    用领域层造一张只有一行的追踪表，再让 MCP 的读工具数它、写工具给它发令牌。
    """
    shutil.copytree(_PKG, tmp_path / "jobws_mcp",
                    ignore=shutil.ignore_patterns("__pycache__"))
    data_root = tmp_path / "data"
    (data_root / "personal" / "05_投递追踪").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k != "JOBWS_REPO_ROOT"}
    env["PYTHONPATH"] = str(tmp_path)
    env["JOBWS_DATA_DIR"] = str(data_root)
    code = """
import os

# 顺序有意义：先 import 本包触发 `paths.py` 的应用根注入，**再**用领域层。
# 领域层在导入期就求值 ROOT，而 pathres 已不从 __file__ 推断（这条顺序要求本身
# 就是设计的一部分：谁能算是「入口」谁负责注入）。
from jobws_mcp import tools_readonly, tools_writable

from jobws_core import tracker

ws = os.path.join(os.environ["JOBWS_DATA_DIR"], "personal")
tracker.write_rows([{"id": "T001", "公司": "示例科技", "岗位": "后端"}], ws)

apps = tools_readonly.list_applications(ws)
assert apps.get("total") == 1, apps
assert apps["items"][0]["id"] == "T001", apps

preview = tools_writable.preview_add_application(
    ws, 公司="示例科技", 岗位="测试岗", 批次="正式批",
    当前阶段=tracker.STAGES[0])  # 用真实枚举值，不猜字面量
assert preview.get("token"), preview
assert preview.get("expires_at"), preview
print("ok")
"""
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, "仓库之外调用工具失败：\n%s" % (proc.stderr or proc.stdout)

