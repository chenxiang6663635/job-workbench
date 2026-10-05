# -*- coding: utf-8 -*-
"""`jobws data-root`：数据根选择的 CLI 面（A3）。

呈现分工（spec §五）：本命令只做序列化与呈现——诊断对象来自
`jobws_core.dataroot.describe()`，与 `jobws doctor` / MCP `jobws.info` /
`GET /api/system/paths` 是**同一份**。

三态契约（spec §四 / 决策 4）：本命令组是失效态（unavailable）下的**补救
通道**——`show` 照常报诊断，`set` / `clear` 在任何状态下都必须可用
（`tools/jobws.py` 的数据根守卫对本命令组豁免）。`set` / `clear` 只做
「记住 / 忘记」，新位置是否可用由 `show` 与 doctor 如实报，不在这里判死。

退出码：0 成功；1 动作失败（IO 错误）或 show 遇 unavailable（与 doctor
同语义，脚本可据此拦截）；2 用法错误（相对路径、未知子命令）。

用法：
    python tools/jobws.py data-root show [--json]
    python tools/jobws.py data-root set <绝对路径> [--json]
    python tools/jobws.py data-root clear [--json]
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


def _workspace_name():
    """当前工作区目录名：`JOBWS_WORKSPACE` 优先，缺省 `personal`（与各端同口径）。"""
    return (os.environ.get("JOBWS_WORKSPACE") or "").strip() or dataroot.DEFAULT_WORKSPACE_NAME


def _diagnose():
    return dataroot.describe(dataroot.form_for_process(), pathres.resolve_root(),
                             workspace_name=_workspace_name())


def _emit(diag, use_json, prefix=None):
    if use_json:
        print(json.dumps(diag, ensure_ascii=False, indent=2))
        return
    if prefix:
        print(prefix)
    print("数据根：%s" % diag["path"])
    print("来源：%s；形态：%s；状态：%s；可写：%s" % (
        diag["source"], diag["form"], diag["state"],
        "是" if diag["writable"] else "否"))
    sel = diag["persisted_selection"]
    if sel is None:
        print("持久化选择：未设置")
    else:
        print("持久化选择：%s（%s%s）" % (
            sel["path"] or "（读取失败）",
            "可读" if sel["readable"] else "不可读，按未设置处理",
            "，被 env 遮蔽" if sel["shadowed_by"] == "env" else ""))
    if diag["state"] == dataroot.STATE_UNAVAILABLE:
        print("提示：恢复该路径、用 `jobws data-root set <绝对路径>` 重选，"
              "或 `jobws data-root clear` 取消选择。")


def _run_show(use_json):
    diag = _diagnose()
    _emit(diag, use_json)
    return 1 if diag["state"] == dataroot.STATE_UNAVAILABLE else 0


def _run_set(path, use_json):
    try:
        doc = dataroot.write_persisted_selection(path, source="cli")
    except ValueError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("错误：写入持久化选择失败：%s（本次未改变原选择）" % exc, file=sys.stderr)
        return 1
    diag = _diagnose()
    prefix = "已记住数据根：%s（root_id: %s）" % (doc["data_root"], doc["root_id"])
    _emit(diag, use_json, prefix)
    return 0


def _run_clear(use_json):
    removed = dataroot.clear_persisted_selection()
    diag = _diagnose()
    prefix = "已清除持久化选择。" if removed else "此前没有持久化选择（无需清除）。"
    _emit(diag, use_json, prefix)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="jobws data-root",
        description="数据根选择：show 读回诊断 / set 记住绝对路径 / clear 取消"
                    "（失效态下的补救通道，三态下都可用）")
    subs = parser.add_subparsers(dest="command", metavar="<子命令>")
    for name, help_text in (("show", "读回数据根诊断（与 doctor 同一份对象）"),
                            ("set", "记住一个数据根（只接受绝对路径）"),
                            ("clear", "清除持久化选择（幂等）")):
        sp = subs.add_parser(name, help=help_text)
        sp.add_argument("--json", action="store_true", help="输出诊断对象的 JSON")
        if name == "set":
            sp.add_argument("path", metavar="<绝对路径>",
                            help="数据根（personal/ 的父目录；相对路径被拒绝）")
    args = parser.parse_args()

    if args.command == "show":
        return _run_show(args.json)
    if args.command == "set":
        return _run_set(args.path, args.json)
    if args.command == "clear":
        return _run_clear(args.json)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
