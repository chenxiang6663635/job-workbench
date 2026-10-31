#!/usr/bin/env python3
"""发布物版本一致性检查（2026-10-30 审计 §四；2026-10-31 改为按结构扫描）。

为什么需要它：历史 tag 上真发生过漂移——`v26.9.0` 的 `package.json` 是 `26.9.0`
而 `package-lock.json` 顶层是 `26.9.15`；`v26.10.0` / `v26.10.1` 的 lock 顶层停在
`26.9.0`。installer 的实际版本由打包配置决定，所以那次没把包装坏；但只要漂移继续
存在，「多处同号」就只能靠维护者记性。

**为什么改成结构扫描**：第一版把位置写死成「5 个读取点」，于是 `integrations/dsh/
package.json` 的 `optionalDependencies["dsh-job-workbench-win32-x64"]` 被漏掉——
落章后主包会去取旧子包，而所有门禁全绿（2026-10-31 审计发现 1）。手抄的清单必然
漏下一位新增的位置，所以现在：

1. 以 `web/electron/package.json` 的 version 为唯一真源；
2. `web/electron/package-lock.json` 的顶层与 `packages[""].version` 必须相等；
3. 仓库内**每一个** `package.json` 的 `version` 必须相等；
4. 这些包互相之间的依赖声明（`dependencies` / `devDependencies` /
   `optionalDependencies` / `peerDependencies` 里指向本仓包名的）必须是**精确版本**
   且与真源相等——范围符（`^`/`~`/`>=`）一律报错，因为发行合同要求「主包与子包同版」。

用法：`python tools/check_release_versions.py`（exit 0 通过 / 1 不一致 / 2 文件缺失）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP = "web/electron/package.json"
LOCK = "web/electron/package-lock.json"
DSH_MAIN = "integrations/dsh/package.json"
DSH_PLATFORM = "integrations/dsh/platform/win32-x64/package.json"
PACKAGE_FILES = [APP, DSH_MAIN, DSH_PLATFORM]
DEP_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
_RANGE_PREFIXES = ("^", "~", ">", "<", "*", "=", "workspace:", "file:", "link:")


def _load(rel: str) -> dict:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return json.load(f)


def collect() -> Tuple[Dict[str, str], Dict[str, str]]:
    """返回 (版本表, 依赖声明表)。

    版本表：标签 → 版本字符串（标签要能读出来才知道该改哪里）。
    依赖声明表：标签 → 声明的 spec（可能是 `^26.10.0` 这种范围，需要单独判）。
    """
    versions: Dict[str, str] = {}
    specs: Dict[str, str] = {}

    packages = {rel: _load(rel) for rel in PACKAGE_FILES}
    local_names = {pkg.get("name") for pkg in packages.values() if pkg.get("name")}

    app_pkg = packages[APP]
    versions[APP] = str(app_pkg.get("version") or "")

    lock = _load(LOCK)
    versions[LOCK + " (top)"] = str(lock.get("version") or "")
    root_pkg = (lock.get("packages") or {}).get("") or {}
    versions[LOCK + ' (packages[""])'] = str(root_pkg.get("version") or "")

    for rel, pkg in packages.items():
        if rel != APP:
            versions[rel] = str(pkg.get("version") or "")
        for section in DEP_SECTIONS:
            for dep, spec in (pkg.get(section) or {}).items():
                if dep not in local_names or dep == pkg.get("name"):
                    continue
                specs["%s → %s.%s" % (rel, section, dep)] = str(spec)

    return versions, specs


def check(versions: Dict[str, str], specs: Dict[str, str] = None) -> List[str]:
    """返回问题列表（空 = 通过）。第一条（应用版本）是真源，其余必须与之相等。"""
    specs = specs or {}
    expected = versions.get(APP, "")
    problems: List[str] = []
    if not expected:
        problems.append("%s 没有 version 字段" % APP)
        return problems

    for path, value in versions.items():
        if path == APP:
            continue
        if not value:
            problems.append("%s 没有 version 字段" % path)
        elif value != expected:
            problems.append("%s = %s（期望 %s）" % (path, value, expected))

    for path, spec in specs.items():
        if spec.startswith(_RANGE_PREFIXES):
            problems.append("%s = %r 不是精确版本（发行要求主包与子包同版，用 %s）"
                            % (path, spec, expected))
        elif spec != expected:
            problems.append("%s = %s（期望 %s）" % (path, spec, expected))

    return problems


def main() -> int:
    try:
        versions, specs = collect()
    except (OSError, ValueError) as exc:
        print("check_release_versions: 读不到版本文件：%s" % exc)
        return 2

    problems = check(versions, specs)
    if problems:
        print("check_release_versions: FAIL（%d 处不一致，真源 = %s）" % (len(problems), APP))
        for item in problems:
            print("  - " + item)
        print("\n修法：把上面每一处都改成与 %s 相同的号（落章时一并改，别分两次）。" % APP)
        return 1

    total = len(versions) + len(specs)
    print("check_release_versions: OK（%d 处同号 = %s：%d 个 version + %d 条内部依赖声明）"
          % (total, versions[APP], len(versions), len(specs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
