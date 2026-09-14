# -*- coding: utf-8 -*-
"""跨宿主双轨审查：把「作者自审 + 独立零上下文审查」的第二轨固化成可复现脚本。

CONTRIBUTING 的流程门禁要求每批 PR 做双轨审查，其中第二轨必须是**全新上下文**
的审查方。在 CodeBuddy 里用 Task 子代理最方便；换到 Claude Code / Codex / 纯 CLI
时这条轨道就断了。本脚本把协议层固定下来：**同一份提示词、同一份 diff、任意
一个装好的第二宿主 CLI**，都能跑出结构化的 findings。

用法：

    python scripts/review.py                      # 自动探测第二宿主，审 main...HEAD
    python scripts/review.py --base <ref> --head <ref>
    python scripts/review.py --host claude        # 指定宿主：claude / codex
    python scripts/review.py --dry-run            # 只准备 diff 与提示词，不调宿主

原理（四个刻意选择）：

- **不把 diff 喂进命令行**：大 diff 会被入参上限截断，审查方拿到的必须是完整
  改动。脚本先把 `git diff base...head -U10` 落成 `tmp_review_diff.patch`
  （根目录 tmp_ 前缀，已 gitignore），提示词里给它**路径**，让审查方自己读。
- **提示词是资产不是即兴**：模板在 `scripts/review_prompt.md`，与 CodeBuddy
  子代理轨用的是同一套判据——跨宿主也仍然是「同一条轨道」。
- **提示词也走文件**：渲染后的提示词落盘 `tmp_review_prompt.md`，命令行只带
  一行 ASCII 导航语。实证（2026-09-14）：Windows 上 codex 常是 npm 的
  `.CMD` 包装，多行参数会被 cmd.exe 在第一个换行处截断——审查方只收到标题
  一行；文件导航同时躲开这个坑与 cmd 代码页对中文参数的影响。
- **只读**：脚本只跑只读 git 子命令（`rev-parse` / `diff` / `log`），绝不
  checkout / reset / stash——审查不该改变被审查的工作区。

边界（诚实声明）：

- 独立性来自**上下文隔离**（全新会话、不带本轮结论）；要模型多样性就换宿主。
- 第二宿主 CLI 需自行安装并登录；本机实测 claude / codex 均可用（copilot 未接）。
  **改动任一宿主分支后都要实跑一次**——两个分支的坑不同（.CMD 参数截断就是
  只在实跑时暴露的那类）。
- codex 分支默认 `--ignore-user-config`：审查要确定性，且用户 config.toml 的
  版本不兼容字段（如 `service_tier`）不该卡住门禁；auth 走 CODEX_HOME 不受影响。
- 输出是**审查意见**，采纳与否由作者判断——与子代理轨同一条纪律：findings 可
  记录「不采纳 + 理由」，不许静默忽略 MAJOR。

退出码：0 审查完成；1 无法探测宿主 / 命令失败；2 用法错误。
"""

from __future__ import print_function

import argparse
import os
import shutil
import subprocess
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_FILE = os.path.join(ROOT, "scripts", "review_prompt.md")
DIFF_FILE = os.path.join(ROOT, "tmp_review_diff.patch")
PROMPT_OUT = os.path.join(ROOT, "tmp_review_prompt.md")


def _git(args):
    """只读 git 子命令。审查脚本绝不改变工作区状态（见模块 docstring）。"""
    result = subprocess.run(["git", "-C", ROOT] + args,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError("git %s 失败：%s"
                           % (" ".join(args), result.stderr.decode("utf-8", "replace").strip()))
    return result.stdout.decode("utf-8", "replace")


def _prepare(base, head):
    """生成 diff 文件与渲染后的提示词；不做任何写仓库的动作（tmp_ 例外，已 gitignore）。"""
    diff_text = _git(["diff", "%s...%s" % (base, head), "-U10"])
    with open(DIFF_FILE, "w", encoding="utf-8") as handle:
        handle.write(diff_text)

    with open(PROMPT_FILE, "r", encoding="utf-8") as handle:
        prompt = handle.read()
    replacements = {
        "{{REPO}}": os.path.abspath(ROOT),
        "{{DIFF_FILE}}": DIFF_FILE,
        "{{BASE}}": base,
        "{{HEAD}}": head,
        "{{COMMITS}}": _git(["log", "--oneline", "%s..%s" % (base, head)]).strip() or "（无）",
        "{{FILES}}": _git(["diff", "--name-only", "%s...%s" % (base, head)]).strip() or "（无）",
    }
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    with open(PROMPT_OUT, "w", encoding="utf-8") as handle:
        handle.write(prompt)
    return prompt, len(diff_text)


# 两个宿主都走「文件导航」：提示词已落盘（PROMPT_OUT），命令行只带一行 ASCII
# 导航语（含换行的长参数会被 `.CMD` 包装截断、中文参数会受 cmd 代码页影响）。
_NAV = "Read the file at %s and follow its instructions." % os.path.relpath(PROMPT_OUT, ROOT)


def _claude_cmd(exe):
    # Read/Grep/Glob 足够：读提示词、读 diff、读源码（不给 Bash——只读排查由此保证）
    return [exe, "-p", _NAV, "--allowedTools", "Read", "Grep", "Glob",
            "--output-format", "text"]


def _codex_cmd(exe):
    return [exe, "exec", "-s", "read-only", "-C", ROOT,
            "--skip-git-repo-check", "--ephemeral", "--ignore-user-config", _NAV]


HOSTS = [("claude", _claude_cmd), ("codex", _codex_cmd)]


def _pick_host(preferred):
    """返回 (名字, 可执行文件全路径, 命令构造函数)。"""
    order = [pair for pair in HOSTS if not preferred or pair[0] == preferred]
    for name, build in order:
        exe = shutil.which(name)
        if exe:
            return name, exe, build
    return None


def main():
    parser = argparse.ArgumentParser(description="跨宿主双轨审查（第二轨）")
    parser.add_argument("--base", default="main", help="审查起点（默认 main）")
    parser.add_argument("--head", default="HEAD", help="审查终点（默认 HEAD）")
    parser.add_argument("--host", choices=[name for name, _ in HOSTS], default=None,
                        help="第二宿主（默认自动探测：claude > codex）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只准备 diff 与提示词并打印，不调用宿主")
    args = parser.parse_args()

    # Windows 控制台默认 GBK：中文输出会被打成乱码（与 scripts/smoke_backend_exe.py 同款处理）
    if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
        if sys.stdout.encoding.lower() != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

    try:
        prompt, diff_size = _prepare(args.base, args.head)
    except RuntimeError as exc:
        print("错误：%s" % exc)
        return 1
    if diff_size == 0:
        print("范围 %s...%s 的 diff 为空——没有需要审查的改动。" % (args.base, args.head))
        return 1

    picked = _pick_host(args.host)
    if picked is None:
        print("错误：找不到第二宿主 CLI（需要 claude 或 codex 在 PATH 上）。")
        print("装好其中一个再跑；或 --host claude/codex 指定。")
        return 1
    name, exe, build = picked

    print("diff 已落盘：%s（%d 字节）" % (DIFF_FILE, diff_size))
    print("提示词已落盘：%s" % PROMPT_OUT)
    print("第二宿主：%s（%s）" % (name, exe))
    if args.dry_run:
        print("--- 提示词（已落盘；命令行只传一行导航语）---")
        print(prompt)
        print("--- dry-run 结束：未调用宿主 ---")
        return 0

    print("开始独立审查（只读；输出即时可见）…")
    proc = subprocess.run(build(exe), cwd=ROOT)
    if proc.returncode != 0:
        print("宿主退出码 %d——审查未完成。" % proc.returncode)
        return 1
    print("审查结束。findings 请按 CONTRIBUTING 的双轨纪律记录进 PR。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
