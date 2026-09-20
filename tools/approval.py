# -*- coding: utf-8 -*-
"""`approval` 的仓内侧：转发 `jobws_core.approval` 的协议外壳，并登记本仓的写操作。

2026-09-19 批 6 第二批：协议外壳（令牌生成 / 一次性 / 过期 / 绑定 / 指纹）搬进
领域包 `jobws_core.approval`；**操作注册表留在这里**——`question_bank` /
`prep_notes` / `init_workspace` 三个领域模块按用户拍板留仓，包内不该反向依赖
它们（那正是三条包级循环依赖的来源）。

两条纪律：
1. **登记发生在 import 本模块时**（下面模块顶层就跑）：`apply()` 靠注册表找
   handler，漏登记会以 `unknown_operation` 拒绝（稳定 code，不是崩溃）；
2. 本模块**不发** DeprecationWarning——它与纯转发 shim 不同，手里握着登记表，
   而 `tools/jobws.py` 在顶层 import 它，告警会污染 CLI 的 stderr。

用法（作为统一入口的子命令）：
    python tools/jobws.py apply <令牌> [--workspace <目录>]
退出码：0 成功，1 令牌不可用或应用时冲突，2 用法错误。
"""

from __future__ import print_function

import argparse
import sys

from jobws_core import approval as _shell

# ---- 转发协议外壳（存量 import 的公开面，一字不改）----
ApprovalError = _shell.ApprovalError
ApprovalConflict = _shell.ApprovalConflict
DEFAULT_TTL_SECONDS = _shell.DEFAULT_TTL_SECONDS
preview = _shell.preview
apply = _shell.apply
register = _shell.register
registered_operations = _shell.registered_operations


def _register_operations():
    """把 13 个写操作登记进包内的注册表。

    冲突类型统一用领域层的 `tracker.ConflictError`：tracker（已进包）与
    question_bank 都用它表示「预览时的判断已不成立」；其余操作不抛冲突，
    登记同一个类型无害。
    """
    import init_workspace
    import prep_notes

    from jobws_core import tracker

    conflict = tracker.ConflictError
    # 只登记**留仓**的两个：另外十一个（track.* / talk.add / mail.add /
    # interview.* / question.*）的实现已在领域包里，由 `jobws_core.approval`
    # 自己登记——独立安装下也拿得到（见包内 `_register_builtin_operations`）。
    for name, handler in (
        ("prep.toggle", prep_notes.apply_approved_toggle),
        ("init", init_workspace.apply_approved_init),
    ):
        _shell.register(name, handler, conflict_type=conflict)


_register_operations()


def __getattr__(name):
    """其余名字（含 `_store_dir` / `_OPERATIONS` 这类私有成员）一律转发到包内。

    测试与排障会直接用私有成员（`tests/test_approval*.py` 给令牌目录打桩、
    断言注册表内容），逐名字转发会漏——PEP 562 兜底比名单可靠。
    """
    return getattr(_shell, name)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws apply",
        description="凭令牌执行已确认的写入（两段式的第二步）")
    parser.add_argument("token", help="preview 阶段给出的令牌")
    parser.add_argument("--workspace", default=None,
                        help="工作区目录（默认沿用令牌绑定的那个）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        result = apply(args.token, workspace=args.workspace)
    except ApprovalConflict as exc:
        print("冲突：%s" % exc)
        return 1
    except ApprovalError as exc:
        print("拒绝：%s" % exc)
        return 1

    print("已执行：%s" % (result.get("summary") or result.get("operation") or ""))
    if result.get("id"):
        print("记录 id：%s" % result["id"])
    if result.get("written") is not None:
        print("写入条数：%d" % result["written"])
    if result.get("trace"):
        # 删除类操作的留痕路径要**显式打出来**：删错之后全靠它回来，而文档只说了
        # "在工作区之外"——不给确切路径等于让人去猜（快照根目录还可能被改过）
        print("留痕（删前整表快照，可整份复制回 questions.csv）：%s" % result["trace"])
    return 0


if __name__ == "__main__":
    # 与其他模块一致：不做独立入口，只给一条可复制的迁移命令。
    print("该脚本只作为统一入口的子命令使用，请改用：python tools/jobws.py apply <令牌>")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
