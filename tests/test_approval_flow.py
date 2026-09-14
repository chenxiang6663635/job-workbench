# -*- coding: utf-8 -*-
"""两段式写入协议的**端到端**回归（真实操作 + 字节级断言）。

`tests/test_approval.py` 测协议外壳（用假操作）；这里测真东西：新增投递与
批量导入走完「预览 → 落盘」两段，落盘前后用**文件字节**说话——

- 预览阶段：`tracker.csv` 的字节必须**一个不差**（"不落盘"不是打印一句就算了）；
- 落盘阶段：字节真的变了，且新记录/时间线都在。

冲突路径同样钉住：预览之后数据变了，apply 必须**拒绝**而不是"照旧写下去"。
"""

import argparse
import io
import os
import sys

import pytest

# 自插 sys.path：不能指望"别的测试模块先被导入时顺手插好"——单独跑本文件
# （pytest 直接收一个文件）时那条隐式依赖就断了（本次实测踩到）。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import approval  # noqa: E402
import init_workspace  # noqa: E402
import tracker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_token_store(tmp_path, monkeypatch):
    """令牌目录挪进 tmp_path——不碰真实临时目录，也避免用例之间互相看见。"""
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval, "_store_dir", lambda: str(store))


def _make_ws(tmp_path):
    """最小工作区：只要一张带头的主表（history.csv 由 append_history 自己建）。"""
    ws = tmp_path / "ws"
    tracking = ws / "05_投递追踪"
    tracking.mkdir(parents=True)
    with io.open(str(tracking / "tracker.csv"), "w",
                 encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(tracker.FIELDS) + "\n")
    return ws


def _add_args(**overrides):
    base = dict(
        company="示例公司甲", role="示例岗位乙", direction="backend", batch="正式批",
        source=None, deadline=None, applied=None, stage="待投", reason=None,
        next=None, next_date=None, resume=None, score=None, archive=None,
        note=None, preview=True,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _csv_bytes(ws):
    return (ws / "05_投递追踪" / "tracker.csv").read_bytes()


def _tracking_snapshot(ws):
    """整个 `05_投递追踪` 目录的快照（相对路径 → 字节）。

    只断言 tracker.csv 是不够的：预览若顺手写了 history.csv、或建了隔离目录，
    那种盲区**照样绿**（独立审查 m4）。快照把这块网补上。
    """
    root = ws / "05_投递追踪"
    return {str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def test_add_preview_is_byte_identical_then_apply_writes(tmp_path):
    """新增：预览字节级不变；凭令牌落盘后记录与时间线都在。"""
    ws = _make_ws(tmp_path)
    before = _csv_bytes(ws)
    snapshot = _tracking_snapshot(ws)

    errors, plan = tracker.preview_add(_add_args(), str(ws))
    assert errors == [] and plan
    token = approval.preview("track.add", str(ws), plan["payload"],
                             plan["summary"], plan["diff"], plan["targets"])

    assert _csv_bytes(ws) == before, "预览阶段必须字节级不变"
    assert _tracking_snapshot(ws) == snapshot, "预览阶段整个追踪目录都不许动"

    result = approval.apply(token["token"])

    assert result["id"] == "A001"
    after = _csv_bytes(ws).decode("utf-8-sig")
    assert "示例公司甲" in after and "示例岗位乙" in after
    history = (ws / "05_投递追踪" / "history.csv").read_text(encoding="utf-8-sig")
    assert "创建" in history, "新建也要入账时间线（停留天数的基准）"


def test_add_validation_errors_never_produce_a_token(tmp_path):
    """校验不过时连令牌都不该生成——两段式的第一步就不放行。"""
    ws = _make_ws(tmp_path)

    errors, plan = tracker.preview_add(_add_args(company=""), str(ws))

    assert errors and plan is None
    assert "`--company` 不能为空" in errors[0]


def test_add_conflict_after_preview_is_refused(tmp_path):
    """预览之后有人加了同公司+岗位：apply 拒绝，而不是硬写第二条。"""
    ws = _make_ws(tmp_path)
    errors, plan = tracker.preview_add(_add_args(), str(ws))
    assert errors == []
    token = approval.preview("track.add", str(ws), plan["payload"],
                             plan["summary"], plan["diff"], plan["targets"])

    tracker.apply_approved_add(plan["payload"], str(ws))  # 模拟"别处先写了一条"
    after_first = _csv_bytes(ws)

    with pytest.raises(approval.ApprovalConflict) as ei:
        approval.apply(token["token"])

    assert "已存在相同公司+岗位" in str(ei.value)
    assert _csv_bytes(ws) == after_first, "冲突时不许再动数据"


def test_import_preview_is_byte_identical_then_apply_writes(tmp_path):
    """批量导入：预览字节级不变；apply 后 ok 行入库。"""
    ws = _make_ws(tmp_path)
    before = _csv_bytes(ws)

    snapshot = _tracking_snapshot(ws)
    csv_rows = [{"公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
                 "批次": "正式批", "当前阶段": "待投"}]
    preview = tracker.preview_import(csv_rows, workspace=str(ws))
    assert len(preview["ok"]) == 1 and not preview["error"]
    token = approval.preview("track.import", str(ws), {"preview": preview},
                             "导入 1 条投递记录", ["| 状态 |"], [])

    assert _csv_bytes(ws) == before, "预览阶段必须字节级不变"
    assert _tracking_snapshot(ws) == snapshot, "预览阶段整个追踪目录都不许动"

    result = approval.apply(token["token"])

    assert result["written"] == 1
    after = _csv_bytes(ws).decode("utf-8-sig")
    assert "示例公司甲" in after


def test_import_conflict_after_preview_is_refused(tmp_path):
    """预览之后出现同公司+岗位：整批拒绝（沿用 commit_import 的锁内重校验）。"""
    ws = _make_ws(tmp_path)
    csv_rows = [{"公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
                 "批次": "正式批", "当前阶段": "待投"}]
    preview = tracker.preview_import(csv_rows, workspace=str(ws))
    token = approval.preview("track.import", str(ws), {"preview": preview},
                             "导入 1 条投递记录", ["| 状态 |"], [])

    tracker.apply_approved_add({"fields": dict(csv_rows[0])}, str(ws))
    after_first = _csv_bytes(ws)

    with pytest.raises(approval.ApprovalConflict):
        approval.apply(token["token"])

    assert _csv_bytes(ws) == after_first


def _seed_one(ws):
    tracker.apply_approved_add({"fields": {
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"}}, str(ws))


def test_update_preview_is_byte_identical_then_apply_writes(tmp_path):
    """更新：预览字节级不变；apply 后字段与时间线都变了。"""
    ws = _make_ws(tmp_path)
    _seed_one(ws)
    snapshot = _tracking_snapshot(ws)

    payload = {"id": "A001", "changes": {"当前阶段": "一面", "下次动作": "准备项目口述"}}
    errors, plan = tracker.preview_update_fields(payload, str(ws))
    assert errors == [] and plan
    token = approval.preview("track.update", str(ws), plan["payload"],
                             plan["summary"], plan["diff"], plan["targets"])

    assert _tracking_snapshot(ws) == snapshot, "预览阶段整个追踪目录都不许动"

    result = approval.apply(token["token"])

    assert result["id"] == "A001"
    after = _csv_bytes(ws).decode("utf-8-sig")
    assert "一面" in after and "准备项目口述" in after
    history = (ws / "05_投递追踪" / "history.csv").read_text(encoding="utf-8-sig")
    assert "当前阶段" in history, "更新要按字段级差异入账时间线"


def test_update_terminal_rollback_is_refused_at_preview(tmp_path):
    """终态不回退：预览阶段就拦（不必等到 apply 才报）。"""
    ws = _make_ws(tmp_path)
    tracker.apply_approved_add({"fields": {
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "已挂", "状态原因": "面试未通过"}}, str(ws))

    errors, plan = tracker.preview_update_fields(
        {"id": "A001", "changes": {"当前阶段": "一面"}}, str(ws))

    assert errors and plan is None


def test_init_preview_creates_nothing_then_apply_creates(tmp_path):
    """init 的两段式：预览连目标目录都不该建；apply 后工作区真的立起来。"""
    target = tmp_path / "new-ws"

    errors, plan = init_workspace.plan_init(str(target), demo=True)

    assert errors == [] and plan
    assert not target.exists(), "预览阶段连目标目录都不该建"
    assert "新建" in plan["summary"]

    token = approval.preview("init", str(target), plan["payload"], plan["summary"],
                             plan["diff"], plan["targets"])
    result = approval.apply(token["token"])

    assert result["written"] > 0
    assert (target / "05_投递追踪" / "tracker.csv").is_file()
    assert (target / "AGENTS.md").is_file()


def test_init_preview_surfaces_overwrites(tmp_path):
    """目标已有数据时，预览必须把「将覆盖」摆在明面上。

    demo 数据落在已经填了真实数据的工作区上就是数据丢失——用户有权在**落盘之前**
    看到"哪几个文件会被盖掉"，而不是事后读一句"已覆盖 N 个"。
    """
    target = tmp_path / "ws"
    (target / "05_投递追踪").mkdir(parents=True)
    (target / "05_投递追踪" / "tracker.csv").write_text(
        "id,公司\nA001,我自己的数据\n", encoding="utf-8")

    errors, plan = init_workspace.plan_init(str(target), demo=True)

    assert errors == []
    # 两个词都要在：只有"新建"没有"覆盖"说明覆盖清单漏了（反之亦然）
    assert "覆盖" in plan["summary"] and "新建" in plan["summary"]
    assert any("将覆盖" in line for line in plan["diff"]), plan["diff"]


def test_init_force_path_survives_apply(tmp_path):
    """对着非空目录（`--force`）的两段式也要能走通。

    安全默认是"目标非空就拒绝"，但用户当初**就是**对着非空目录预览的——载荷里
    记着 force，apply 不该反悔；否则这条路根本走不通（`-force` 形同虚设）。
    """
    target = tmp_path / "ws"
    (target / "05_投递追踪").mkdir(parents=True)
    (target / "05_投递追踪" / "tracker.csv").write_text(
        "id,公司\nA001,我自己的数据\n", encoding="utf-8")

    errors, plan = init_workspace.plan_init(str(target), demo=True, force=True)
    assert errors == []
    assert plan["payload"]["force"] is True

    token = approval.preview("init", str(target), plan["payload"], plan["summary"],
                             plan["diff"], plan["targets"])
    result = approval.apply(token["token"])

    assert result["written"] > 0
    tracker_csv = (target / "05_投递追踪" / "tracker.csv").read_text(encoding="utf-8-sig")
    assert "我自己的数据" not in tracker_csv, "demo 数据应已覆盖旧内容"
