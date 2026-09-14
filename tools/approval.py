# -*- coding: utf-8 -*-
"""写入操作的两段式协议：先预览（**不落盘**），凭令牌再落盘。

为什么要有它：写类操作会改用户数据，而调用方不止一个（命令行、MCP 宿主、网页端）。
两段式把「会写什么」在落盘**之前**摊成 diff，并把「确实要写」这个意图固化成
一次性令牌——写错数据的代价远高于多敲一次确认。

三条硬性（`tests/test_approval.py` 与 `tests/test_approval_flow.py` 逐条钉住）：

1. **预览不落盘**：preview 阶段一个字节都不写工作区——令牌存在系统临时目录里，
   不进工作区（预览连一个目录都不该在工作区里建）；
2. **令牌一次性**：apply 时**先把令牌取走（删除）再执行**——重放与并发都在取走
   那一步被挡下，一份令牌只可能有一个赢家；
3. **令牌有过期时间且绑定目标**：默认 10 分钟；令牌里记着工作区绝对路径与载荷
   指纹，跨工作区、或与预览时不一致的载荷，一律拒绝。

操作实现由各领域模块提供（本模块只管协议外壳，不碰业务）：

    "track.add"    -> tracker.apply_approved_add
    "track.import" -> tracker.apply_approved_import

**乐观并发**：预览到确认之间，工作区数据可能已经变了（用户手工改过、另一个
会话写过）。所以 apply 不是"照着预览时的快照盲写"，而是**在锁内用最新数据
重校验**，不通过就整体拒绝并要求重新预览——已确认的写入宁可失败一次，也不
在半信半疑的状态下落盘。

用法（作为统一入口的子命令）：
    python tools/jobws.py apply <令牌> [--workspace <目录>]
退出码：0 成功，1 令牌不可用或应用时冲突，2 用法错误。
"""

from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import tracker  # noqa: E402

# 令牌有效期（秒）：够用户读完一份差异表，又不至于让"很久以前的那次预览"被当成
# 刚做的事。过期的代价只是重新预览一次，所以宁可短一些。
DEFAULT_TTL_SECONDS = 600

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


class ApprovalError(RuntimeError):
    """令牌不可用（不存在 / 已过期 / 已用过 / 不匹配 / 被改过）时抛出。

    消息面向用户（会经 CLI 输出或 MCP 返回透出去），所以必须写清"怎么办"。
    """


class ApprovalConflict(ApprovalError):
    """预览之后工作区数据变了，已确认的写入不再安全——请重新预览。"""


def _store_dir():
    """令牌目录：系统临时目录下的固定子目录。

    刻意**不放工作区**：预览阶段连一个目录都不该在工作区里建（硬性第 1 条）；
    也刻意不放仓库：多个工作区共用同一份代码时互不干扰。

    澄清一句：「预览不落盘」指的是**不碰用户数据**——预览会在系统临时目录里建
    这个目录、写一份令牌，那是协议自身的簿记，与工作区无关（独立审查 M2）。
    """
    path = os.path.join(tempfile.gettempdir(), "jobws-approvals")
    os.makedirs(path, exist_ok=True)
    return path


def _token_path(token):
    return os.path.join(_store_dir(), token + ".json")


def _payload_fingerprint(payload):
    """载荷指纹：把「这次要写什么」压成一个稳定摘要，用于防篡改。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def preview(operation, workspace, payload, summary, diff, targets,
            ttl=DEFAULT_TTL_SECONDS):
    """登记一次待确认的写入，返回令牌与差异（**不碰工作区**）。

    「会写什么」由各操作的预览函数算好传进来：`payload` 是够 apply 用的最小
    数据，`summary`/`diff`/`targets` 只给人看。本模块只管协议——令牌的生成、
    过期、一次性与绑定。
    """
    token = uuid.uuid4().hex
    now = time.time()
    record = {
        "token": token,
        "operation": operation,
        "workspace": os.path.abspath(workspace) if workspace else None,
        "created_at": now,
        "expires_at": now + ttl,
        "payload": payload,
        "payload_hash": _payload_fingerprint(payload),
        "summary": summary,
        "targets": list(targets),
    }
    with open(_token_path(token), "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
    return {
        "token": token,
        "operation": operation,
        "summary": summary,
        "diff": list(diff),
        "targets": list(targets),
        "expires_at": record["expires_at"],
    }


def apply(token, workspace=None):
    """凭令牌执行已确认的写入；令牌一次性，取走即焚。

    workspace 不传时沿用令牌绑定的那个（CLI 的常见用法）；传了就必须一致——
    否则等于把 A 工作区的确认书用到了 B 工作区上。
    """
    if not isinstance(token, str) or not _TOKEN_RE.match(token):
        raise ApprovalError(
            "令牌格式不对（%r）——它应该是 32 位十六进制；请重新预览。" % (token,))
    path = _token_path(token)
    if not os.path.isfile(path):
        raise ApprovalError(
            "找不到这个令牌：它可能已被使用、已被清理，或来自另一个临时目录"
            "（比如另一个用户的会话）。请重新预览。")
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ApprovalError("令牌文件读不出来（%s）——请重新预览。" % exc)

    # 先取走再执行：重放与并发都挡在这一步。取走失败说明另一个进程正拿着它，
    # 此时**不能**继续——否则同一份确认会被执行两次。
    try:
        os.remove(path)
    except OSError as exc:
        raise ApprovalError("令牌取走失败（%s）——请重新预览。" % exc)

    if time.time() > float(record.get("expires_at") or 0):
        raise ApprovalError(
            "令牌已过期（有效期 %d 秒）。请重新预览——数据可能已经变了。"
            % DEFAULT_TTL_SECONDS)

    bound = record.get("workspace")
    if bound and workspace and os.path.abspath(workspace) != bound:
        raise ApprovalError(
            "令牌绑定的是工作区 %s，与当前工作区 %s 不符——请重新预览。"
            % (bound, os.path.abspath(workspace)))
    if bound and not workspace:
        workspace = bound

    payload = record.get("payload")
    if _payload_fingerprint(payload) != record.get("payload_hash"):
        raise ApprovalError("令牌载荷已被改动——拒绝执行，请重新预览。")

    handler = _OPERATIONS.get(record.get("operation"))
    if handler is None:
        raise ApprovalError("未知操作 %r（可能是旧版本残留的令牌）——请重新预览。"
                            % record.get("operation"))

    try:
        result = handler(payload, workspace)
    except tracker.ConflictError as exc:
        # 领域层发现"预览时的判断已不成立"——转译成协议层的冲突语义，
        # 调用方只需认 ApprovalError / ApprovalConflict 两种。
        raise ApprovalConflict(str(exc))
    result = dict(result or {})
    result.setdefault("operation", record.get("operation"))
    result.setdefault("summary", record.get("summary"))
    return result


# 操作注册表：key 是 preview 时用的操作名，value 是"给定载荷就落盘"的函数。
# 只登记**已实现**的操作——没实现的不会走到这里（也没有路径能生成它的令牌）。
_OPERATIONS = {
    "track.add": tracker.apply_approved_add,
    "track.import": tracker.apply_approved_import,
}


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
    return 0


if __name__ == "__main__":
    # 与其他模块一致：不做独立入口，只给一条可复制的迁移命令。
    print("该脚本只作为统一入口的子命令使用，请改用：python tools/jobws.py apply <令牌>")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
