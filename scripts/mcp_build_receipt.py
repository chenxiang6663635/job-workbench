# -*- coding: utf-8 -*-
"""生成 MCP 运行时构建收据：把「这串哈希是由什么造出来的」写成可回查的 JSON。

为什么需要它（G4 构建合同 §4.5）：只记最终 exe 的哈希不够——出问题时无法回答
「这次构建用的是哪个 commit、哪个 setuptools、哪个 wheel」。尤其 `dirty` 字段：
一个带未提交改动的构建，其 `git_sha` 无法代表实际源码。

用法（由 build_mcp_exe.ps1 在 -FromLock 构建成功后调用）：
    python scripts/mcp_build_receipt.py --out <json> \
        --python <构建 venv 的 python> --lock <lock 路径> \
        --core-wheel <jobws_core-*.whl> --mcp-wheel <jobws_mcp-*.whl> \
        --exe <bin/jobws-mcp.exe> --manifest <prebuilds.json> [--from-lock]

退出码：0 写成功；2 读不到必需输入。
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args):
    """在仓库根跑 git；失败返回空串（不抛——收据不该因为 git 不可用而整体失败）。"""
    try:
        out = subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def probe(python, expr):
    """在目标解释器里求一个表达式，返回字符串；失败返回空串。"""
    try:
        out = subprocess.run([python, "-c", "print(%s)" % expr], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=60)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _pkg_version(python, name):
    return probe(python, "__import__('importlib.metadata', fromlist=['x']).version(%r)" % name)


def _source():
    status = git("status", "--porcelain")
    return {
        "git_sha": git("rev-parse", "HEAD"),
        # dirty 是关键：带未提交改动的构建，git_sha 无法代表实际源码
        "dirty": bool(status),
        "dirty_files": len(status.splitlines()) if status else 0,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def _interpreter(python, from_lock):
    return {
        "version": probe(python, "sys.version.split()[0]"),
        "executable": python,
        "declarative_venv": bool(from_lock),
    }


def _tools(python, from_lock):
    # 必须来自**构建 venv 自身**——--no-build-isolation 下它就是执行构建的那份
    return {
        "setuptools": _pkg_version(python, "setuptools"),
        "pip": _pkg_version(python, "pip"),
        "no_build_isolation": bool(from_lock),
    }


def _pem_sha(exe):
    pem = os.path.join(os.path.dirname(exe), "_internal", "certifi", "cacert.pem")
    return sha256(pem) if os.path.isfile(pem) else ""


def build_receipt(args, manifest):
    return {
        "schemaVersion": 1,
        "kind": "jobws-mcp-build-receipt",
        "source": _source(),
        "interpreter": _interpreter(args.python, args.from_lock),
        "dependencies": {
            "lock": os.path.abspath(args.lock),
            "lock_sha256": sha256(args.lock),
            "package_count": len(manifest.get("files") or {}),
        },
        "build_tools": _tools(args.python, args.from_lock),
        "first_party": {
            "jobws_core": {"path": os.path.abspath(args.core_wheel),
                           "sha256": sha256(args.core_wheel)},
            "jobws_mcp": {"path": os.path.abspath(args.mcp_wheel),
                          "sha256": sha256(args.mcp_wheel)},
        },
        "security_baseline": {
            "certifi": _pkg_version(args.python, "certifi"),
            "pem_sha256": _pem_sha(args.exe),
        },
        "artifact": {
            "exe": os.path.abspath(args.exe),
            "exe_sha256": sha256(args.exe),
            "manifest_sha256": sha256(args.manifest),
            "manifest_version": manifest.get("version"),
            "file_count": len(manifest.get("files") or {}),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--python", required=True, help="构建 venv 的解释器")
    ap.add_argument("--lock", required=True)
    ap.add_argument("--core-wheel", required=True)
    ap.add_argument("--mcp-wheel", required=True)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--from-lock", action="store_true",
                    help="本次是否由 -FromLock 从锁重建环境")
    args = ap.parse_args()

    for label, path in (("lock", args.lock), ("core-wheel", args.core_wheel),
                        ("mcp-wheel", args.mcp_wheel), ("exe", args.exe),
                        ("manifest", args.manifest)):
        if not os.path.isfile(path):
            print("FATAL 缺输入 %s: %s" % (label, path), file=sys.stderr)
            return 2

    manifest = json.load(io.open(args.manifest, encoding="utf-8"))
    receipt = build_receipt(args, manifest)

    with io.open(args.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")

    print("构建收据: %s" % args.out)
    print("  git=%s dirty=%s setuptools=%s exe=%s"
          % (receipt["source"]["git_sha"][:8] or "?",
             receipt["source"]["dirty"],
             receipt["build_tools"]["setuptools"] or "?",
             receipt["artifact"]["exe_sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
