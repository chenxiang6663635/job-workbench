# -*- coding: utf-8 -*-
"""v0.4.0-A 前三个子项的数据层回归（链接列 / 来源自检 / 阶段词表）。

钉四件，每一件都对应一个真实会出事的口径：

1. **新列缺列兼容**：旧工作区的 CSV 没有「链接」列——读回、写入、自检全链路
   都要像没这回事一样工作，写回时再把新列补出来（即「零迁移」的工程含义）。
2. **来源纳入自检**：手改 CSV 填了枚举外的来源值必须被点名——此前来源只在
   CLI/导入的写入入口校验，绕过它们之后的脏值没有任何一层拦得住。
3. **阶段词表只增不改**：旧阶段值与流转顺序是历史数据、筛选与解析器的共同
   契约；新增值必须放在正确的相邻位置（顺序即单调覆盖语义）。
4. **单调性回归**：`status_parse` 对新增阶段的强弱判定与设计一致。
"""

import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import status_parse  # noqa: E402
import tracker  # noqa: E402

# 旧格式 = 当前 FIELDS 去掉「链接」列；从 FIELDS 派生而不是抄一份字面量，
# 免得以后再加列时这份「旧格式」跟着一起长（那就测不出缺列兼容了）。
OLD_FIELDS = [f for f in tracker.FIELDS if f != "链接"]


def _ws(tmp_path):
    ws = os.path.join(str(tmp_path), "ws")
    os.makedirs(os.path.join(ws, "05_投递追踪"))
    return ws


def _write_old_style(path, row):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OLD_FIELDS, extrasaction="ignore",
                                restval="")
        writer.writeheader()
        writer.writerow(row)


def _old_row(**overrides):
    row = {field: "" for field in OLD_FIELDS}
    row.update({"id": "A001", "公司": "示例公司", "岗位": "示例岗位",
                "方向": "other", "批次": "正式批", "来源": "内推",
                "投递日期": "2026-09-01", "当前阶段": "已投"})
    row.update(overrides)
    return row


def _tracker_path(ws):
    return os.path.join(ws, "05_投递追踪", "tracker.csv")


# --- 1. 缺列兼容 ---------------------------------------------------------------

def test_old_csv_without_link_column_still_reads(tmp_path):
    ws = _ws(tmp_path)
    _write_old_style(_tracker_path(ws), _old_row())
    rows = tracker.read_rows(ws)
    assert len(rows) == 1
    assert (rows[0].get("链接") or "") == ""


def test_write_rows_backfills_the_link_column(tmp_path):
    """写回时补出新列：旧文件第一行数据不丢，新列出现且值为空。"""
    ws = _ws(tmp_path)
    path = _tracker_path(ws)
    _write_old_style(path, _old_row())
    rows = tracker.read_rows(ws)
    rows[0]["链接"] = "https://example.com/job/1"
    tracker.write_rows(rows, ws)

    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert "链接" in (reader.fieldnames or [])
        again = [dict(r) for r in reader]
    assert again[0]["链接"] == "https://example.com/job/1"
    assert again[0]["公司"] == "示例公司"


def test_run_check_passes_on_old_csv_without_link_column(tmp_path):
    """旧表（无链接列）自检不报问题——「缺列」不是数据错误，是历史格式。"""
    ws = _ws(tmp_path)
    _write_old_style(_tracker_path(ws), _old_row())
    result = tracker.run_check(ws)
    bad = [(f["file"], f["issues"]) for f in result["files"] if not f["ok"]]
    assert bad == []


# --- 2. 来源纳入自检 -----------------------------------------------------------

def test_run_check_flags_unknown_source(tmp_path):
    ws = _ws(tmp_path)
    _write_old_style(_tracker_path(ws), _old_row(来源="某招聘 App"))
    result = tracker.run_check(ws)
    issues = next(f for f in result["files"] if f["file"] == "tracker.csv")["issues"]
    assert any("来源" in issue and "某招聘 App" in issue for issue in issues), issues
    assert result["ok"] is False


def test_run_check_flags_unknown_stage_with_new_values_registered(tmp_path):
    """反向确认：新阶段值（AI面）是合法值，不会被自检误伤。"""
    ws = _ws(tmp_path)
    _write_old_style(_tracker_path(ws), _old_row(当前阶段="AI面"))
    result = tracker.run_check(ws)
    bad = [(f["file"], f["issues"]) for f in result["files"] if not f["ok"]]
    assert bad == []


def test_new_sources_pass_the_check(tmp_path):
    for source in ("宣讲会", "招聘会"):
        assert source in tracker.SOURCES, "%s 未登记进 SOURCES" % source


def test_source_order_is_activity_after_referral():
    """「宣讲会 / 招聘会」插在「内推」之后、「其他」之前（顺序影响下拉展示）。"""
    assert tracker.SOURCES.index("内推") < tracker.SOURCES.index("宣讲会")
    assert tracker.SOURCES.index("招聘会") < tracker.SOURCES.index("其他")


# --- 3. 词表只增不改 -----------------------------------------------------------

def test_legacy_stage_values_are_untouched():
    """旧值一个都不能少——历史 CSV、筛选、解析器都按它们记账。"""
    for value in ("待投", "已投", "笔试", "一面", "二面", "三面", "HR面",
                  "offer", "签约"):
        assert value in tracker.STAGES, value
    for value in ("已挂", "已放弃", "我拒绝的 offer"):
        assert value in tracker.TERMINAL_STAGES, value


def test_new_stages_sit_in_the_right_neighbourhood():
    """顺序即单调语义：新阶段与相邻阶段的先后关系写死，防止挪位悄悄改变判定。"""
    def idx(stage):
        return tracker.STAGES.index(stage)

    assert idx("已投") < idx("测评") < idx("笔试")
    assert idx("笔试") < idx("AI面") < idx("群面") < idx("一面")
    assert idx("三面") < idx("HR面") < idx("终面") < idx("offer")


def test_interview_rounds_cover_new_stages():
    for value in ("测评", "AI面", "群面", "终面"):
        assert value in tracker.INTERVIEW_ROUNDS, value


def test_link_is_updatable_and_in_both_tables():
    assert "链接" in tracker.FIELDS
    assert "链接" in tracker.INTERVIEW_FIELDS
    assert "链接" in tracker.UPDATABLE


def test_preview_add_normalises_source_whitespace(tmp_path):
    """带空格的来源在预览入口就归一：不能「strip 后校验、原样落盘」（独立审查）。"""
    ws = _ws(tmp_path)
    errors, plan = tracker.preview_add_fields({
        "公司": "示例公司", "岗位": "示例岗位", "方向": "other",
        "批次": "正式批", "当前阶段": "待投", "来源": " 内推 "}, ws)
    assert errors == [] and plan
    assert plan["payload"]["fields"]["来源"] == "内推"


def test_preview_update_normalises_link_whitespace(tmp_path):
    """update 与 add 同一口径：链接在任何写路径都 strip 后落盘（独立审查 m1）。"""
    ws = _ws(tmp_path)
    row = {field: "" for field in tracker.FIELDS}
    row.update({"id": "A001", "公司": "示例公司", "岗位": "示例岗位",
                "方向": "other", "批次": "正式批", "当前阶段": "已投"})
    tracker.write_rows([row], ws)
    errors, plan = tracker.preview_update_fields(
        {"id": "A001", "changes": {"链接": " https://example.com/j "}}, ws)
    assert errors == [] and plan
    assert plan["payload"]["changes"]["链接"] == "https://example.com/j"


# --- 4. 单调性回归（解析器与词表共用口径）------------------------------------

def test_stage_rank_follows_the_new_order():
    assert status_parse.stage_rank("测评") < status_parse.stage_rank("笔试")
    assert status_parse.stage_rank("笔试") < status_parse.stage_rank("AI面")
    assert status_parse.stage_rank("AI面") < status_parse.stage_rank("一面")
    assert status_parse.stage_rank("HR面") < status_parse.stage_rank("终面")


def test_can_override_supports_the_new_stages():
    assert status_parse.can_override("AI面", "一面")[0] is True
    assert status_parse.can_override("一面", "AI面")[0] is False
    assert status_parse.can_override("测评", "笔试")[0] is True
    assert status_parse.can_override("群面", "一面")[0] is True
    assert status_parse.can_override("终面", "offer")[0] is True
