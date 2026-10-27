# -*- coding: utf-8 -*-
"""MCP 构建环境判据（C1–C7）——纯函数，无 argv、无退出码。

从 `check_mcp_build_environment.py` 拆出（2026-10-27）：那个入口文件一度 309 行，
超过仓库的 300 行规模预算。按职责切一刀——判据留在这里，入口只管 CLI 与退出码。

为什么要独立成文件（而不是塞进入口）：同一套判据要被两处复用——
`build_mcp_exe.ps1` 的构建前门禁，以及 `tests/test_mcp_build_lock.py` 的负向测试。
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from importlib import metadata

FIRST_PARTY = ("jobws-core", "jobws-mcp")

# venv 引导工具：不在受控第三方集合内，允许存在（版本单独记录，不参与锁比对）。
# 刻意**不**把 setuptools / wheel / packaging 放进来——它们参与实际构建（hook 会 collect）。
BOOTSTRAP_ALLOWED = ("pip",)

EXPECT_PY = (3, 12)


def norm(name: str) -> str:
    """PEP 503 规范化：大小写、`-`/`_`/`.` 归一。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_lock(path: str) -> dict[str, str]:
    """解析 lock：返回 {规范化名: 版本}。忽略注释与 --hash 续行。"""
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+)", line)
            if m:
                out[norm(m.group(1))] = m.group(2)
    return out


def _dist_editable(dist) -> bool:
    """PEP 610：direct_url.json 的 dir_info.editable 为真 → editable 安装。"""
    try:
        raw = dist.read_text("direct_url.json")
    except Exception:  # noqa: BLE001 —— 元数据损坏按非 editable 记录，另有重复/来源判据兜底
        return False
    if not raw:
        return False
    try:
        return bool(json.loads(raw).get("dir_info", {}).get("editable"))
    except ValueError:
        return False


def _dist_source(dist) -> tuple[str, str]:
    """PEP 610 的 direct_url：返回 (来源 URL, wheel 的 sha256)。

    `pip install ./some/wheel.whl` → `archive_info.hash = "sha256=…"`（可核对）
    `pip install ./pkg`（目录）    → 只有 `dir_info`，**没有** wheel 哈希（记缺口）
    """
    try:
        raw = dist.read_text("direct_url.json")
    except Exception:  # noqa: BLE001
        return "", ""
    if not raw:
        return "", ""
    try:
        d = json.loads(raw)
    except ValueError:
        return "", ""
    h = str((d.get("archive_info") or {}).get("hash", ""))
    sha = h[len("sha256="):] if h.startswith("sha256=") else ""
    return str(d.get("url", "")), sha


def collect_installed() -> list[dict]:
    """读真实环境：返回 [{name, version, editable, source, wheel_sha256}]。

    允许重名（用于检出重复元数据）。
    """
    rows = []
    for dist in metadata.distributions():
        try:
            name = dist.metadata["Name"]
            version = dist.version
        except Exception:  # noqa: BLE001
            continue
        if not name:
            continue
        source, wheel_sha = _dist_source(dist)
        rows.append({
            "name": name,
            "version": version,
            "editable": _dist_editable(dist),
            "source": source,
            "wheel_sha256": wheel_sha,
        })
    return rows


def check_interpreter() -> dict:
    """C1：必须是 Windows x64 + CPython 3.12（与 lock 的 --python-platform 对齐）。"""
    ok = (
        sys.platform == "win32"
        and platform.machine().upper() in ("AMD64", "X86_64")
        and sys.version_info[:2] == EXPECT_PY
        and platform.python_implementation() == "CPython"
    )
    detail = "%s/%s CPython %d.%d (%s)" % (
        sys.platform, platform.machine(), sys.version_info[0], sys.version_info[1],
        platform.python_implementation(),
    )
    return {"id": "C1 解释器 = Windows x64 CPython 3.12", "status": "PASS" if ok else "FAIL", "detail": detail}


def check_sets(lock: dict[str, str], installed: list[dict]) -> list[dict]:
    """C2–C4、C6：缺包 / 多余包 / 版本错误 / 重复元数据。"""
    rows = []
    by_name: dict[str, list[dict]] = {}
    for d in installed:
        by_name.setdefault(norm(d["name"]), []).append(d)

    missing = sorted(set(lock) - set(by_name))
    extra = sorted(
        n for n in set(by_name) - set(lock)
        if n not in {norm(x) for x in FIRST_PARTY} and n not in {norm(x) for x in BOOTSTRAP_ALLOWED}
    )
    version_bad = sorted(
        "%s: 实际 %s != lock %s" % (n, by_name[n][0]["version"], lock[n])
        for n in set(lock) & set(by_name) if by_name[n][0]["version"] != lock[n]
    )
    dup = sorted(n for n, ds in by_name.items() if len(ds) > 1)

    # C2b：第一方包**必须不在锁里**（分层：第三方走锁，第一方走 wheel 身份）。
    # 若有人把 jobws-core 写进 .in，它会以"第三方"身份被静默比对版本，绕过 C5 的来源核对。
    leak = sorted(set(lock) & {norm(x) for x in FIRST_PARTY})
    rows.append({"id": "C2b 锁中不含第一方包（分层未被破坏）",
                 "status": "FAIL" if leak else "PASS",
                 "detail": "leaked=%s" % (leak or "无")})

    rows.append({"id": "C2 无缺失依赖（lock 有、venv 无）", "status": "FAIL" if missing else "PASS",
                 "detail": "missing=%s" % (missing or "无")})
    rows.append({"id": "C3 无多余依赖（venv 有、lock 无、非引导工具）", "status": "FAIL" if extra else "PASS",
                 "detail": "extra=%s" % (extra or "无")})
    rows.append({"id": "C4 版本与 lock 一致", "status": "FAIL" if version_bad else "PASS",
                 "detail": "drift=%s" % (version_bad or "无")})
    rows.append({"id": "C6 无重复包元数据", "status": "FAIL" if dup else "PASS",
                 "detail": "duplicates=%s" % (dup or "无")})
    return rows


def check_first_party(installed: list[dict]) -> list[dict]:
    """C5 + C5b：第一方包的存在/形态，以及**可审计身份**（版本 / 来源 / wheel 哈希）。

    C5（硬判据）：必须存在，且**非 editable**（editable 是链接树，不是制品来源）。
    C5b（缺口判据）：必须能指出这次装的是**哪个 wheel**。pip 安装本地 wheel 时，
    `direct_url.json` 里会有 `archive_info.hash = "sha256=…"`；目录安装（`pip install .`）
    只有 `dir_info`、**没有 wheel 哈希**——那种情况记 SKIP（缺口可见），不冒充通过。

    为什么 C5b 必要：只防 editable 防不了"装的是上一次构建的旧 wheel"。第一方包的
    版本号在开发期常常不变，光看版本号无法区分两次构建。
    """
    by_name: dict[str, list[dict]] = {}
    for d in installed:
        by_name.setdefault(norm(d["name"]), []).append(d)

    problems: list[str] = []
    audit: list[str] = []
    unverifiable: list[str] = []

    for fp in FIRST_PARTY:
        ds = by_name.get(norm(fp))
        if not ds:
            problems.append("%s 未安装" % fp)
            continue
        if any(d["editable"] for d in ds):
            problems.append("%s 是 editable 安装（必须是本次检出构建的 wheel）" % fp)
            continue

        d = ds[0]
        version = d.get("version", "")
        source = d.get("source", "")
        wheel_sha = d.get("wheel_sha256", "")
        if wheel_sha:
            audit.append("%s==%s wheel_sha256=%s…" % (fp, version, wheel_sha[:12]))
        elif source:
            unverifiable.append("%s==%s 来源=%s（无 wheel 哈希：疑似目录安装）"
                                % (fp, version, source[:60]))
        else:
            unverifiable.append("%s==%s 无 direct_url 记录（来源不可审计）" % (fp, version))

    rows = [
        {"id": "C5 第一方包非 editable 且存在",
         "status": "FAIL" if problems else "PASS",
         "detail": "; ".join(problems) or "ok"},
        # SKIP 不计入 failed（不误报产品失败），但会出现在结果里，缺口不会被读成全绿
        {"id": "C5b 第一方包 wheel 身份可审计",
         "status": "SKIP" if unverifiable else "PASS",
         "detail": "; ".join(unverifiable) if unverifiable else ("; ".join(audit) or "ok")},
    ]
    return rows


def check_pip() -> dict:
    """C7：pip check 无依赖冲突（无 pip 时记为 SKIP，不冒充 PASS）。"""
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "check"],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"id": "C7 pip check 无依赖冲突", "status": "SKIP", "detail": "无法执行: %s" % exc}
    if r.returncode == 0:
        return {"id": "C7 pip check 无依赖冲突", "status": "PASS", "detail": "ok"}
    return {"id": "C7 pip check 无依赖冲突", "status": "FAIL",
            "detail": (r.stdout + r.stderr).strip()[:400]}
