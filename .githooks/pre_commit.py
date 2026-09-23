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
  3. size budget - staged files only (CONTRIBUTING「规模预算」): logic files
     ≤300 lines, functions ≤80; stock exemptions in tools/size_allowlist.txt
     规模预算（只扫暂存文件）：与 CI 的 `jobws lint size` 共用同一实现
     （tools/check_size.py）——存量已登记（水位线只许变小），不误伤既有提交
  4. quick regression - pytest -q tests (skipped gracefully if env lacks pytest
     or its interpreter is below the 3.12 baseline)
     快速回归：全量 pytest（2026-09-20 实测 ≈25s / 934 条用例；随套件增长，耗时
     超过 TEST_SLOW_WARN_SECONDS 会在输出里点名阈值——见 CONTRIBUTING「测试规模
     与阈值」）；环境缺 pytest、或解释器低于基线（3.12）时降级为提示，不阻塞
     ——那种情况下结论本就不可信，CI 兜底

Emergency bypass / 紧急跳过: git commit --no-verify
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

HEADER = "pre-commit / 提交前校验"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 规模预算判定复用 tools/check_size.py——判定唯一实现：CI / 本地手跑 / 本钩子同源。
# **必须起别名**：本文件已有一个名为 check_size 的函数（>1MB 体积检查），模块级
# 定义会覆盖同名 import——直接 `import check_size` 会被它盖掉（初版就这么栽的）。
_TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
import check_size as size_budget  # noqa: E402
# 解释器基线：与 tests/conftest.py 的护栏同源（两处都改才算同步）
PY_BASELINE = (3, 12)
# 全量 pytest 的"动手阈值"：到点就该上并行/子集，而不是等到提交难受才想起来。
# 当前基线 ≈25s（2026-09-20 实测 934 条用例）；阈值 60s 与 CONTRIBUTING
# 「测试规模与阈值」同源——只提示、不阻断：让数字每次提交自己说话。
TEST_SLOW_WARN_SECONDS = 60
# pytest 的硬超时：没有上限时，一次挂起的测试会让提交永远卡在命令行里，
# 看起来像"还在跑"而不是"失败了"（2026-09-23 审计 P2）。到点即阻断并说清原因。
TEST_TIMEOUT_SECONDS = 900
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


def privacy_problem(paths: list[str], diff_text: str) -> str | None:
    """给定文件清单与 diff 文本做隐私判定（纯函数，本地钩子与 CI 共用同一份）。"""
    for path in paths:
        if PERSONAL_PATH_PATTERN.search(path):
            return f"staged file lives under personal/: {path}"
    added = "\n".join(line for line in diff_text.splitlines() if line.startswith("+"))
    for m in PHONE_PATTERN.finditer(added):
        number = m.group(0)
        if number in PLACEHOLDER_NUMBERS or len(set(number[3:])) == 1:
            continue  # 占位号（如 13800000000），非真实号码
        return f"possible real phone number in staged diff: {number} (use 13800000000-style placeholders)"
    for m in EMAIL_PATTERN.finditer(added):
        return f"possible real email in staged diff: {m.group(0)} (use sample@example.com)"
    return None


def check_privacy(files: list[str]) -> str | None:
    """本地入口：判定针对**暂存但未提交**的内容。

    只扫新增行（+）：删除/修正真实号码的「清理类提交」不应被自己的护栏拦死
    （独立审查抓出的自缚场景）。
    """
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return privacy_problem(files, diff)


def check_privacy_ci(base: str) -> str | None:
    """CI 入口（第二道闸）：用 PR 的完整 diff 复跑同一份判定。

    为什么还要在 CI 跑一遍：`--no-verify` 的存在是**有意保留**的逃生口，但它同时
    会跳过隐私护栏；无论本地怎么走，PR 里的那份 diff 都必须被同一个实现过一遍。

    两种必须显式失败而不能静默放行的情况（批末独立审查发现）：
    1. **base 取不到**（浅克隆里常见）——`git diff` 退出 128。以前没接住异常，
       结果不是"闸门拦下"而是"traceback 轰掉 CI job"；现在给出可执行的提示。
    2. **base 为空串**——`"%s...HEAD" % ""` 退化成一个点，diff 恒为空、判定恒过。
       空值一律当"没给"，回落到 origin/main。
    """
    base = (base or "").strip() or "origin/main"
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "%s^{commit}" % base],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if probe.returncode != 0:
            return ("取不到比对基线 `%s`——CI 里给 backend job 的 checkout 加 "
                    "fetch-depth: 0，或显式传 base" % base)
        diff_run = subprocess.run(
            ["git", "diff", "-U0", "%s...HEAD" % base],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
        paths_run = subprocess.run(
            ["git", "diff", "--name-only", "-z", "%s...HEAD" % base],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        return "git diff 失败（base=%s，exit=%s）：%s" % (base, exc.returncode, exc.stderr)
    return privacy_problem([p for p in paths_run.split("\0") if p], diff_run)


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


def check_size_budget() -> str | None:
    """规模预算（**只扫暂存文件**）：与 CI 的 `jobws lint size` 共用同一实现。

    为什么放在提交入口：规模超限是「看一眼就知道、但很容易忘了看」的那类
    问题——它不该等 CI 跑一轮才被指出。staged 模式只看本次要提交的文件，
    毫秒级；存量超标的文件都在 tools/size_allowlist.txt 登记过（水位线只许
    变小），因此这里不会误伤既有提交（2026-09-16 接入）。
    """
    problems = size_budget.scan(staged=True)
    if not problems:
        return None
    return ("规模预算超限（按职责拆分，或登记进 tools/size_allowlist.txt 并写清理由）:\n  "
            + "\n  ".join(problems))


def resolve_interpreter() -> str:
    """快检用哪个解释器：`JOBWS_PYTHON` > 仓库内 `.venv` > 运行钩子的解释器。

    git 调钩子用的是 `#!python`——本机很可能落到别的项目在用的环境（如 conda 3.8），
    所以不能默认信任 `sys.executable`：基线 3.12 之后，用低版本跑测验会得到**静默
    不可信**的结论（`tests/conftest.py` 会直接拦下，退出码 2）。这里只负责"找到对
    的那个"；找不到就在 `check_tests` 里降级提示，而不是让提交卡在一条看不懂的红上。
    """
    explicit = os.environ.get("JOBWS_PYTHON")
    if explicit:
        return explicit
    for candidate in (os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
                      os.path.join(REPO_ROOT, ".venv", "bin", "python")):
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def interpreter_version(python: str) -> tuple[int, ...] | None:
    """取解释器的主次版本；取不到（路径不存在/命令不可执行）返回 None。"""
    try:
        out = subprocess.run(
            [python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    parts = (out.stdout or "").strip().split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return (int(parts[0]), int(parts[1]))


def check_tests() -> str | None:
    """全量 pytest（当前 ≈25s；阈值提示见 TEST_SLOW_WARN_SECONDS）。

    环境缺 pytest/依赖时降级提示，CI 兜底。
    """
    python = resolve_interpreter()
    version = interpreter_version(python)
    if version is not None and version < PY_BASELINE:
        print("pytest: SKIP (解释器 %d.%d 低于基线 %d.%d：%s)"
              % (version[0], version[1], PY_BASELINE[0], PY_BASELINE[1], python))
        print("  设 JOBWS_PYTHON=<3.12 的 python> 可让钩子跑快检"
              "（维护者环境见 CONTRIBUTING「解释器基线」）；CI 会兜底。")
        return None
    started = time.monotonic()
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "tests", "-q", "--no-header"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # 卡住 ≠ 通过：这里的结论要么是"红"、要么是"不知道"，绝不能当作绿
        return ("pytest 超过 %ds 未完成（%s）——多半有用例挂在 IO / 网络上；"
                "修它，或临时用 --no-verify（后续必须回来重跑）"
                % (TEST_TIMEOUT_SECONDS, python))
    elapsed = time.monotonic() - started
    if result.returncode == 0:
        print("pytest: PASS (%s, %.1fs)" % (python, elapsed))
        if elapsed >= TEST_SLOW_WARN_SECONDS:
            print("  注意：全量已 %.0fs（阈值 %ds）——按 CONTRIBUTING「测试规模与阈值」"
                  "处理（先上 xdist，覆盖率不降）。" % (elapsed, TEST_SLOW_WARN_SECONDS))
        return None
    # 4 = 用法/路径错误，5 = 收集到 0 项，2 = 被中断（如解释器护栏拦下）：
    # 都是环境问题而非测试失败，降级提示（CI 兜底）
    if "No module named pytest" in (result.stderr or "") or result.returncode in (2, 4, 5):
        print(f"pytest: SKIP (rc={result.returncode}: environment/collection issue - CI will cover it)")
        return None
    tail = (result.stdout or result.stderr or "").strip().splitlines()[-3:]
    return "pytest failed:\n  " + "\n  ".join(tail)


def _force_utf8(stream) -> None:
    """把流切到 UTF-8——与 `tools/jobws.py` 同款处理。

    Windows 控制台默认 GBK，输出被管道接走时按 locale 编码，中文会变乱码
    （降级提示正是要给人看的，乱码就等于没说）。
    """
    if stream is None or not getattr(stream, "encoding", None):
        return
    if stream.encoding.lower() == "utf-8":
        return
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception as exc:  # 只影响显示层：说一声，不阻断（禁静默吞错）
        sys.stderr.write("note: stdout utf-8 switch failed (%s)\n" % exc)


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _force_utf8(sys.stdout)

    # CI 形态（`python .githooks/pre_commit.py --privacy-ci [base]`）：只跑隐私一项，
    # 且没有"已暂存"的概念，diff 取自基点到 HEAD
    if argv and argv[0] == "--privacy-ci":
        # 空串 == 没给（环境变量存在但为空时 `or` 才会兜住，这里统一成同一语义）
        base = (argv[1] if len(argv) > 1 else "") or os.environ.get("JOBWS_PRIVACY_BASE", "")
        problem = check_privacy_ci(base)
        if problem:
            print("[pre-commit][FAIL] privacy: %s" % problem)
            return 1
        print("privacy: OK（diff base=%s）" % base)
        return 0

    files = staged_files()
    print(f"--- pre-commit ({len(files)} staged files) ---")

    problems = []
    for name, fn in (("privacy", lambda: check_privacy(files)),
                     ("size", lambda: check_size(files)),
                     ("size-budget", check_size_budget),
                     ("tests", check_tests)):
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
