#!python
"""Repository commit-msg hook / 提交信息规范校验。

校验格式 type(scope): subject；豁免 git 自动生成的 Merge/Revert。
subject 必须中文（本仓库提交信息与 PR 标题一律中文）。

判定逻辑在 tools/commit_header.py ——与 CI 校验 PR 标题用的是同一份实现。
PR 标题在 squash 合并后会直接成为主干上的提交 subject，两处必须同源，
否则「本地中文、主干英文」的混排会再次出现。

注意：本钩子**不**提示 --no-verify。它管的是文案，为一句文案去跳过整条钩子链
（连带跳过 pre-commit 的隐私护栏）是反向激励；紧急绕过的方式写在 CONTRIBUTING，
不该由报错信息主动教。

Adapted from thermal_comfort_code's commit-msg governance, simplified.
"""

from __future__ import annotations

import locale
import os
import sys

# 钩子可能在任何 Python 环境下执行，这里只依赖标准库
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))

try:
    import commit_header  # noqa: E402
except ImportError:
    # 共享模块缺失或改名时降级为提示而不是抛栈：钩子自身坏掉不该让人无法提交
    # （同理 pre-commit 在缺 pytest 时降级）。真正的兜底在 CI。
    commit_header = None


def _first_line(text: str) -> str:
    if text.startswith("\ufeff"):  # 容忍 BOM：部分编辑器写 UTF-8-BOM 会破坏首行正则
        text = text[1:]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return ""


def read_message(path: str):
    """读取提交信息文件，返回 (首行, 错误说明)。

    编码这里必须较真：中文 Windows 的编辑器/终端可能把 COMMIT_EDITMSG 写成 GBK。
    原来直接 `errors="replace"` 会静默把中文换成 U+FFFD，于是校验器给出
    「subject 必须含中文」这种**误导性**结论——作者明明写了中文，却被指没写；
    而且它同时是静默的数据损坏（违反「禁静默吞错」）。
    改为按序尝试 UTF-8 → 系统首选编码，都不行就明确报编码错误，不再猜。
    """
    with open(path, "rb") as fh:
        raw_bytes = fh.read()

    tried = []
    # 固定把 gb18030 放进回退链，而不是只依赖「系统首选编码」：钩子跑在哪个平台
    # 不该改变判定结果（Linux CI 上首选就是 UTF-8，那样 GBK 文件会被误判为坏文件）。
    # gb18030 是 GBK/CP936 的超集，覆盖中文 Windows 的真实场景。
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gb18030"):
        if encoding.lower() in tried:  # 首选就是 UTF-8 时不必试两遍
            continue
        tried.append(encoding.lower())
        try:
            return _first_line(raw_bytes.decode(encoding)), None
        except UnicodeDecodeError:
            continue
    return "", ("提交信息不是 UTF-8 / %s / gb18030 能解析的编码，无法读取首行\n"
                "  请把编辑器或终端改成 UTF-8 后重试"
                % locale.getpreferredencoding(False))


def main(argv: list) -> int:
    if not argv:
        print("[commit-msg][FAIL] missing message file argument")
        return 1

    message, encoding_error = read_message(argv[0])
    if encoding_error:
        print("[commit-msg][FAIL] %s" % encoding_error)
        return 1
    if not message:
        print("[commit-msg][FAIL] commit message is empty")
        return 1
    if commit_header is None:
        print("[commit-msg][SKIP] 找不到 tools/commit_header.py，跳过提交信息校验")
        print("  （仓库文件缺失或已改名；CI 的 PR 标题校验仍会兜底）")
        return 0

    problems = commit_header.validate(message)
    if problems:
        for problem in problems:
            print("[commit-msg][FAIL] %s" % problem)
        print("  改文案即可——这条只关乎措辞，不关乎代码。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
