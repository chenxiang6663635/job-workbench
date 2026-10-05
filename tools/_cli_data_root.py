# -*- coding: utf-8 -*-
"""`jobws data-root`（A3/B1）：show / set / clear / migrate 与「三态下都必须可用」。

为什么单独一个文件：`tests/test_dataroot_persisted.py` 锁域层读写；这里锁
**CLI 呈现面与分发层**——退出码、`--json`、错误文案，以及 spec 决策 4 的硬
约束：失效态（unavailable）下 `set` / `clear` 仍是可用明路（`tools/jobws.py`
的数据根守卫必须对本命令组豁免）。这是 A2 未覆盖、A3 钉死的一条。

B1 起 `migrate` 加入本组（spec 决策 5）：**默认 dry-run**（只出计划，一个字节
不写），`--apply` 才执行迁移事务；`--resume` 续跑在途事务、`--rollback` 把
选择指回旧根。状态机与三条纪律见 `jobws_core.dataroot_migrate` 的模块说明。

退出码：0 成功（含 dry-run / 幂等跳过 / 无在途事务）；1 动作失败（预检
blocked、迁移 failed、在途事务状态不明）；2 用法错误（相对路径、标志冲突、
未知子命令）。

用法：
    python tools/jobws.py data-root show [--json]
    python tools/jobws.py data-root set <绝对路径> [--json]
    python tools/jobws.py data-root clear [--json]
    python tools/jobws.py data-root migrate <绝对路径> [--apply] [--json]
    python tools/jobws.py data-root migrate --resume [--apply] [--json]
    python tools/jobws.py data-root migrate --rollback [--apply] [--json]
"""
from __future__ import print_function

import argparse
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from jobws_core import dataroot, dataroot_migrate as migrate, pathres  # noqa: E402

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


# --- migrate（B1）---------------------------------------------------------------

def _migrate_source_root():
    """迁移的源根 = 当前生效的数据根（与 show / doctor 同一条解析链）。"""
    res = dataroot.resolve_data_root(dataroot.form_for_process(), pathres.resolve_root())
    return res.path


def _plan_view(plan):
    """计划的要点视图（逐文件清单不进 CLI 输出——事务记录里有全量）。"""
    manifest = plan.get("manifest") or {}
    return {
        "ok": plan["ok"],
        "already_current": plan["already_current"],
        "source_root": plan["source_root"],
        "target_root": plan["target_root"],
        "workspace": plan["workspace"],
        "target_workspace": plan["target_workspace"],
        "staging": plan["staging"],
        "root_id": plan["root_id"],
        "entries": len(manifest.get("entries") or []),
        "skipped": len(manifest.get("skipped") or []),
        "links": manifest.get("links") or [],
        "total_bytes": manifest.get("total_bytes"),
        "free_bytes": plan.get("free_bytes"),
        "reasons": plan.get("reasons") or [],
    }


def _emit_plan(view, use_json):
    if use_json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
        return
    if view["already_current"]:
        print("当前数据根已指向该目标（root_id 相同），无需迁移。")
        return
    print("迁移计划（dry-run：只读盘点与预检，未写任何东西）")
    print("源根：%s" % view["source_root"])
    print("目标根：%s（工作区：%s）" % (view["target_root"], view["workspace"]))
    print("暂存目录：%s" % view["staging"])
    print("清单：%d 个文件 / %d 字节；另有 %d 个运行时产物将如实跳过"
          % (view["entries"], view["total_bytes"] or 0, view["skipped"]))
    if view["links"]:
        print("符号链接 / junction：%s" % " / ".join(view["links"][:3]))
    if view["free_bytes"] is not None:
        print("目标卷可用空间：%d 字节" % view["free_bytes"])
    for item in view["reasons"]:
        print("· [%s] %s" % (item["kind"], item["message"]))


def _emit_action(result, use_json, label):
    """resume / rollback / apply 三类动作结果的统一呈现；返回退出码。"""
    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    status = result.get("status")
    if status == "nothing":
        print("%s：没有在途事务。" % label)
        return 0
    if status == "unknown":
        print("错误：%s" % result.get("reason"), file=sys.stderr)
        return 1
    if status == "dry-run":
        print("%s演练：相位 %s；将执行 %s；已落位 %d / 还差 %d（源 %s → 目标 %s）"
              % (label, result.get("phase"), "、".join(result.get("steps") or []),
                 result.get("staged") or 0, result.get("remaining") or 0,
                 result.get("source_root"), result.get("target_root")))
        return 0
    if status in ("rolled-back", "noop"):
        if not use_json:
            print("%s完成：选择已指回 %s；目标根与暂存原样保留（%s / %s）——"
                  "不删、不回搬，观察期清理由你裁决。"
                  % (label, result.get("source_root"),
                     "在" if result.get("target_kept") else "不在",
                     "在" if result.get("staging_kept") else "不在"))
        return 0
    if status == "done":
        if not use_json:
            copy = result.get("copy") or {}
            verify = result.get("verify") or {}
            print("%s完成：源 %s → 目标 %s（root_id: %s）"
                  % (label, result.get("source_root"), result.get("target_root"),
                     result.get("root_id")))
            if copy:
                print("复制：%d 个新拷 / %d 个差量命中（%d 字节）"
                      % (copy.get("copied", 0), copy.get("reused", 0),
                         copy.get("bytes", 0)))
            if verify is not None:
                print("校验：%d 个文件逐字节一致" % verify.get("checked", 0))
                for warning in verify.get("warnings") or []:
                    print("告警：%s" % warning)
            print("旧目录未删除（观察期内两份都在）。")
        return 0
    if status == "failed":
        if not use_json:
            print("错误：%s" % result.get("reason"), file=sys.stderr)
            print("源目录未受影响；排除原因后重新执行即可（已落位文件按差量续用）。",
                  file=sys.stderr)
        return 1
    if not use_json:
        print("%s：%s" % (label, json.dumps(result, ensure_ascii=False)))
    return 0


def _run_migrate(args):
    """migrate 子命令：目标路径 / --resume / --rollback 三选一；默认 dry-run。"""
    chosen = [bool(args.path), args.resume, args.rollback]
    if sum(chosen) > 1:
        print("错误：目标路径、--resume、--rollback 只能三选一", file=sys.stderr)
        return 2
    if args.rollback:
        result = migrate.rollback(apply=args.apply)
        if result.get("status") == "dry-run":
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("回滚演练：选择将从 %s 指回 %s（目标根 %s 原样保留）"
                      % (result.get("from") or "（未设置）", result.get("to"),
                         result.get("target_root")))
            return 0
        return _emit_action(result, args.json, "回滚")
    if args.resume:
        return _emit_action(migrate.resume(apply=args.apply), args.json, "续跑")
    if not args.path:
        print("错误：需要一个目标绝对路径，或 --resume / --rollback", file=sys.stderr)
        return 2
    plan = migrate.plan(args.path, _migrate_source_root())
    view = _plan_view(plan)
    if not args.json:
        _emit_plan(view, args.json)
    if view["already_current"]:
        if args.json:
            print(json.dumps({"status": "noop", "already_current": True,
                              "target_root": view["target_root"]},
                             ensure_ascii=False, indent=2))
        return 0
    if not plan["ok"]:
        if args.json:
            print(json.dumps(view, ensure_ascii=False, indent=2))
        print("未执行迁移。", file=sys.stderr)
        return 2 if any(item["kind"] == "usage" for item in plan["reasons"]) else 1
    if not args.apply:
        print("（以上是 dry-run 预演；确认无误后加 --apply 执行迁移）")
        return 0
    return _emit_action(migrate.apply(plan), args.json, "迁移")


def main():
    parser = argparse.ArgumentParser(
        prog="jobws data-root",
        description="数据根选择与迁移：show 读回诊断 / set 记住绝对路径 / clear 取消"
                    " / migrate 迁移到新位置（失效态下的补救通道，三态下都可用）")
    subs = parser.add_subparsers(dest="command", metavar="<子命令>")
    for name, help_text in (("show", "读回数据根诊断（与 doctor 同一份对象）"),
                            ("set", "记住一个数据根（只接受绝对路径）"),
                            ("clear", "清除持久化选择（幂等）")):
        sp = subs.add_parser(name, help=help_text)
        sp.add_argument("--json", action="store_true", help="输出诊断对象的 JSON")
        if name == "set":
            sp.add_argument("path", metavar="<绝对路径>",
                            help="数据根（personal/ 的父目录；相对路径被拒绝）")
    mp = subs.add_parser(
        "migrate",
        help="迁移数据根到新位置（默认 dry-run；--apply 执行；"
             "--resume / --rollback 服务在途事务）")
    mp.add_argument("path", nargs="?", metavar="<绝对路径>",
                    help="目标数据根（personal/ 的父目录；相对路径被拒绝）")
    mp.add_argument("--apply", action="store_true",
                    help="执行迁移（缺省只做 dry-run 计划 / 演练）")
    mp.add_argument("--resume", action="store_true",
                    help="续跑在途事务（按清单 / 哈希差量，不重拷已落位文件）")
    mp.add_argument("--rollback", action="store_true",
                    help="把持久化选择指回旧根（不删、不回搬）")
    mp.add_argument("--json", action="store_true", help="输出结果的 JSON")
    args = parser.parse_args()

    if args.command == "show":
        return _run_show(args.json)
    if args.command == "set":
        return _run_set(args.path, args.json)
    if args.command == "clear":
        return _run_clear(args.json)
    if args.command == "migrate":
        return _run_migrate(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
