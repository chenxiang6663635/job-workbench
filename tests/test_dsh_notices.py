"""DSH npm 包的许可材料（2026-10-30 审计 §六；2026-10-31 修重复同步）。

问题：两个包都声明 `"license": "MIT"`，但 `integrations/dsh/` 里没有 LICENSE，
`files` 也不含根部的 `LICENSE` / `THIRD-PARTY-NOTICES.md`——npm 只打包包目录内的
文件，`files: ["../../LICENSE"]` 无效。平台包还会分发 PyInstaller 打进去的第三方依赖。

做法：`scripts/sync_notices.cjs` 在 `prepack` 里把两份材料复制进包目录（生成物，
已 gitignore），两个包的 `files` 都列上它们。

**第一版的坑**（本轮审计发现 3）：源目录是「从目标往上找同时含两份材料的目录」，
第一次运行后包目录自己就满足条件 → 第二次起 `root === target` → 直接跳过，根许可
更新了也刷不过去。现在来源固定为仓库根（从脚本位置往上找 `.git`），无条件覆盖。
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNC = os.path.join(ROOT, "integrations", "dsh", "scripts", "sync_notices.cjs")
PACKAGES = [
    os.path.join(ROOT, "integrations", "dsh", "package.json"),
    os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64", "package.json"),
]
NOTICES = ["LICENSE", "THIRD-PARTY-NOTICES.md"]

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑同步脚本")


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def test_both_manifests_list_the_notices():
    for path in PACKAGES:
        with open(path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        for name in NOTICES:
            assert name in pkg.get("files", []), "%s 的 files 里缺 %s" % (path, name)
        assert "sync_notices.cjs" in pkg["scripts"]["prepack"], \
            "%s 的 prepack 没有同步许可材料" % path


@needs_node
def test_first_run_copies_both_files_verbatim(tmp_path):
    subprocess.run(["node", SYNC, str(tmp_path)], check=True, capture_output=True)
    for name in NOTICES:
        assert _read(str(tmp_path / name)) == _read(os.path.join(ROOT, name)), name + " 内容不一致"


@needs_node
def test_second_run_refreshes_a_stale_copy(tmp_path):
    """包目录里已有（旧）副本时必须覆盖——这正是第一版漏掉的场景。"""
    subprocess.run(["node", SYNC, str(tmp_path)], check=True, capture_output=True)
    for name in NOTICES:
        with open(str(tmp_path / name), "ab") as f:
            f.write(b"\nOLD-MARKER\n")
    subprocess.run(["node", SYNC, str(tmp_path)], check=True, capture_output=True)
    for name in NOTICES:
        assert b"OLD-MARKER" not in _read(str(tmp_path / name)), name + " 没有被刷新"


@needs_node
def test_refuses_to_target_the_repo_root_itself():
    """目标就是仓库根时应当报错：那意味着在仓库根打包，许可会自己覆盖自己。"""
    result = subprocess.run(["node", SYNC, ROOT], capture_output=True, text=True)
    assert result.returncode != 0
    assert "仓库根" in (result.stderr or "")
