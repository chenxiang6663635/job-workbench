"""DSH npm 包的许可材料（2026-10-30 审计 §六）。

问题：两个包都声明 `"license": "MIT"`，但 `integrations/dsh/` 里没有 LICENSE，
`files` 也不含根部的 `LICENSE` / `THIRD-PARTY-NOTICES.md`——npm 只打包包目录内的
文件，`files: ["../../LICENSE"]` 无效。平台包还会分发 PyInstaller 打进去的第三方依赖，
光靠 `package.json` 的 license 字段不足以构成合规发行物。

做法：`scripts/sync_notices.cjs` 在 `prepack` 里把两份材料复制进包目录（生成物，
已 gitignore），两个包的 `files` 都列上它们。
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNC = os.path.join(ROOT, "integrations", "dsh", "scripts", "sync_notices.cjs")
PACKAGES = [
    os.path.join(ROOT, "integrations", "dsh", "package.json"),
    os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64", "package.json"),
]
NOTICES = ["LICENSE", "THIRD-PARTY-NOTICES.md"]


def test_both_manifests_list_the_notices():
    for path in PACKAGES:
        with open(path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        for name in NOTICES:
            assert name in pkg.get("files", []), "%s 的 files 里缺 %s" % (path, name)
        assert "sync_notices.cjs" in pkg["scripts"]["prepack"], \
            "%s 的 prepack 没有同步许可材料" % path


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑同步脚本")
def test_sync_copies_both_files_verbatim():
    """目标必须在仓库内：脚本是从目标目录往上找 LICENSE 的（包目录天然在仓库里）。"""
    target = tempfile.mkdtemp(prefix=".tmp-notices-", dir=ROOT)
    try:
        subprocess.run(["node", SYNC, target], check=True, capture_output=True)
        for name in NOTICES:
            copied = os.path.join(target, name)
            assert os.path.isfile(copied), name + " 没被复制"
            with open(os.path.join(ROOT, name), "rb") as f:
                expected = f.read()
            with open(copied, "rb") as f:
                assert f.read() == expected, name + " 内容与仓库根不一致"
    finally:
        shutil.rmtree(target, ignore_errors=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑同步脚本")
def test_sync_fails_loudly_when_no_license_above(tmp_path):
    """目标目录往上找不到 LICENSE 时必须 exit 1，不能静默产出无许可的包。"""
    result = subprocess.run(
        ["node", SYNC, str(tmp_path / "nowhere")], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "找不到" in (result.stderr or "")
