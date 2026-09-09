#!python
"""Repository pre-commit hook / 仓库级 pre-commit 校验脚本。

Adapted from the governance architecture of thermal_comfort_code (githooks pattern),
kept minimal for a single-maintainer product repo.
借鉴 thermal_comfort_code 的 hooks 治理模式，按单人产品仓库精简。

Checks:
  1. privacy guard - staged files must not touch personal/ or real-contact patterns
     隐私护栏：暂存文件不得触及 personal/ 或真实联系方式模式
  2. oversized files - no staged file > 1MB outside allowed binary dirs
     超大文件：白名单目录外不得新增 >1MB 文件
  3. quick regression - pytest -q tests (skipped gracefully if env lacks pytest)
     快速回归：全量 pytest 很快（<1s）；环境缺 pytest 时降级为提示，不阻塞

Emergency bypass / 紧急跳过: git commit --no-verify
"""

from __future__ import annotations

import re
import subprocess
import sys

HEADER = "pre-commit / 提交前校验"
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 占位号白名单：文档/模板里规范推荐的示例号（13800000000 是本项目 CONTRIBUTING 的占位示例）
PLACEHOLDER_NUMBERS = {"13800000000", "13800138000", "12345678901"}
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@(?:qq|163|126|gmail|outlook|hotmail)\.(?:com|net)", re.IGNORECASE)
PERSONAL_PATH_PATTERN = re.compile(r"(^|[\\/])personal([\\/]|$)")
BINARY_OK_PREFIXES = ("docs/screenshots/", "web/electron/icons/", "web/electron/release/", "docs/brand/")
MAX_FILE_BYTES = 1024 * 1024


def fail(msg: str) -> int:
    print(f"[pre-commit][FAIL] {msg}")
    print("Emergency bypass / 紧急跳过: git commit --no-verify")
    return 1


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def check_privacy(files: list[str]) -> str | None:
    """personal/ 路径与真实联系方式模式一律不得进提交。"""
    for path in files:
        if PERSONAL_PATH_PATTERN.search(path):
            return f"staged file lives under personal/: {path}"
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    for m in PHONE_PATTERN.finditer(diff):
        number = m.group(0)
        if number in PLACEHOLDER_NUMBERS or len(set(number[3:])) == 1:
            continue  # 占位号（如 13800000000），非真实号码
        return f"possible real phone number in staged diff: {number} (use 13800000000-style placeholders)"
    for m in EMAIL_PATTERN.finditer(diff):
        return f"possible real email in staged diff: {m.group(0)} (use sample@example.com)"
    return None


def check_size(files: list[str]) -> str | None:
    for path in files:
        if any(path.startswith(p) for p in BINARY_OK_PREFIXES):
            continue
        try:
            size = subprocess.run(
                ["git", "cat-file", "-s", f":{path}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if size and int(size) > MAX_FILE_BYTES:
                return f"staged file exceeds 1MB: {path} ({int(size) // 1024}KB) - use gitignore or move to an allowed dir"
        except (subprocess.CalledProcessError, ValueError):
            continue
    return None


def check_tests() -> str | None:
    """全量 pytest 很快（<1s）。环境缺 pytest/依赖时降级提示，CI 兜底。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--no-header"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        print("pytest: PASS")
        return None
    if "No module named pytest" in (result.stderr or ""):
        print("pytest: SKIP (not installed in this interpreter - CI will cover it)")
        return None
    tail = (result.stdout or result.stderr or "").strip().splitlines()[-3:]
    return "pytest failed:\n  " + "\n  ".join(tail)


def main() -> int:
    files = staged_files()
    print(f"--- pre-commit ({len(files)} staged files) ---")

    problems = []
    for name, fn in (("privacy", lambda: check_privacy(files)), ("size", lambda: check_size(files)), ("tests", check_tests)):
        problem = fn()
        print(f"{name}: {'FAIL' if problem else 'OK'}")
        if problem:
            problems.append((name, problem))

    if problems:
        for name, problem in problems:
            print(f"\n[pre-commit][FAIL] {name}: {problem}")
        print("Emergency bypass / 紧急跳过: git commit --no-verify")
        return 1
    print("pre-commit: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
