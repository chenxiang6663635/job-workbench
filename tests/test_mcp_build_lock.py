# -*- coding: utf-8 -*-
"""MCP Build Lock Contract v1 的判据测试（负向为主）。

设计要点：测试**真跑** `scripts/check_mcp_build_environment.py`，用它的
`--installed-json` 注入模式构造违规环境。这样测的是判据本身，而不是
"脚本里有没有某个关键字"——后者是假测试（本仓 2026-10 已在别处吃过教训）。

覆盖：
  · 正向：与锁集合相等 → PASS
  · 缺包 / 多余包 / 版本错 / 第一方 editable / 重复元数据 → 各自 FAIL
  · lock 与 .in 的版本闭包一致（防手改 lock 与输入脱节）
  · certifi 固定为已批准基线 2026.10.19（防再次被顺带升级）
  · lock 每项都带 --hash（无 hash 的"锁"只能防版本漂移，防不了内容替换）
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "mcp" / "build-requirements.lock"
LOCK_IN = ROOT / "mcp" / "build-requirements.in"
CHECKER = ROOT / "scripts" / "check_mcp_build_environment.py"

FIRST_PARTY = ("jobws-core", "jobws-mcp")
BOOTSTRAP = ("pip",)


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text):
    """从 lock / .in 文本里取 {规范化名: 版本}（忽略 hash 续行与注释）。"""
    pins = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+)", line)
        if m:
            pins[_norm(m.group(1))] = m.group(2)
    return pins


def lock_pins():
    return parse_pins(LOCK.read_text(encoding="utf-8"))


def build_dists(drop=(), extra=(), override=None, editable=(), first_party_hash=True):
    """按锁构造一份"正确的"已安装集合，再按需注入违规。"""
    override = override or {}
    editable = {_norm(x) for x in editable}
    rows = [
        {"name": n, "version": override.get(n, v), "editable": n in editable,
         "source": "", "wheel_sha256": ""}
        for n, v in lock_pins().items() if n not in drop
    ]
    # 第一方包与引导工具不在锁里：检查器校验「存在 + 非 editable + wheel 身份可审计」。
    # first_party_hash=False 用于模拟「目录安装」——有来源但无 wheel 哈希（应为缺口）。
    for name in FIRST_PARTY:
        rows.append({
            "name": name,
            "version": "0.0.0+local",
            "editable": _norm(name) in editable,
            "source": ("file:///repo/dist/%s-0.0.0-py3-none-any.whl" % name
                       if first_party_hash else "file:///repo/packages/%s" % name),
            "wheel_sha256": ("a" * 64) if first_party_hash else "",
        })
    for name in BOOTSTRAP:
        rows.append({"name": name, "version": "25.0", "editable": False,
                     "source": "", "wheel_sha256": ""})
    rows.extend({"name": n, "version": v, "editable": False,
                 "source": "", "wheel_sha256": ""} for n, v in extra)
    return {"dists": rows}


def run_checker(tmp_path, dists, lock_text=None):
    """跑检查器（注入模式），返回 (退出码, 结果 dict)。lock_text 可替换锁内容。"""
    fake = tmp_path / "installed.json"
    fake.write_text(json.dumps(dists), encoding="utf-8")
    lock_path = LOCK
    if lock_text is not None:
        lock_path = tmp_path / "custom.lock"
        lock_path.write_text(lock_text, encoding="utf-8")
    report = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--lock", str(lock_path),
         "--installed-json", str(fake), "--json-out", str(report)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert report.is_file(), "检查器未产出 JSON：%s" % (proc.stdout + proc.stderr)
    return proc.returncode, json.loads(report.read_text(encoding="utf-8"))


def failed_ids(result):
    return {r["id"].split()[0] for r in result["rows"] if r["status"] == "FAIL"}


# ---------------------------------------------------------------- 正向
def test_clean_environment_passes(tmp_path):
    rc, res = run_checker(tmp_path, build_dists())
    assert rc == 0, failed_ids(res)
    assert res["all_ok"] is True
    assert res["mode"] == "injected"


# ---------------------------------------------------------------- 负向（四类必测 + 重复）
def test_extra_package_fails(tmp_path):
    """多装一个包必须 FAIL——hook 会把它 collect 进制品。"""
    rc, res = run_checker(tmp_path, build_dists(extra=[("pytest", "8.3.0")]))
    assert rc == 1
    assert "C3" in failed_ids(res)


def test_missing_package_fails(tmp_path):
    rc, res = run_checker(tmp_path, build_dists(drop={"mcp"}))
    assert rc == 1
    assert "C2" in failed_ids(res)


def test_version_drift_fails(tmp_path):
    rc, res = run_checker(tmp_path, build_dists(override={"mcp": "2.2.0"}))
    assert rc == 1
    assert "C4" in failed_ids(res)


@pytest.mark.parametrize("pkg", FIRST_PARTY)
def test_first_party_editable_fails(tmp_path, pkg):
    rc, res = run_checker(tmp_path, build_dists(editable=[pkg]))
    assert rc == 1
    assert "C5" in failed_ids(res)


def test_first_party_missing_wheel_hash_is_gap_not_fail(tmp_path):
    """目录安装（有来源、无 wheel 哈希）→ C5 仍过，C5b 记 SKIP 缺口。

    这是分工的关键：只防 editable 防不了「装的是上次构建的旧 wheel」。
    缺口不能算产品失败（rc 仍 0），但必须在结果里看得见。
    """
    rc, res = run_checker(tmp_path, build_dists(first_party_hash=False))
    status = {r["id"].split()[0]: r["status"] for r in res["rows"]}
    assert rc == 0, "缺口不应被算成失败：%s" % failed_ids(res)
    assert status["C5"] == "PASS"
    assert status["C5b"] == "SKIP"
    c5b = next(r for r in res["rows"] if r["id"].startswith("C5b"))
    assert "无 wheel 哈希" in c5b["detail"]


def test_lock_with_first_party_leaks_layer_fails(tmp_path):
    """第一方包混进锁 → C2b FAIL。

    否则它会被当第三方静默比对版本，绕过 C5 的来源核对。
    """
    text = LOCK.read_text(encoding="utf-8")
    text += "\njobws-core==1.0.0 \\\n    --hash=sha256:%s\n" % ("a" * 64)
    rc, res = run_checker(tmp_path, build_dists(), lock_text=text)
    assert rc == 1
    assert "C2b" in failed_ids(res)


def test_duplicate_metadata_fails(tmp_path):
    dists = build_dists()
    dists["dists"].append({"name": "mcp", "version": "2.3.0", "editable": False})
    rc, res = run_checker(tmp_path, dists)
    assert rc == 1
    assert "C6" in failed_ids(res)


# ---------------------------------------------------------------- 锁自身完整性
def test_lock_matches_in_closure():
    """lock 与 .in 必须是**同一组**包与版本：手改 lock 而与输入脱节即失败。"""
    in_pins, lock = parse_pins(LOCK_IN.read_text(encoding="utf-8")), lock_pins()
    assert in_pins == lock, (
        "build-requirements.in 与 .lock 不一致："
        "仅 in 有=%s 仅 lock 有=%s 版本不同=%s" % (
            sorted(set(in_pins) - set(lock)),
            sorted(set(lock) - set(in_pins)),
            sorted(k for k in set(in_pins) & set(lock) if in_pins[k] != lock[k]),
        )
    )


def test_lock_pins_approved_certifi_baseline():
    """certifi 必须固定在已批准基线：版本升级要走独立门禁，不得随构建改进顺带生效。"""
    assert lock_pins().get("certifi") == "2026.10.19"


def test_every_lock_entry_has_hash():
    """每项都必须带至少一个 --hash：无 hash 的锁防不了同版本号的内容替换。"""
    text = LOCK.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^(?=[A-Za-z0-9_.\-]+==)", text)
    missing = []
    for block in blocks:
        m = re.match(r"^([A-Za-z0-9_.\-]+)==", block)
        if m and "--hash=sha256:" not in block:
            missing.append(m.group(1))
    assert not missing, "缺 hash 的包：%s" % missing


def test_build_script_calls_checker_not_duplicated_rules():
    """构建入口必须**调用**检查器，而不是自己再写一套规则（两套规则会漂移）。"""
    ps1 = (ROOT / "scripts" / "build_mcp_exe.ps1").read_text(encoding="utf-8")
    assert "check_mcp_build_environment.py" in ps1
    assert "build-requirements.lock" in ps1
