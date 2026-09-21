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
import re
import sys
from pathlib import Path

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from jobws_core import tracker  # noqa: E402
from jobws_core.tracker import application_delete, deletes  # noqa: E402


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


# --- 第三组：CLI（经统一入口 jobws）-------------------------------------------
#
# 删除永远两段式：CLI 只发令牌，`jobws apply <令牌>` 才落盘。这组网跟着**用户
# 实际走的路**（jobws 统一入口），而不是各模块的 main()——B8 入口统一的教训。


def _invoke_jobws(monkeypatch, capsys, argv):
    """经统一入口调一次命令（与 test_cli_surface 同款）。"""
    import jobws  # noqa: E402  （tools/ 已在文件顶部进 sys.path）

    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        result = jobws.main()
        code = 0 if result is None else result
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


CLI_SUB = {"mails": "mail", "interviews": "interview", "contacts": "contact",
           "talks": "talk", "offers": "offer"}


@pytest.mark.parametrize("store_key,record_id,values", CASES)
def test_cli_delete_previews_without_writing(ws, outside, monkeypatch, capsys,
                                             store_key, record_id, values):
    path = _seed(ws, store_key, [(record_id, values)])
    before = path.read_bytes()

    code, out = _invoke_jobws(
        monkeypatch, capsys,
        ["track", "--workspace", ws, CLI_SUB[store_key], "delete", "--id", record_id])

    assert code == 0
    assert "预览（未删除）" in out
    assert "要落盘请执行" in out
    assert path.read_bytes() == before


def test_cli_delete_then_apply_lands_with_trace(ws, outside, monkeypatch, capsys):
    """端到端：CLI 预览拿令牌 → `jobws apply` 落盘 → 行删了 + 留痕在。"""
    _seed(ws, "mails", [("M001", {"主题": "面试邀约"}),
                        ("M002", {"主题": "笔试通知"})])
    code, out = _invoke_jobws(
        monkeypatch, capsys,
        ["track", "--workspace", ws, "mail", "delete", "--id", "M001"])
    assert code == 0
    match = re.search(r"apply ([0-9a-f]{32})", out)
    assert match, out
    token = match.group(1)

    code, out = _invoke_jobws(monkeypatch, capsys, ["apply", token, "--workspace", ws])

    assert code == 0
    assert "已执行" in out
    assert "留痕" in out
    assert [row["邮件id"] for row in tracker.read_mails(ws)] == ["M002"]


def test_cli_delete_missing_id_exits_one(ws, outside, monkeypatch, capsys):
    _seed(ws, "mails", [("M001", {"主题": "面试邀约"})])

    code, out = _invoke_jobws(
        monkeypatch, capsys,
        ["track", "--workspace", ws, "mail", "delete", "--id", "M999"])

    assert code == 1
    assert "找不到" in out


# --- 第四组：投递删除（解绑联动 + 时间线追记）--------------------------------


def _seed_application(ws, rows):
    """主表种子：rows = [(id, {字段: 值}), ...]。"""
    path = os.path.join(ws, "05_投递追踪", "tracker.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for record_id, values in rows:
            row = dict((field, "") for field in tracker.FIELDS)
            row.update(values)
            row["id"] = record_id
            writer.writerow(row)
    return Path(path)


def test_preview_application_delete_lists_unbind_candidates(ws, outside):
    """差异表逐条列出将解绑的关联记录（"哪几条"正是判断依据），且不落盘。"""
    app_path = _seed_application(ws, [
        ("A001", {"公司": "TCL", "岗位": "前端开发", "当前阶段": "已投"}),
        ("A002", {"公司": "格力", "岗位": "后端", "当前阶段": "已投"})])
    mail_path = _seed(ws, "mails", [("M001", {"主题": "面试邀约",
                                              "关联记录": "A001"})])
    itv_path = _seed(ws, "interviews", [("I001", {"公司": "TCL", "轮次": "一面",
                                                   "关联记录": "A001"})])
    before = [p.read_bytes() for p in (app_path, mail_path, itv_path)]

    errors, plan = application_delete.preview_delete_application("A001", ws)

    assert errors == []
    assert plan["payload"]["id"] == "A001"
    assert plan["payload"]["unbind"]["mails"][0]["邮件id"] == "M001"
    assert plan["payload"]["unbind"]["interviews"][0]["面试id"] == "I001"
    diff = "\n".join(plan["diff"])
    assert "将解绑 2 条关联记录" in diff
    assert "M001" in diff and "I001" in diff
    assert "A001" in plan["summary"]
    # 预览是承诺：三张表一个字节都不动
    assert [p.read_bytes() for p in (app_path, mail_path, itv_path)] == before


def test_apply_application_delete_unbinds_and_records_history(ws, outside):
    _seed_application(ws, [
        ("A001", {"公司": "TCL", "岗位": "前端开发", "当前阶段": "已投"}),
        ("A002", {"公司": "格力", "岗位": "后端", "当前阶段": "已投"})])
    _seed(ws, "mails", [("M001", {"主题": "面试邀约", "关联记录": "A001"}),
                        ("M002", {"主题": "笔试通知", "关联记录": "A002"})])
    _seed(ws, "interviews", [("I001", {"公司": "TCL", "轮次": "一面",
                                       "关联记录": "A001"})])
    errors, plan = application_delete.preview_delete_application("A001", ws)

    result = application_delete.apply_approved_application_delete(plan["payload"], ws)

    assert result["written"] == 1
    assert result["unbound"] == 2
    assert "已删除投递：A001" in result["summary"]
    assert "并解绑 2 条关联记录" in result["summary"]
    # 主表少一行、别家不动
    assert [row["id"] for row in tracker.read_rows(ws)] == ["A002"]
    # 从表保留行、仅外键清空（别家的关联一字不动）
    mails = tracker.read_mails(ws)
    assert [row["邮件id"] for row in mails] == ["M001", "M002"]
    assert mails[0]["关联记录"] == ""
    assert mails[1]["关联记录"] == "A002"
    assert tracker.read_interviews(ws)[0]["关联记录"] == ""
    # 时间线不删、追记一条「已删除」
    assert any(entry["id"] == "A001" and entry["新值"] == "已删除"
               for entry in tracker.read_history(ws))
    # 留痕：主表 + 每张被解绑的从表各一份「改前整表」快照，都在工作区之外
    traces = result["trace"].split(";")
    assert len(traces) == 3
    names = sorted(os.path.basename(trace) for trace in traces)
    assert any(name.startswith("applications-before-delete") for name in names)
    assert any(name.startswith("mails-before-delete") for name in names)
    assert any(name.startswith("interviews-before-delete") for name in names)
    for trace in traces:
        assert os.path.isfile(trace)
        assert not os.path.abspath(trace).startswith(os.path.abspath(ws) + os.sep)


def test_apply_application_delete_conflict_when_linked_row_changed(ws, outside):
    """任一待解绑行被改过 → 整体拒绝，主表与从表都零字节改动。"""
    app_path = _seed_application(ws, [
        ("A001", {"公司": "TCL", "岗位": "前端开发", "当前阶段": "已投"})])
    mail_path = _seed(ws, "mails", [("M001", {"主题": "面试邀约",
                                              "关联记录": "A001"})])
    errors, plan = application_delete.preview_delete_application("A001", ws)
    _rewrite(mail_path, "面试邀约", "面试邀约（改过）")
    before = [p.read_bytes() for p in (app_path, mail_path)]

    with pytest.raises(tracker.ConflictError):
        application_delete.apply_approved_application_delete(plan["payload"], ws)

    assert [p.read_bytes() for p in (app_path, mail_path)] == before


def test_apply_application_delete_without_links(ws, outside):
    _seed_application(ws, [("A001", {"公司": "TCL", "岗位": "前端开发"})])
    errors, plan = application_delete.preview_delete_application("A001", ws)
    assert not plan["payload"]["unbind"]

    result = application_delete.apply_approved_application_delete(plan["payload"], ws)

    assert result["written"] == 1
    assert result["unbound"] == 0
    assert tracker.read_rows(ws) == []


def test_preview_application_delete_missing_id(ws):
    errors, plan = application_delete.preview_delete_application("A999", ws)
    assert plan is None
    assert any("找不到" in error for error in errors)


def test_cli_application_delete_previews_and_lands(ws, outside, monkeypatch, capsys):
    """端到端：`track delete --id` 预览（含解绑清单）→ `jobws apply` 落盘。"""
    _seed_application(ws, [("A001", {"公司": "TCL", "岗位": "前端开发",
                                     "当前阶段": "已投"})])
    _seed(ws, "mails", [("M001", {"主题": "面试邀约", "关联记录": "A001"})])

    code, out = _invoke_jobws(
        monkeypatch, capsys,
        ["track", "--workspace", ws, "delete", "--id", "A001"])

    assert code == 0
    assert "将解绑 1 条关联记录" in out
    match = re.search(r"apply ([0-9a-f]{32})", out)
    assert match, out

    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["apply", match.group(1), "--workspace", ws])

    assert code == 0
    assert tracker.read_rows(ws) == []
    assert tracker.read_mails(ws)[0]["关联记录"] == ""
