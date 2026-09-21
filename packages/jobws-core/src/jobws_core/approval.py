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

**操作实现由调用侧登记**（`register()`），本模块只管协议外壳，不碰业务：

    登记表分两半：包内 `_register_builtin_operations()` 自登记 17 个操作
    （track.* / talk.add / mail.add / interview.* / question.* / mail.delete /
    interview.delete / contact.delete / talk.delete / offer.delete /
    application.delete），仓库的 `tools/approval.py` 在 import 时追加 2 个
    留仓操作（prep.toggle / init）。

为什么改成注册制（2026-09-19 批 6 第二批）：原先这里写死
`"track.add" -> tracker.apply_approved_add` 这类映射，等于**包反向依赖实现方**。
协议外壳搬进 `jobws-core` 之后，那会成为三条包级循环依赖的根源——尤其
`question_bank` / `prep_notes` / `init_workspace` 按用户拍板留仓，包内不可能
指向它们。注册制把「谁实现」交给调用侧，包内零反向依赖。

**登记是 import 期的副作用**：漏登记的后果是 `apply()` 以 `unknown_operation`
拒绝（稳定 code，不是崩溃）——调用方看到的是「这个操作没人认领」。

**乐观并发**：预览到确认之间，工作区数据可能已经变了（用户手工改过、另一个
会话写过）。所以 apply 不是"照着预览时的快照盲写"，而是**在锁内用最新数据
重校验**，不通过就整体拒绝并要求重新预览——已确认的写入宁可失败一次，也不在
半信半疑的状态下落盘。

退出码（CLI 侧 `tools/approval.py` 的 `main`）：0 成功，1 令牌不可用或应用时冲突，
2 用法错误。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid

# 令牌有效期（秒）：够用户读完一份差异表，又不至于让"很久以前的那次预览"被当成
# 刚做的事。过期的代价只是重新预览一次，所以宁可短一些。
DEFAULT_TTL_SECONDS = 600

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


class ApprovalError(RuntimeError):
    """令牌不可用（不存在 / 已过期 / 已用过 / 不匹配 / 被改过）时抛出。

    消息面向用户（会经 CLI 输出或 MCP 返回透出去），所以必须写清"怎么办"。

    code 是**稳定**的程序化判据（批 8 加；MCP 侧据此区分四类拒绝）：
    bad_token / not_found（含重放与已清理）/ unreadable / lost / expired /
    binding / fingerprint / unknown_operation / conflict。
    文案可以改，code 不要改——测试与调用方都按它断言。
    """

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


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


# 操作注册表：key 是 preview 时用的操作名，value 是「给定载荷就落盘」的函数。
#
# 由调用侧经 register() 填入（见模块 docstring「为什么改成注册制」）。
# **值的形态保持单值**：测试与工厂直接 setitem 假 handler 进来（monkeypatch 打桩），
# 改成元组会让那些既有用法全部 TypeError。
_OPERATIONS = {}

# 每个操作的「冲突异常类型」（可选）：领域层发现"预览时的判断已不成立"时抛的就是它，
# apply 据此转译成 ApprovalConflict 的语义。缺失即视为不抛冲突。
_CONFLICT_TYPES = {}


def register(operation, handler, conflict_type=None):
    """登记一个写操作。

    handler 的签名固定为 `handler(payload, workspace) -> dict`。
    conflict_type 是「预览时的判断已不成立」那一类异常（领域层自己的
    `ConflictError`）——登记它，apply 才能把它转译成 ApprovalConflict 的语义，
    而不是让调用方去认领域层的异常类。
    """
    _OPERATIONS[operation] = handler
    _CONFLICT_TYPES[operation] = conflict_type


def registered_operations():
    """已登记的操作名（排障与测试用：漏登记时一眼看得出少了谁）。"""
    return sorted(_OPERATIONS)


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
            "令牌格式不对（%r）——它应该是 32 位十六进制；请重新预览。" % (token,),
            code="bad_token")
    path = _token_path(token)
    if not os.path.isfile(path):
        # 重放（第二次 apply 同一令牌）也落在这里——与"从未存在"有意不区分
        raise ApprovalError(
            "找不到这个令牌：它可能已被使用、已被清理，或来自另一个临时目录"
            "（比如另一个用户的会话）。请重新预览。",
            code="not_found")
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ApprovalError("令牌文件读不出来（%s）——请重新预览。" % exc,
                            code="unreadable")

    # 先取走再执行：重放与并发都挡在这一步。取走失败说明另一个进程正拿着它，
    # 此时**不能**继续——否则同一份确认会被执行两次。
    try:
        os.remove(path)
    except OSError as exc:
        raise ApprovalError("令牌取走失败（%s）——请重新预览。" % exc,
                            code="lost")

    if time.time() > float(record.get("expires_at") or 0):
        raise ApprovalError(
            "令牌已过期（有效期 %d 秒）。请重新预览——数据可能已经变了。"
            % DEFAULT_TTL_SECONDS,
            code="expired")

    bound = record.get("workspace")
    if bound and workspace and os.path.abspath(workspace) != bound:
        raise ApprovalError(
            "令牌绑定的是工作区 %s，与当前工作区 %s 不符——请重新预览。"
            % (bound, os.path.abspath(workspace)),
            code="binding")
    if bound and not workspace:
        workspace = bound

    payload = record.get("payload")
    if _payload_fingerprint(payload) != record.get("payload_hash"):
        raise ApprovalError("令牌载荷已被改动——拒绝执行，请重新预览。",
                            code="fingerprint")

    handler = _OPERATIONS.get(record.get("operation"))
    if handler is None:
        raise ApprovalError("未知操作 %r（可能是旧版本残留的令牌，或调用侧漏登记）"
                            "——请重新预览。" % record.get("operation"),
                            code="unknown_operation")
    conflict_type = _CONFLICT_TYPES.get(record.get("operation"))

    try:
        result = handler(payload, workspace)
    except Exception as exc:
        # 领域层发现"预览时的判断已不成立"——转译成协议层的冲突语义，
        # 调用方只需认 ApprovalError / ApprovalConflict 两种（不必认识领域异常）。
        if conflict_type is not None and isinstance(exc, conflict_type):
            raise ApprovalConflict(str(exc), code="conflict")
        raise
    result = dict(result or {})
    result.setdefault("operation", record.get("operation"))
    result.setdefault("summary", record.get("summary"))
    return result


def _register_builtin_operations():
    """登记「实现已在包内」的十七个操作（PR-B 起：登记表**分层**）。

    另半截在仓库的 `tools/approval.py`：它追加 `prep.toggle` 与 `init`——那两个
    领域模块按用户拍板留仓。这样拆的收益是**导入不再依赖仓库**：独立安装的
    MCP 侧 `from jobws_core import approval` 就拿到十七个可用操作，而那两个仓库侧
    操作会以 `unknown_operation`（稳定 code）显式拒绝，不是崩溃。

    为什么注册制 + 分层而不是写死：见模块 docstring「为什么改成注册制」。
    这里的 import 都在函数内/末尾，`tracker` 只在函数内回头 import 本模块，
    所以不构成循环。
    """
    from . import question_bank, question_delete, tracker

    conflict = tracker.ConflictError
    operations = (
        ("track.add", tracker.apply_approved_add),
        ("track.update", tracker.apply_approved_update),
        ("track.import", tracker.apply_approved_import),
        ("talk.add", tracker.apply_approved_talk),
        ("mail.add", tracker.apply_approved_mail),
        # 批 4.7：面试补两段式（原先只有 CLI 直写路径）——三端共用同一份载荷与校验。
        ("interview.add", tracker.apply_approved_interview_add),
        ("interview.update", tracker.apply_approved_interview_update),
        ("question.add", question_bank.apply_approved_add),
        ("question.update", question_bank.apply_approved_update),
        ("question.import", question_bank.apply_approved_import),
        # 2026-09-20：给导入装刹车——删一道题也得先看过"将删哪几行"。
        ("question.delete", question_delete.apply_approved_delete),
        # 2026-09-21 批 D（数据安全网）：五类记录删除——泛型实现在
        # tracker/deletes.py，各薄包装共用同一份纪律（预览 → 令牌 →
        # 工作区外留痕 → 锁内落盘）；MCP / 插件端刻意不开放（模型不代劳删除）。
        ("mail.delete", tracker.apply_approved_mail_delete),
        ("interview.delete", tracker.apply_approved_interview_delete),
        ("contact.delete", tracker.apply_approved_contact_delete),
        ("talk.delete", tracker.apply_approved_talk_delete),
        ("offer.delete", tracker.apply_approved_offer_delete),
        # 主表删除带「解绑关联记录」联动（不级联删），走专有实现（tracker/deletes.py）
        ("application.delete", tracker.apply_approved_application_delete),
    )
    for name, handler in operations:
        register(name, handler, conflict_type=conflict)


_register_builtin_operations()
