# -*- coding: utf-8 -*-
"""记录删除：mail / interview / contact / talk / offer 五张表的泛型实现（2026-09-21 批 D）。

为什么是「一个泛型 + 各表薄包装」：五张表的删除语义完全相同——单条 + 全字段
行指纹 + 整表快照留痕 + 锁内剔除写回——差异只在（id 字段、字段表、读写函数、
留痕子目录、展示标签）。各写一份正是"五处口径漂移"的温床；而题库删除
（`jobws_core.question_delete`，2026-09-20）已经把同一份语义打磨过一遍：
预览优先 / 真删 / 留痕可恢复。这里把它参数化，不重新发明。

三条纪律（逐条对齐题库删除）：
1. **预览优先**：先把"将删哪一行"列成差异表，人确认后才准删；落盘只在
   `jobws apply <令牌>` 一处（本模块不开写端点、不碰协议层）；
2. **真删**：锁内整表重读 → 核对指纹 → 剔除 → 原子重写（不做软删除标记——
   数据文件保持"可读可手改"，这是全仓的「文件即数据库」约定）；
3. **留痕可恢复**：删之前把**整表快照**写到工作区之外
   （`<snapshot_root>/<工作区名>/<域>-deletes/`，与题库删除同一片快照域）——
   写不出就**中止删除**：无痕删除违背这个操作对自己的承诺，宁可不动。
"""

import datetime
import os

from jobws_core import pathres  # noqa: E402  （快照根目录：**必须**在工作区之外）
from jobws_core.filelock import file_lock  # noqa: E402

from ._core import ConflictError, _atomic_write_csv, _lock_path, resolve_ws  # noqa: E402
from ._schema import (CONTACT_FIELDS, INTERVIEW_FIELDS, MAIL_FIELDS,  # noqa: E402
                      OFFER_FIELDS, TALK_FIELDS)
from .contacts import contact_path, find_contact, read_contacts, write_contacts  # noqa: E402
from .interviews import (find_interview, interview_path, read_interviews,  # noqa: E402
                         write_interviews)
from .mails import find_mail, mail_path, read_mails, write_mails  # noqa: E402
from .offers import find_offer, offer_path, read_offers, write_offers  # noqa: E402
from .talks import find_talk, read_talks, talk_path, write_talks  # noqa: E402


# 每张表的「存储描述符」：泛型实现里全部分叉都收敛在这张表里。
# cli_hint 只进错误文案（「用 `track mail list` 查」）——不是调用。
_STORES = {
    "mails": {
        "key": "mails", "name_cn": "邮件", "id_field": "邮件id",
        "fields": MAIL_FIELDS, "path": mail_path, "read": read_mails,
        "write": write_mails, "find": find_mail,
        "label_fields": ("主题",), "trace_dir": "mail-deletes",
        "cli_hint": "track mail list",
    },
    "interviews": {
        "key": "interviews", "name_cn": "面试记录", "id_field": "面试id",
        "fields": INTERVIEW_FIELDS, "path": interview_path,
        "read": read_interviews, "write": write_interviews,
        "find": find_interview, "label_fields": ("公司", "岗位", "轮次"),
        "trace_dir": "interview-deletes", "cli_hint": "track interview list",
    },
    "contacts": {
        "key": "contacts", "name_cn": "联系人", "id_field": "联系人id",
        "fields": CONTACT_FIELDS, "path": contact_path, "read": read_contacts,
        "write": write_contacts, "find": find_contact,
        "label_fields": ("姓名", "公司"), "trace_dir": "contact-deletes",
        "cli_hint": "track contact list",
    },
    "talks": {
        "key": "talks", "name_cn": "宣讲会", "id_field": "宣讲会id",
        "fields": TALK_FIELDS, "path": talk_path, "read": read_talks,
        "write": write_talks, "find": find_talk,
        "label_fields": ("公司", "时间"), "trace_dir": "talk-deletes",
        "cli_hint": "track talk list",
    },
    "offers": {
        "key": "offers", "name_cn": "Offer", "id_field": "offer_id",
        "fields": OFFER_FIELDS, "path": offer_path, "read": read_offers,
        "write": write_offers, "find": find_offer,
        "label_fields": ("公司", "岗位"), "trace_dir": "offer-deletes",
        "cli_hint": "track offer list",
    },
}

# 已登记的记录类型（排障与测试用：漏登记时一眼看得出少了谁）
STORES = tuple(sorted(_STORES))


def _fingerprint(store, row):
    """一行的指纹：全字段去空白取值。

    为什么不用"只认 id"：各表 id 是 max+1（`next_mail_id` 等）——删掉最大号
    之后再新增，新记录会**复用**同一个 id；只认 id 就会出现"预览删 M003、
    落盘删掉刚新增的 M003"。指纹不符即整体拒绝（与题库的 `_validate_fingerprints`
    同一思路，那里是五字段、这里全字段——从表列少，全字段更稳）。
    """
    return dict((field, (row.get(field) or "").strip()) for field in store["fields"])


def _label(store, row):
    """一行的展示标签（进摘要文案）：取描述符里定的 label_fields，非空拼接。"""
    parts = [(row.get(field) or "").strip() for field in store["label_fields"]]
    return " ".join(part for part in parts if part)


def _fmt(store, record_id, label):
    return "%s%s" % (record_id, ("（%s）" % label) if label else "")


def preview_delete(store_key, record_id, workspace=None):
    """预览删除一条记录（**不落盘**），返回 (errors, plan)。

    校验都在预览期给出**具体原因**（找不到 / 重复 id）——预览是"将要落什么"
    的承诺，含糊失败比明确报错更贵。
    """
    store = _STORES.get(store_key)
    if store is None:
        return ["未知的记录类型：%s" % store_key], None
    record_id = (record_id or "").strip()
    if not record_id:
        return ["缺少记录 id（用 `%s` 查）" % store["cli_hint"]], None
    ws = resolve_ws(workspace)
    rows = store["read"](ws)
    row = store["find"](rows, record_id)
    if row is None:
        return ["找不到 id 为 %s 的%s（用 `%s` 查）"
                % (record_id, store["name_cn"], store["cli_hint"])], None
    # id 重复守卫：落盘按 id 匹配全部同 id 行——重复会让"删一条"变成"带走多行"，
    # 而 CSV 被手改过时这完全可能（与题库的重复守卫同款）
    same = [item for item in rows
            if (item.get(store["id_field"]) or "").strip() == record_id]
    if len(same) > 1:
        return ["CSV 里有重复的 %s（%s）——一次删除会带走多行，先修数据再删"
                % (store["id_field"], record_id)], None
    label = _label(store, row)
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in store["fields"]:
        value = (row.get(field) or "").strip()
        if value:
            diff.append("| %s | %s |" % (field, value))
    plan = {
        "payload": {"store": store_key, "id": record_id,
                    "rows": [_fingerprint(store, row)]},
        "summary": "删除%s：%s" % (store["name_cn"], _fmt(store, record_id, label)),
        "diff": diff,
        "targets": [store["path"](ws)],
    }
    return [], plan


def trace_path(store_key, workspace=None):
    """删除留痕目录：**工作区之外**（与题库快照同域，按工作区名分目录）。"""
    store = _STORES[store_key]
    ws = resolve_ws(workspace)
    name = os.path.basename(os.path.normpath(ws)) or "workspace"
    return os.path.join(pathres.snapshot_root(), name, store["trace_dir"])


def _write_trace(store, rows, workspace=None):
    """删之前把**整表**快照写走；恢复方式 = 把该文件复制回原 CSV 路径。

    写不出来就**中止删除**（与题库同一条纪律，理由也一样）：留痕若与被删对象
    同处一地，一次误操作会连它一起抹掉；而"没有后路的删除"不该被执行——
    它恰恰是唯一不可逆的写。
    """
    target_dir = trace_path(store["key"], workspace)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = os.path.join(target_dir, "%s-before-delete-%s.csv" % (store["key"], stamp))
    try:
        # makedirs 也放进 try：建不出目录（权限 / 盘满）时抛裸 OSError 会以 500
        # 冒出去，而它其实是"留痕写不出来 → 中止删除"，语义与写文件失败完全同类
        os.makedirs(target_dir, exist_ok=True)
        _atomic_write_csv(path, rows, store["fields"], "utf-8-sig")
    except OSError as exc:
        raise ConflictError(
            "删除前的留痕写不出来（%s）——已中止，工作区未做任何改动" % exc)
    return path


def _validate_fingerprint(store, rows, expected):
    """核对"要删的还正是预览时那一行"。

    不在了 / 不再唯一 / 被改过，都整体拒绝：删错一行之后用户根本察觉不到，
    快照也就不会去用——宁可这次不删，请用户重新预览。
    """
    rid = (expected.get(store["id_field"]) or "").strip()
    matches = [item for item in rows
               if (item.get(store["id_field"]) or "").strip() == rid]
    if len(matches) != 1:
        raise ConflictError(
            "%s 这一行在预览之后不在了或不再唯一（已放弃本次删除，未做任何改动）"
            % rid)
    if _fingerprint(store, matches[0]) != expected:
        raise ConflictError(
            "%s 这一行在预览之后被改过（已放弃本次删除，未做任何改动）——请重新预览"
            % rid)


def apply_approved_delete(payload, workspace=None):
    """两段式第二步：锁内读最新 → 核对行指纹 → **先留痕** → 剔除 → 原子重写。

    顺序有意如此：留痕在写回之前、且写不出就中止——反过来（先删再补痕）在
    崩溃时留下的是"删了但没有痕"的最坏形态。
    """
    store_key = (payload.get("store") or "").strip()
    store = _STORES.get(store_key)
    if store is None:
        raise ConflictError(
            "未知的记录类型（%r）——载荷来自旧版本或已损坏，请重新预览" % store_key)
    record_id = str(payload.get("id") or "").strip()
    expected = [item for item in (payload.get("rows") or [])
                if isinstance(item, dict)]
    if not record_id:
        raise ConflictError("载荷里没有记录 id（请重新预览）")
    if len(expected) != 1:
        # 手搓 / 老令牌没有指纹：没有它就没法确认「删的还是那一行」，拒绝
        raise ConflictError(
            "载荷里没有行指纹（请重新预览——它是防「预览删 A、落盘删 B」的第二次核对）")
    ws = resolve_ws(workspace)
    with file_lock(_lock_path(ws)):
        rows = store["read"](ws)
        _validate_fingerprint(store, rows, expected[0])
        keeping = [item for item in rows
                   if (item.get(store["id_field"]) or "").strip() != record_id]
        removed = len(rows) - len(keeping)
        trace = _write_trace(store, rows, ws)
        store["write"](keeping, ws)
    label = _label(store, expected[0])
    return {"id": record_id, "written": removed, "trace": trace,
            "summary": "已删除%s：%s"
                       % (store["name_cn"], _fmt(store, record_id, label))}


# ---- 各表薄包装：登记表与 CLI / 后端直接引用的名字（实现全在上面一份）--------
#
# apply 的包装体一致（载荷自带 store 键，落盘实现同一份）——名字分开是为了
# 登记表、测试断言与排障时能指名道姓；不为此再抄五份实现。


def preview_delete_mail(mail_id, workspace=None):
    """薄包装：邮件删除预览。"""
    return preview_delete("mails", mail_id, workspace)


def apply_approved_mail_delete(payload, workspace=None):
    """薄包装：邮件删除落盘（登记为 `mail.delete`）。"""
    return apply_approved_delete(payload, workspace)


def preview_delete_interview(interview_id, workspace=None):
    """薄包装：面试记录删除预览。"""
    return preview_delete("interviews", interview_id, workspace)


def apply_approved_interview_delete(payload, workspace=None):
    """薄包装：面试记录删除落盘（登记为 `interview.delete`）。"""
    return apply_approved_delete(payload, workspace)


def preview_delete_contact(contact_id, workspace=None):
    """薄包装：联系人删除预览。"""
    return preview_delete("contacts", contact_id, workspace)


def apply_approved_contact_delete(payload, workspace=None):
    """薄包装：联系人删除落盘（登记为 `contact.delete`）。"""
    return apply_approved_delete(payload, workspace)


def preview_delete_talk(talk_id, workspace=None):
    """薄包装：宣讲会删除预览。"""
    return preview_delete("talks", talk_id, workspace)


def apply_approved_talk_delete(payload, workspace=None):
    """薄包装：宣讲会删除落盘（登记为 `talk.delete`）。"""
    return apply_approved_delete(payload, workspace)


def preview_delete_offer(offer_id, workspace=None):
    """薄包装：Offer 删除预览。"""
    return preview_delete("offers", offer_id, workspace)


def apply_approved_offer_delete(payload, workspace=None):
    """薄包装：Offer 删除落盘（登记为 `offer.delete`）。"""
    return apply_approved_delete(payload, workspace)
