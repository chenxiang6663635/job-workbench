# -*- coding: utf-8 -*-
"""MCP 构建环境准入检查（MCP Build Lock Contract v1 的 CLI 入口）。

判据本身在 `mcp_build_env_checks.py`（纯函数）；本文件只管 argparse、打印与退出码。
拆分原因：合并后本文件曾达 309 行，超出 300 行规模预算——按职责切分，入口变薄。

为什么判据要独立于 PowerShell：同一套规则被构建入口与负向测试复用。
若写在 PowerShell 里，测试只能"扫描脚本里有没有关键字"，那是假测试。

为什么是**集合相等**而不是 `LOCK ⊆ INSTALLED`：
  「该有的都有」不保证「不该有的没有」。PyInstaller 的 hook 会把 venv 里
  顺手装的包 collect 进制品（`setuptools` 就是这样进的），所以多余包必须 FAIL。

用法：
  python scripts/check_mcp_build_environment.py --lock mcp/build-requirements.lock
  python scripts/check_mcp_build_environment.py --lock ... --installed-json fake.json
    加 --installed-json 即「注入模式」：不读真实环境、不查解释器/pip check，
    仅评估集合判据——供测试构造违规组合。

退出码（三态，2026-10-27 收紧）：
  0  全 PASS
  1  有 FAIL；或 `--strict` 下出现缺口（SKIP）
  3  无 FAIL 但有缺口（SKIP）——日常检查可见、不阻断
构建入口用 `--strict`：缺口（如第一方包无 wheel 哈希、无 pip）即拒绝产出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# scripts/ 不是包；用入口自身所在目录做导入根，避免依赖调用方的 cwd。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_build_env_checks import (  # noqa: E402  —— 必须在 sys.path 调整之后
    check_first_party,
    check_interpreter,
    check_pip,
    check_sets,
    collect_installed,
    load_lock,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", required=True)
    ap.add_argument("--installed-json", default="", help="注入已安装集合（测试用）；给出则跳过真实环境判据")
    ap.add_argument("--json-out", default="", help="把结果写成 JSON")
    ap.add_argument("--strict", action="store_true",
                    help="把 SKIP 缺口也算失败（构建入口用；G4 签署要求签署版无缺口）")
    args = ap.parse_args()

    lock = load_lock(args.lock)
    injected = bool(args.installed_json)
    if injected:
        with open(args.installed_json, encoding="utf-8") as fh:
            installed = json.load(fh)["dists"]
    else:
        installed = collect_installed()

    rows = []
    if not injected:
        rows.append(check_interpreter())
    rows.extend(check_sets(lock, installed))
    rows.extend(check_first_party(installed))
    if not injected:
        rows.append(check_pip())

    failed = [r for r in rows if r["status"] == "FAIL"]
    gaps = [r for r in rows if r["status"] == "SKIP"]

    # 三态退出码（2026-10-27 收紧）：SKIP 表示「某项强制证据没拿到」，它不该静默通过。
    #   0 = 全 PASS
    #   3 = 无 FAIL 但有缺口（SKIP）——日常检查可见、不阻断
    #   1 = 有 FAIL，或 --strict 下出现缺口（构建入口用 strict，故缺口 = 拒绝产出）
    # 为什么需要 strict：G4 要签「第一方构建来源完整可追溯」时，C5b 无 wheel 哈希、
    # C7 无 pip 这类缺口不能以 SKIP 混进签署版结论。
    if failed:
       code = 1
    elif gaps and args.strict:
       code = 1
    elif gaps:
       code = 3
    else:
       code = 0

    result = {"mode": "injected" if injected else "real", "lock": args.lock,
             "lock_packages": len(lock), "installed_dists": len(installed),
             "rows": rows, "failed": len(failed), "gaps": len(gaps),
             "strict": bool(args.strict),
             "all_ok": code == 0, "exit_code": code}

    print("MCP 构建环境准入检查（lock 包数=%d，venv 分布数=%d%s）"
         % (len(lock), len(installed), "，strict" if args.strict else ""))
    for r in rows:
       print("  [%-4s] %s — %s" % (r["status"], r["id"], str(r["detail"])[:150]))
    if failed:
       print("结论：FAIL（%d 项失败）" % len(failed))
    elif gaps:
       print("结论：%s（%d 项缺口）"
             % ("FAIL — strict 下缺口不允许通过" if args.strict else "PASS_WITH_GAPS", len(gaps)))
    else:
       print("结论：PASS")

    if args.json_out:
       with open(args.json_out, "w", encoding="utf-8", newline="") as fh:
           fh.write(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
