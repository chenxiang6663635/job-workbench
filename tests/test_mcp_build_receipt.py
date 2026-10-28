# -*- coding: utf-8 -*-
"""构建收据生成器（scripts/mcp_build_receipt.py）的行为测试。

为什么值得测：收据是 G4 签署「这次构建的输入身份」的唯一载体。如果它悄悄漏字段、
或在缺输入时仍然写出一份"看起来完整"的 JSON，签署就建立在空话上。
"""

import io
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "mcp_build_receipt.py")

sys.path.insert(0, os.path.join(REPO, "scripts"))
import mcp_build_receipt as R  # noqa: E402


def _make_tree(tmp_path, files=2, pem=True):
    """造一份最小的 manifest + exe + pem 目录，返回各路径。"""
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    exe = binp / "jobws-mcp.exe"
    exe.write_bytes(b"fake-exe")
    if pem:
        cert = binp / "_internal" / "certifi"
        cert.mkdir(parents=True, exist_ok=True)
        (cert / "cacert.pem").write_text("fake-pem", encoding="utf-8")

    manifest = tmp_path / "prebuilds.json"
    manifest.write_text(json.dumps({
        "schemaVersion": 1, "version": "26.11.0", "status": "built",
        "files": {"bin/jobws-mcp.exe": "x", "bin/a.txt": "y"} if files else {},
    }), encoding="utf-8")

    lock = tmp_path / "build-requirements.lock"
    lock.write_text("certifi==2026.10.19 --hash=sha256:aa\n", encoding="utf-8")

    wheel = tmp_path / "jobws_core-0.0.0-py3-none-any.whl"
    wheel.write_bytes(b"fake-wheel")
    return {"exe": exe, "manifest": manifest, "lock": lock, "wheel": wheel}


def _args(tree, py=None):
    class A:
        pass

    a = A()
    a.python = py or sys.executable
    a.lock = str(tree["lock"])
    a.core_wheel = str(tree["wheel"])
    a.mcp_wheel = str(tree["wheel"])
    a.exe = str(tree["exe"])
    a.manifest = str(tree["manifest"])
    a.from_lock = True
    return a


def test_receipt_has_all_required_sections(tmp_path):
    tree = _make_tree(tmp_path)
    manifest = json.load(io.open(tree["manifest"], encoding="utf-8"))
    receipt = R.build_receipt(_args(tree), manifest)

    for section in ("source", "interpreter", "dependencies", "build_tools",
                    "first_party", "security_baseline", "artifact"):
        assert section in receipt, "收据缺 %s 段" % section

    # dirty 字段必须在：带未提交改动的构建，git_sha 不代表实际源码
    assert "dirty" in receipt["source"]
    assert receipt["interpreter"]["declarative_venv"] is True
    assert receipt["build_tools"]["no_build_isolation"] is True
    assert receipt["artifact"]["manifest_version"] == "26.11.0"
    assert receipt["artifact"]["file_count"] == 2
    assert len(receipt["artifact"]["exe_sha256"]) == 64


def test_receipt_records_pem_and_lock_hash(tmp_path):
    tree = _make_tree(tmp_path)
    manifest = json.load(io.open(tree["manifest"], encoding="utf-8"))
    receipt = R.build_receipt(_args(tree), manifest)

    assert receipt["security_baseline"]["pem_sha256"] == R.sha256(
        str(tree["exe"].parent / "_internal" / "certifi" / "cacert.pem"))
    assert receipt["dependencies"]["lock_sha256"] == R.sha256(str(tree["lock"]))


def test_missing_pem_is_empty_not_crash(tmp_path):
    """没有 cacert.pem 时记空串——不因为缺一个文件就整体失败。"""
    tree = _make_tree(tmp_path, pem=False)
    manifest = json.load(io.open(tree["manifest"], encoding="utf-8"))
    receipt = R.build_receipt(_args(tree), manifest)
    assert receipt["security_baseline"]["pem_sha256"] == ""


@pytest.mark.parametrize("missing", ["lock", "exe", "manifest", "wheel"])
def test_cli_returns_2_on_missing_input(tmp_path, missing):
    """缺输入必须 exit 2，**不能**写出一份看似完整的收据。"""
    tree = _make_tree(tmp_path)
    tree[missing].unlink()
    out = tmp_path / "receipt.json"

    proc = subprocess.run(
        [sys.executable, SCRIPT, "--out", str(out),
         "--python", sys.executable, "--lock", str(tree["lock"]),
         "--core-wheel", str(tree["wheel"]), "--mcp-wheel", str(tree["wheel"]),
         "--exe", str(tree["exe"]), "--manifest", str(tree["manifest"])],
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    assert proc.returncode == 2, "缺 %s 时应 exit 2，实际 %d" % (missing, proc.returncode)
    assert not out.exists(), "缺输入时不得写出收据"
