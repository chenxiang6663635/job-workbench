#!/usr/bin/env python3
"""发布物版本一致性检查（2026-10-30 审计 §四）。

为什么需要它：历史 tag 上真发生过漂移——`v26.9.0` 的 `package.json` 是 `26.9.0`
而 `package-lock.json` 顶层是 `26.9.15`；`v26.10.0` / `v26.10.1` 的 lock 顶层停在
`26.9.0`。installer 的实际版本由打包配置决定，所以那次没把包装坏；但只要漂移继续
存在，「6 处同号」就只能靠维护者记性。

这里把「应用版本」当唯一真源，其它四处必须逐字相等：

    web/electron/package.json          version
    web/electron/package-lock.json     version（顶层）
    web/electron/package-lock.json     packages[""].version
    integrations/dsh/package.json      version（npm 主包）
    integrations/dsh/platform/win32-x64/package.json  version（平台子包）

另有两条已在别处把关、本脚本不重复：`tools/assets_registry.py --check`（插件壳 /
marketplace 清单 vs 真源）与 `python tools/jobws.py skills check`（9 个技能 metadata）。

用法：`python tools/check_release_versions.py`（exit 0 通过 / 1 不一致 / 2 文件缺失）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP = "web/electron/package.json"
LOCK = "web/electron/package-lock.json"
DSH_MAIN = "integrations/dsh/package.json"
DSH_PLATFORM = "integrations/dsh/platform/win32-x64/package.json"


def _load(rel: str) -> dict:
    path = os.path.join(ROOT, rel)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect() -> Dict[str, str]:
    """读出五处版本号；缺文件会抛 OSError / ValueError，由调用方转成 exit 2。"""
    app = _load(APP)
    lock = _load(LOCK)
    root_pkg = (lock.get("packages") or {}).get("") or {}
    return {
        APP: str(app.get("version") or ""),
        LOCK + " (top)": str(lock.get("version") or ""),
        LOCK + ' (packages[""])': str(root_pkg.get("version") or ""),
        DSH_MAIN: str(_load(DSH_MAIN).get("version") or ""),
        DSH_PLATFORM: str(_load(DSH_PLATFORM).get("version") or ""),
    }


def check(versions: Dict[str, str]) -> List[str]:
    """返回不一致项（空列表 = 通过）。第一条（应用版本）是真源，其余必须与之相等。"""
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
    return problems


def main() -> int:
    try:
        versions = collect()
    except (OSError, ValueError) as exc:
        print("check_release_versions: 读不到版本文件：%s" % exc)
        return 2

    problems = check(versions)
    if problems:
        print("check_release_versions: FAIL（%d 处不一致，真源 = %s）" % (len(problems), APP))
        for item in problems:
            print("  - " + item)
        print("\n修法：把上面每一处都改成与 %s 相同的号（落章时一并改，别分两次）。" % APP)
        return 1

    print("check_release_versions: OK（5 处同号 = %s）" % versions[APP])
    return 0


if __name__ == "__main__":
    sys.exit(main())
