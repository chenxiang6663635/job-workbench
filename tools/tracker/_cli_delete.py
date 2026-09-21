# -*- coding: utf-8 -*-
"""删除类子命令的统一尾部：五张从表的 delete 动作共用（2026-09-21 批 D）。

与 add / update 的 `--preview` 可选项不同，删除**永远**两段式：不给直写口——
先预览"将删哪一行"，再 `jobws apply <令牌>` 落盘。这是"删除是唯一不可逆的写"
这一事实的直接翻译。

为什么单独成文件而不是塞进任一 `_cli_*.py`：它被五个域文件共用，放进任一个
都会让那个文件成为其余四个的下游（import 环）；而"五处各写一遍预览尾部"正是
本批要消灭的口径漂移源。
"""

import logging
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core  # noqa: E402
from . import deletes  # noqa: E402


def run_delete_preview(store_key, record_id, operation, workspace=None):
    """删除的统一尾部：领域层校验 → 两段式预览（打印差异 + 令牌）。

    返回退出码：0 = 已签发令牌（等工作区外的 `jobws apply <令牌>` 落盘）；
    1 = 校验失败，未做任何改动。领域层负责"将删什么"的完整校验与差异表，
    这里只做打印与协议登记——没有第二份校验就没有失配的机会。
    """
    ws = workspace or _core.WORKSPACE
    errors, plan = deletes.preview_delete(store_key, record_id, ws)
    if errors:
        print("## 校验失败\n")
        for error in errors:
            print("- %s" % error)
        print("\n未做任何改动。")
        return 1
    from jobws_core import approval  # 延迟导入（与 _cli_mail / _cli_interview 同款）
    result = approval.preview(operation, ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    print("## 预览（未删除）\n")
    print(result["summary"])
    print("")
    for line in plan["diff"]:
        print(line)
    print("\n要落盘请执行：python tools/jobws.py apply %s" % result["token"])
    print("令牌 %d 秒内有效、且只能用一次。" % approval.DEFAULT_TTL_SECONDS)
    return 0
