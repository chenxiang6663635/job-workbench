# -*- coding: utf-8 -*-
"""投递（主表）删除：带「解绑关联记录」联动（2026-09-21 批 D）。

为什么单开模块而不是并进 `deletes.py`：后者是五张从表的泛型（单条 + 剔除
写回），主表删除多出两件事——① 五张从表以「关联记录」外键指回主表，删行会
留悬空外键（`track check` 报坏）；② 时间线里留着该 id 的全部变更。职责不同、
评审面不同，拆开各自守规模预算。

处理策略（2026-09-21 拍板分叉 4=B）：**解绑而不是级联删除**——关联记录保留、
外键置空，差异表逐条列明；history 不删、追记一条「已删除」。删投递把"这家
公司我面过三轮"的证据一起抹掉远超用户意图；解绑保留事实、消除悬空，是最小
动作。

留痕 / 指纹 / 标签三件小工具与 `deletes.py` 共用（同包兄弟模块直接取私有名
——拆模块是为了行数与职责，不是为了把这些工具抄第二份）。
"""

from jobws_core.filelock import file_lock  # noqa: E402

from ._core import ConflictError, _lock_path, csv_path, resolve_ws  # noqa: E402
from ._schema import FIELDS  # noqa: E402
from .applications import append_history, read_rows, write_rows  # noqa: E402
from .deletes import (  # noqa: E402  （同包工具：留痕 / 指纹 / 标签）
    _STORES, _fingerprint, _fmt, _label, _validate_fingerprint, _write_trace)


# 会以「关联记录」指回主表的五张从表（与 deletes._STORES 同源）
_UNBIND_STORES = ("mails", "interviews", "contacts", "talks", "offers")

# 主表描述符：**不进 _STORES**——投递删除带解绑联动，走专有实现；
# 它存在只为复用指纹 / 标签 / 留痕这几件小工具。
_APP_STORE = {
    "key": "applications", "name_cn": "投递记录", "id_field": "id",
    "fields": FIELDS, "path": csv_path, "read": read_rows, "write": write_rows,
    "label_fields": ("公司", "岗位"), "trace_dir": "application-deletes",
    "cli_hint": "track list",
}


def _application_row(rows, application_id):
    for row in rows:
        if (row.get("id") or "").strip() == application_id:
            return row
    return None


def _application_label(row):
    parts = [(row.get("公司") or "").strip(), (row.get("岗位") or "").strip()]
    return " ".join(part for part in parts if part)


def _linked_rows(store, application_id, workspace):
    """该从表里所有指回这条投递的行（关联记录 == id）。"""
    return [row for row in store["read"](workspace)
            if (row.get("关联记录") or "").strip() == application_id]


def preview_delete_application(application_id, workspace=None):
    """预览删除一条投递记录（**不落盘**）：差异表含「将解绑的关联记录」清单。

    解绑清单不是装饰：它是"删这一行会动到另外几张表"的**唯一事前告知**——
    用户据此决定是删、还是先处理那些关联记录。逐条列出（不是只给数字），
    因为"哪几条"正是判断依据。
    """
    application_id = (application_id or "").strip()
    if not application_id:
        return ["缺少记录 id（用 `%s` 查）" % _APP_STORE["cli_hint"]], None
    ws = resolve_ws(workspace)
    rows = read_rows(ws)
    row = _application_row(rows, application_id)
    if row is None:
        return ["找不到 id 为 %s 的投递记录（用 `%s` 查）"
                % (application_id, _APP_STORE["cli_hint"])], None
    # id 重复守卫：落盘按 id 匹配——重复会让"删一条"变成"带走多行"
    same = [item for item in rows
            if (item.get("id") or "").strip() == application_id]
    if len(same) > 1:
        return ["CSV 里有重复的 id（%s）——一次删除会带走多行，先修数据再删"
                % application_id], None

    unbind = {}
    for store_key in _UNBIND_STORES:
        store = _STORES[store_key]
        linked = _linked_rows(store, application_id, ws)
        if linked:
            unbind[store_key] = [_fingerprint(store, item) for item in linked]
    total_unbind = sum(len(items) for items in unbind.values())

    label = _application_label(row)
    if total_unbind:
        note = "将解绑 %d 条关联记录" % total_unbind
        label = "%s；%s" % (label, note) if label else note
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            diff.append("| %s | %s |" % (field, value))
    if total_unbind:
        diff.append("")
        diff.append("将解绑 %d 条关联记录（记录保留，仅清空「关联记录」列）："
                    % total_unbind)
        for store_key in _UNBIND_STORES:
            store = _STORES[store_key]
            for item in unbind.get(store_key, []):
                rid = (item.get(store["id_field"]) or "").strip()
                diff.append("- %s：%s" % (store["name_cn"],
                                          _fmt(store, rid, _label(store, item))))
    targets = [csv_path(ws)]
    for store_key in _UNBIND_STORES:
        if store_key in unbind:
            targets.append(_STORES[store_key]["path"](ws))
    plan = {
        "payload": {"id": application_id,
                    "rows": [_fingerprint(_APP_STORE, row)],
                    "unbind": unbind},
        "summary": "删除投递：%s" % _fmt(_APP_STORE, application_id, label),
        "diff": diff,
        "targets": targets,
    }
    return [], plan


def apply_approved_application_delete(payload, workspace=None):
    """投递删除的落盘段：全部核对 → 全部留痕 → 解绑从表 → 删主表行 → 追记时间线。

    顺序纪律与泛型一致，只是范围更大：**任一待解绑行与主表行不符就整体拒绝**
    （还没动任何字节）；留痕覆盖每一张将被改动的表（主表 + 被解绑的从表），
    一份写不出就中止。
    """
    application_id = str(payload.get("id") or "").strip()
    expected = [item for item in (payload.get("rows") or [])
                if isinstance(item, dict)]
    if not application_id:
        raise ConflictError("载荷里没有记录 id（请重新预览）")
    if len(expected) != 1:
        raise ConflictError(
            "载荷里没有行指纹（请重新预览——它是防「预览删 A、落盘删 B」的第二次核对）")
    unbind = payload.get("unbind") or {}
    ws = resolve_ws(workspace)
    traces = []
    with file_lock(_lock_path(ws)):
        rows = read_rows(ws)
        _validate_fingerprint(_APP_STORE, rows, expected[0])
        row = _application_row(rows, application_id)
        # 先把全部待解绑行读出来核指纹——任一不符整体拒绝（仍在"零改动"之前）。
        # 同时对五张从表重扫「现在实际指回这条投递的行」：预览之后用户又给这条
        # 投递新挂了关联记录（不在预览清单里）的话，静默删主行会让新行外键悬空
        # ——「将解绑哪些行」是落盘内容的一部分，它变了就必须整体拒绝。
        unbind_plan = []
        for store_key in _UNBIND_STORES:
            store = _STORES[store_key]
            table_rows = store["read"](ws)
            current_ids = set(
                (item.get(store["id_field"]) or "").strip()
                for item in table_rows
                if (item.get("关联记录") or "").strip() == application_id)
            wanted = [item for item in (unbind.get(store_key) or [])
                      if isinstance(item, dict)]
            for item in wanted:
                _validate_fingerprint(store, table_rows, item)
                # 清单内的行不算"多出来的"（指纹通过 = 它还在且仍指回本投递）
                current_ids.discard((item.get(store["id_field"]) or "").strip())
            if current_ids:
                raise ConflictError(
                    "预览之后「%s」又有 %d 条记录新挂到这条投递上（%s）——将解绑"
                    "的清单变了，已拒绝本次删除，请重新预览"
                    % (store["name_cn"], len(current_ids),
                       "、".join(sorted(current_ids))))
            if wanted:
                unbind_plan.append((store, table_rows, wanted))
        # 留痕：主表 + 每一张将被改动的从表，覆盖"本次操作会动到的全部数据"
        traces.append(_write_trace(_APP_STORE, rows, ws))
        for store, table_rows, _wanted in unbind_plan:
            traces.append(_write_trace(store, table_rows, ws))
        # 先解绑（清空「关联记录」后写回，同行其它字段逐字保留）——把"中途崩溃"
        # 的窗口收窄成无害形态：留"解绑了但主行还在"可重试，反向则留悬空外键
        unbound_total = 0
        for store, table_rows, wanted in unbind_plan:
            wanted_ids = set((item.get(store["id_field"]) or "").strip()
                             for item in wanted)
            for table_row in table_rows:
                if (table_row.get(store["id_field"]) or "").strip() in wanted_ids:
                    table_row["关联记录"] = ""
                    unbound_total += 1
            store["write"](table_rows, ws)
        # 再删主表行
        keeping = [item for item in rows
                   if (item.get("id") or "").strip() != application_id]
        write_rows(keeping, ws)
        # 时间线追记一条（history 不删——行没了，但"这件事发生过"留在时间线上）
        append_history([{"id": application_id, "字段": "记录",
                         "原值": _application_label(row), "新值": "已删除"}], ws)
    label = _application_label(row or {})
    if unbound_total:
        note = "并解绑 %d 条关联记录" % unbound_total
        label = "%s；%s" % (label, note) if label else note
    return {"id": application_id, "written": 1, "unbound": unbound_total,
            "trace": ";".join(traces),
            "summary": "已删除投递：%s" % _fmt(_APP_STORE, application_id, label)}
