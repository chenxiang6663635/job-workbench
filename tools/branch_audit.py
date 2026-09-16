# -*- coding: utf-8 -*-
"""盘点本地分支的合并状态，回答「哪些可以删」。

**为什么不能直接用 git**：`main` 开的是 squash 合并，squash 会重写提交，
于是分支与 `main` 的 ancestry 永远对不上——`git branch --merged main` 一个都
认不出来，`git branch -d` 也会以「未合并」为由拒绝。分支看起来像还有用，
实际早已并入。2026-09-16 清账时本地就这样积了 26 个已合并分支。

**所以判据只有 PR 记录**（`merged: true`）。无 PR 的分支才回退到「头部提交
subject 是否已出现在 main」（squash 会把 PR 标题留作 subject，故可命中）。

只读、只报告、不删除——删的动作由人决定（见 CONTRIBUTING「合完就删分支」）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

# 远端 URL → owner/repo，避免把仓库名写死在脚本里
_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True,
    ).stdout


def owner_repo() -> tuple[str, str]:
    url = _git("remote", "get-url", "origin").strip()
    m = _REMOTE_RE.search(url)
    if not m:
        raise SystemExit(f"无法从 origin 解析出 owner/repo：{url}")
    return m.group("owner"), m.group("repo")


def _token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, check=True,
    ).stdout
    return next(
        (line.split("=", 1)[1] for line in out.splitlines()
         if line.startswith("password=")),
        "",
    )


def api(path: str):
    """经 curl 取 API（GitHub CLI 未登录时的可用通道）。失败返回 None。"""
    proc = subprocess.run(
        [
            "curl", "-s", "--max-time", "30",
            "-H", f"Authorization: Bearer {_token()}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28",
            f"https://api.github.com{path}",
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def local_branches(base: str) -> list[str]:
    out = _git("branch", "--format=%(refname:short)")
    return [b.strip() for b in out.splitlines() if b.strip() and b.strip() != base]


def head_subject(branch: str) -> str:
    return _git("log", "--format=%s", "-1", branch).strip()


def main() -> int:
    owner, repo = owner_repo()
    base = "main"
    base_subjects = {s.strip() for s in _git("log", "--format=%s", base).splitlines() if s.strip()}

    deletable: list[tuple[str, str]] = []
    review: list[tuple[str, str]] = []
    keep: list[tuple[str, str]] = []

    for branch in local_branches(base):
        prs = api(f"/repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=all&per_page=5")
        if prs is None:
            review.append((branch, "查询 PR 失败（网络/凭据），未判定"))
            continue

        if prs:
            number = prs[0]["number"]
            detail = api(f"/repos/{owner}/{repo}/pulls/{number}")
            if detail is None:
                review.append((branch, f"PR#{number} 详情查询失败"))
            elif detail.get("merged"):
                deletable.append((branch, f"PR#{number} 已合并"))
            elif detail.get("state") == "closed":
                review.append((branch, f"PR#{number} 已关闭但未合并"))
            else:
                keep.append((branch, f"PR#{number} 仍开启"))
            continue

        # 无 PR：回退到 subject 比对
        if head_subject(branch) in base_subjects:
            deletable.append((branch, f"无 PR，但头部提交 subject 已在 {base}"))
        else:
            keep.append((branch, f"无 PR 且提交不在 {base}"))

    def show(title: str, rows: list[tuple[str, str]]) -> None:
        print(f"\n=== {title} ({len(rows)}) ===")
        for name, why in sorted(rows):
            print(f"  {name:42s} {why}")

    show("可安全删除", deletable)
    show("需人工确认", review)
    show("保留", keep)

    if deletable:
        print("\n确认后删除（-D：squash 场景下 -d 必然误判为未合并）：")
        print("  git branch -D " + " ".join(n for n, _ in sorted(deletable)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

