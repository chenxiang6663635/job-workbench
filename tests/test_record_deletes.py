# -*- coding: utf-8 -*-
"""记录删除（批 D 数据安全网）：泛型实现 + 各表薄包装的钉住用例。

语义照 `test_bank_delete.py` 逐条对齐，钉住五件事：
1. **预览不落盘**：预览后 CSV 一个字节都没变（按 bytes 断言）；
2. **匹配不到报错误**：空转等于骗人；重复 id 会在落盘时"带走多行"，先拒；
3. **留痕落在工作区之外**：删前**整表快照**写走，写不出即**中止删除**
   （无痕删除违背承诺——宁可不动）；
4. **预览后目标变了就整体拒绝**：被改过 / 不在了——零字节写入；
5. **落盘前核对全字段指纹**：id 是 max+1（最大号删除后会被复用），只认 id
   会出现"预览删 A、落盘删 B"。

五张表（mail / interview / contact / talk / offer）走同一份参数化网——
泛型实现的收益就该由"同一组断言覆盖五处"来兑现。
"""

import csv
import io
import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import tracker  # noqa: E402
from jobws_core.tracker import deletes  # noqa: E402


# (store 键, 记录 id, 种子字段值)——五表各一条样本行
CASES = [
    ("mails", "M001", {"主题": "面试邀约", "日期": "2026-09-21"}),
    ("interviews", "I001", {"公司": "TCL", "岗位": "前端开发", "轮次": "一面",
                            "面试时间": "2026-09-22 14:00"}),
    ("contacts", "C001", {"姓名": "王女士", "公司": "TCL", "角色": "HR"}),
    ("talks", "T001", {"公司": "TCL", "时间": "2026-09-22 19:00", "形式": "线上"}),
    ("offers", "O001", {"公司": "TCL", "岗位": "前端开发", "月薪": "15K"}),
]


@pytest.fixture()
def ws(tmp_path):
    path = tmp_path / "ws"
    (path / "05_投递追踪").mkdir(parents=True)
    return str(path)


@pytest.fixture()
def outside(tmp_path, monkeypatch):
    """把留痕根钉到临时目录：不污染真实快照区，又能断言「在工作区之外」。"""
    root = tmp_path / "snapshots"
    monkeypatch.setattr(deletes.pathres, "snapshot_root", lambda: str(root))
    return str(root)


def _seed(ws, store_key, rows):
    """按该表字段表造 CSV；rows = [(id, {字段: 值}), ...]。返回文件路径。"""
    store = deletes._STORES[store_key]
    path = store["path"](ws)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=store["fields"])
        writer.writeheader()
        for record_id, values in rows:
            row = dict((field, "") for field in store["fields"])
            row.update(values)
            row[store["id_field"]] = record_id
            writer.writerow(row)
    return Path(path)


def _rewrite(path, old, new):
    """整文件替换一个子串（模拟外部编辑器改 CSV）。"""
    text = path.read_text(encoding="utf-8-sig").replace(old, new)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(text)
    return path


# --- 第一组：五表参数化——预览不落盘 / 落盘往返 + 留痕 / 两类冲突 --------------


@pytest.mark.parametrize("store_key,record_id,values", CASES)
def test_preview_does_not_touch_the_csv(ws, store_key, record_id, values):
    path = _seed(ws, store_key, [(record_id, values)])
    before = path.read_bytes()

    errors, plan = deletes.preview_delete(store_key, record_id, ws)

    assert errors == []
    assert plan["payload"]["store"] == store_key
    assert plan["payload"]["id"] == record_id
    id_field = deletes._STORES[store_key]["id_field"]
    assert plan["payload"]["rows"][0][id_field] == record_id
    assert record_id in plan["summary"]
    # 预览是"将要落什么"的承诺：文件一个字节都不动
    assert path.read_bytes() == before


@pytest.mark.parametrize("store_key,record_id,values", CASES)
def test_apply_removes_row_and_traces_full_snapshot_outside(
        ws, outside, store_key, record_id, values):
    second = record_id[:-1] + "2"
    path = _seed(ws, store_key, [(record_id, values), (second, {})])
    errors, plan = deletes.preview_delete(store_key, record_id, ws)

    result = deletes.apply_approved_delete(plan["payload"], ws)

    store = deletes._STORES[store_key]
    assert result["written"] == 1
    assert record_id in result["summary"]
    assert [row[store["id_field"]] for row in store["read"](ws)] == [second]
    # 留痕 = 删前整表快照，且在工作区之外（同一次误操作抹不掉它）
    trace = result["trace"]
    assert os.path.isfile(trace)
    assert not os.path.abspath(trace).startswith(os.path.abspath(ws) + os.sep)
    with io.open(trace, encoding="utf-8-sig", newline="") as handle:
        traced = list(csv.DictReader(handle))
    assert [row[store["id_field"]] for row in traced] == [record_id, second]


@pytest.mark.parametrize("store_key,record_id,values", CASES)
def test_apply_conflict_when_row_changed(ws, outside, store_key, record_id, values):
    path = _seed(ws, store_key, [(record_id, values)])
    errors, plan = deletes.preview_delete(store_key, record_id, ws)
    # 模拟外部编辑器（不拿我们的锁）在预览后改了字段值
    _field, value = next(iter(values.items()))
    _rewrite(path, value, value + "改")
    before = path.read_bytes()

    with pytest.raises(tracker.ConflictError):
        deletes.apply_approved_delete(plan["payload"], ws)

    # 拒绝时一个字节都不写（保持外部编辑后的内容）
    assert path.read_bytes() == before


@pytest.mark.parametrize("store_key,record_id,values", CASES)
def test_apply_conflict_when_row_gone(ws, outside, store_key, record_id, values):
    path = _seed(ws, store_key, [(record_id, values)])
    errors, plan = deletes.preview_delete(store_key, record_id, ws)
    os.remove(path)

    with pytest.raises(tracker.ConflictError):
        deletes.apply_approved_delete(plan["payload"], ws)

    # 不重建文件、不做任何事
    assert not os.path.exists(path)


# --- 第二组：mail 深度组（预览校验 / 留痕中止 / 载荷守卫 / 登记点）------------


def test_preview_missing_id_is_an_error_not_a_silent_noop(ws):
    _seed(ws, "mails", [("M001", {"主题": "面试邀约"})])
    errors, plan = deletes.preview_delete_mail("M999", ws)
    assert plan is None
    assert any("找不到" in error for error in errors)


def test_preview_rejects_duplicate_ids(ws):
    path = _seed(ws, "mails", [("M001", {"主题": "面试邀约"}),
                               ("M002", {"主题": "笔试通知"})])
    # CSV 可手改：重复 id 会让"删一条"变成"带走两行"——预览期就拒
    _rewrite(path, "M002", "M001")
    errors, plan = deletes.preview_delete_mail("M001", ws)
    assert plan is None
    assert any("重复" in error for error in errors)


def test_preview_rejects_empty_id(ws):
    errors, plan = deletes.preview_delete_mail("", ws)
    assert plan is None
    assert any("缺少记录 id" in error for error in errors)


def test_apply_aborts_when_trace_cannot_be_written(ws, tmp_path, monkeypatch):
    """留痕写不出来 → 中止删除、零字节改动（无痕删除违背承诺，宁可不动）。"""
    path = _seed(ws, "mails", [("M001", {"主题": "面试邀约"})])
    errors, plan = deletes.preview_delete_mail("M001", ws)
    # 把留痕根指到一个「文件」上：makedirs 必然失败（NotADirectoryError ⊂ OSError）
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(deletes.pathres, "snapshot_root", lambda: str(blocker))
    before = path.read_bytes()

    with pytest.raises(tracker.ConflictError):
        deletes.apply_approved_mail_delete(plan["payload"], ws)

    assert path.read_bytes() == before
    assert len(tracker.read_mails(ws)) == 1


def test_apply_rejects_payload_without_fingerprint(ws, outside):
    _seed(ws, "mails", [("M001", {"主题": "面试邀约"})])
    with pytest.raises(tracker.ConflictError):
        deletes.apply_approved_mail_delete({"store": "mails", "id": "M001"}, ws)


def test_apply_rejects_unknown_store(ws):
    with pytest.raises(tracker.ConflictError):
        deletes.apply_approved_delete({"store": "nope", "id": "X", "rows": [{}]}, ws)


def test_registry_has_all_delete_operations():
    from jobws_core import approval  # noqa: E402

    pairs = [
        ("mail.delete", deletes.apply_approved_mail_delete),
        ("interview.delete", deletes.apply_approved_interview_delete),
        ("contact.delete", deletes.apply_approved_contact_delete),
        ("talk.delete", deletes.apply_approved_talk_delete),
        ("offer.delete", deletes.apply_approved_offer_delete),
    ]
    for name, handler in pairs:
        assert approval._OPERATIONS.get(name) is handler, name
