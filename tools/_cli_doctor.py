# -*- coding: utf-8 -*-
"""`jobws doctor`：数据根的三态体检（A2）。

呈现分工（spec §五）：CLI / API / MCP / 设置页**只做序列化与呈现**——本命令
不自己算任何东西，`jobws_core.dataroot.describe()` 是唯一事实源（`jobws.info`
与 `/api/system/paths` 的 `dataRootDiagnostic` 读的是同一份对象）。

退出码（A2 契约）：
- `unavailable` → 非零（失效：读 / 写 / 破坏性全部拒绝的机器可读信号）；
- `ambiguous` / `uninitialized` / `ok` → 0（状态从输出读出——ambiguous 是告警
  「读仍可用」，uninitialized 是正常首启，都不该让脚本失败）。

用法：
    python tools/jobws.py doctor            # 人读版（中文）
    python tools/jobws.py doctor --json     # ResolvedDataRootDiagnostic 的 JSON

CLI 文案刻意不走 i18n（CLI 不是界面）；跨端一致性由 `docs/four-ends.md` 的
能力矩阵与诊断对象的字段契约保证。
"""
from __future__ import print_function

import argparse
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from jobws_core import dataroot, pathres  # noqa: E402

# 直跑本文件（不经 jobws 入口）也要能定位应用根；已注入时不动。
pathres.set_app_root_if_unset(os.path.dirname(_TOOLS_DIR))

_STATE_LABELS = {
    dataroot.STATE_OK: "正常（ok）",
    dataroot.STATE_AMBIGUOUS: "有歧义（ambiguous）——读可用，破坏性操作会被拒绝",
    dataroot.STATE_UNINITIALIZED: "未初始化（uninitialized）——还没有工作区，正常首启",
    dataroot.STATE_UNAVAILABLE: "失效（unavailable）——持久化选择指向不可用的位置，读写被拒绝",
}


def _workspace_name():
    """当前工作区目录名：`JOBWS_WORKSPACE` 优先，缺省 `personal`（与各端同口径）。"""
    return (os.environ.get("JOBWS_WORKSPACE") or "").strip() or dataroot.DEFAULT_WORKSPACE_NAME


def _print_human(diag):
    """人读版：状态、根、来源、工作区、持久化选择与候选清单。"""
    print("数据根诊断（三态）：%s" % _STATE_LABELS.get(diag["state"], diag["state"]))
    print("- 数据根：%s" % diag["path"])
    print("- 来源：%s；形态：%s；可写：%s" % (
        diag["source"], diag["form"], "是" if diag["writable"] else "否"))
    ws = os.path.join(diag["path"], _workspace_name())
    print("- 当前工作区：%s（%s）" % (ws, "已建" if os.path.exists(ws) else "未建"))
    sel = diag["persisted_selection"]
    if sel is None:
        print("- 持久化选择：未设置")
    else:
        print("- 持久化选择：%s（%s%s）" % (
            sel["path"] or "（读取失败）",
            "可读" if sel["readable"] else "不可读，按未设置处理",
            "，被 env 遮蔽" if sel["shadowed_by"] == "env" else ""))
    if diag["legacy_candidates"]:
        print("- 候选根：")
        for cand in diag["legacy_candidates"]:
            print("    %s（%s）" % (
                cand["path"], "含工作区" if cand["has_workspace"] else "无工作区"))
    if diag["state"] == dataroot.STATE_UNAVAILABLE:
        print("提示：恢复该路径、或清除持久化选择后重试（选择命令随 A3 提供）。")
    if diag["state"] == dataroot.STATE_AMBIGUOUS:
        print("提示：本机有多个候选根含工作区——破坏性操作会在确认目标根之前被拒绝。")


def main():
    parser = argparse.ArgumentParser(
        prog="jobws doctor",
        description="数据根三态体检（ok / ambiguous / uninitialized / unavailable）")
    parser.add_argument("--json", action="store_true",
                        help="输出 ResolvedDataRootDiagnostic 的 JSON（机器可读）")
    args = parser.parse_args()

    diag = dataroot.describe(dataroot.form_for_process(), pathres.resolve_root(),
                             workspace_name=_workspace_name())
    if args.json:
        print(json.dumps(diag, ensure_ascii=False, indent=2))
    else:
        _print_human(diag)
    return 1 if diag["state"] == dataroot.STATE_UNAVAILABLE else 0


if __name__ == "__main__":
    sys.exit(main())
