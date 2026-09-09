#!python
"""Repository commit-msg hook / 提交信息规范校验。

Enforces Conventional Commits headers: type(scope): subject
校验格式 type(scope): subject；豁免 git 自动生成的 Merge/Revert。
subject 允许中文（本仓库提交信息以中文为主）。

Adapted from thermal_comfort_code's commit-msg governance, simplified.
"""

from __future__ import annotations

import re
import sys

TYPES = {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"}
HEADER_PATTERN = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9][a-z0-9_/-]*)\))?: (?P<subject>\S.*)$")


def first_meaningful_line(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    if raw.startswith("\ufeff"):  # 容忍 BOM：部分编辑器写 UTF-8-BOM 会破坏首行正则
        raw = raw[1:]
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return ""


def main(argv: list[str]) -> int:
    if not argv:
        print("[commit-msg][FAIL] missing message file argument")
        return 1
    message = first_meaningful_line(argv[0])
    if not message:
        print("[commit-msg][FAIL] commit message is empty")
        return 1
    if message.startswith(("Merge ", "Revert ", "Initial commit")):
        return 0

    match = HEADER_PATTERN.match(message)
    if not match:
        print(f"[commit-msg][FAIL] header must be 'type(scope): subject' - got: {message}")
        print(f"  allowed types: {', '.join(sorted(TYPES))}")
        return 1
    if match.group("type") not in TYPES:
        print(f"[commit-msg][FAIL] unknown type '{match.group('type')}' - allowed: {', '.join(sorted(TYPES))}")
        return 1
    if len(message) > 100:
        print(f"[commit-msg][FAIL] header longer than 100 chars ({len(message)}) - move detail to the body")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
