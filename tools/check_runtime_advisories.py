#!/usr/bin/env python3
"""运行时依赖的最低安全版本检查（2026-10-30 审计 §五）。

背景：`npm audit --omit=dev` 覆盖不到 Electron 本体——它落在 `devDependencies` 里
（Electron 项目的常规组织方式：构建工具下载它，安装包仍然随包分发运行时）。
「完整依赖」那条审计虽然覆盖到，但 `continue-on-error: true`，只报告不阻断。
于是**用户实际运行的运行时**（electron）可以悄悄落后于安全版本而 CI 全绿。

本脚本不联网、不做通用漏洞扫描，只钉住**已知的、有明确修复版本**的运行时基线；
新的 advisory 仍由 npm audit 的报告步骤暴露，升级后再把基线往上抬一行。

用法：`python tools/check_runtime_advisories.py`（exit 0 通过 / 1 低于基线 / 2 读不到锁）
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "web", "electron", "package-lock.json")

# 运行时包 → (最低安全版本, 说明)。加行时必须写清 advisory 与日期，
# 否则半年后没人知道这个数字从哪来。
BASELINE: Dict[str, Tuple[str, str]] = {
    "electron": (
        "44.9.1",
        "GHSA-jr5w-w6x2-84p9（2026-10-22，证书信任）：44 系列需 >= 44.9.1",
    ),
}


def _semver(text: str) -> Optional[Tuple[int, int, int]]:
    """只处理 `x.y.z`；`-beta.1` 这类后缀**乐观截断**（`44.9.1-beta.1` 当作 `44.9.1`）。

    这是刻意的宽松：本仓 lock 不会出现预发布（`devDependencies.electron` 是 `^44.9.1`
    这样的正式版范围），而「截断」只在极端情况下偏松（把 RC 当正式版放行），不会把
    正式版误判成 RC。若将来真锁了预发布，宁可手动确认，也不要让门禁随机红。
    """
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def locked_version(package: str, lock_path: str = LOCK) -> Optional[str]:
    """从 package-lock 的 `node_modules/<pkg>` 读锁定的版本。"""
    with open(lock_path, "r", encoding="utf-8") as f:
        lock = json.load(f)
    entry = (lock.get("packages") or {}).get("node_modules/" + package) or {}
    version = entry.get("version")
    return str(version) if version else None


def check(versions: Dict[str, Optional[str]], baseline: Dict[str, Tuple[str, str]] = None) -> List[str]:
    """返回问题列表（空 = 通过）。"""
    baseline = BASELINE if baseline is None else baseline
    problems: List[str] = []
    for package, (minimum, why) in baseline.items():
        actual = versions.get(package)
        if not actual:
            problems.append("%s：锁文件里找不到这个运行时（基线 %s）" % (package, minimum))
            continue
        have, want = _semver(actual), _semver(minimum)
        if have is None or want is None:
            problems.append("%s：版本号无法解析（锁 %r / 基线 %r）" % (package, actual, minimum))
        elif have < want:
            problems.append("%s %s < 最低安全版 %s —— %s" % (package, actual, minimum, why))
    return problems


def main() -> int:
    try:
        versions = {name: locked_version(name) for name in BASELINE}
    except (OSError, ValueError) as exc:
        print("check_runtime_advisories: 读不到 web/electron/package-lock.json：%s" % exc)
        return 2

    problems = check(versions)
    if problems:
        print("check_runtime_advisories: FAIL")
        for item in problems:
            print("  - " + item)
        print("\n修法：升 `devDependencies.electron` 到基线以上并重新生成 lock；"
              "同时到 CHANGELOG 记一条（用户运行时换了版本）。")
        return 1

    for package in sorted(BASELINE):
        print("check_runtime_advisories: OK  %s %s >= %s" % (package, versions[package], BASELINE[package][0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
