# -*- coding: utf-8 -*-
"""题库 `questions.csv`：领域层、1a 的 Markdown 解析与两段式导入。

钉住四件事：
1. **数据层**：写入 → 读回一致；旧文件缺新列时由原子写补空（不落 None）；
2. **1a 解析**：`03_面试准备/**/*.md` 只读解析——模板与 README 不算题，领域取
   子目录、题目取一级标题（没标题时退回文件名）；
3. **两段式**：预览一个字节都不落盘；重复题跳过；空载荷 / 全重复在落盘段被拒；
4. **枚举**：状态 / 来源 / 难度非法即报错——预览与落盘**共用同一校验**（改一个
   值就能让两段行为分叉的写法要在这里红）。
"""

import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import question_bank  # noqa: E402
import tracker  # noqa: E402


@pytest.fixture()
def ws(tmp_path):
    """最小工作区：只要有 05_投递追踪 目录就够题库落盘。"""
    path = tmp_path / "ws"
    (path / "05_投递追踪").mkdir(parents=True)
    return str(path)


def _write_md(workspace, rel, text):
    path = os.path.join(workspace, "03_面试准备", rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _add(workspace, title, domain="", **extra):
    fields = {"题目": title, "领域": domain}
    fields.update(extra)
    errors, plan = question_bank.preview_add_fields(fields, workspace)
    assert not errors, errors
    return question_bank.apply_approved_add(plan["payload"], workspace)


# --- 1. 数据层 ---------------------------------------------------------------


def test_empty_bank_reads_as_empty(ws):
    assert question_bank.read_questions(ws) == []


def test_add_then_read_roundtrip(ws):
    result = _add(ws, "讲讲 TCP 三次握手", "技术面", 科目="网络")
    assert result["id"] == "Q001"
    rows = question_bank.read_questions(ws)
    assert len(rows) == 1
    assert rows[0]["题目"] == "讲讲 TCP 三次握手"
    assert rows[0]["状态"] == "未看"          # 默认未看
    assert rows[0]["来源"] == "自拟"          # 默认自拟
    assert rows[0]["创建日期"]                # 落成当天


def test_filters_are_applied(ws):
    _add(ws, "A 题", "技术面", 科目="网络")
    _add(ws, "B 题", "行为面", 科目="沟通")
    assert len(question_bank.read_questions(ws, domain="技术面")) == 1
    assert len(question_bank.read_questions(ws, keyword="沟通")) == 1
    assert question_bank.read_questions(ws, keyword="沟通")[0]["题目"] == "B 题"
    assert question_bank.read_questions(ws, status="会了") == []


def test_legacy_file_without_new_columns_is_backfilled(ws):
    """旧题库（少几列）读回再写，所有列都要齐——否则下游按列名取值会得到 None。"""
    path = question_bank.question_path(ws)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("题目id,题目\nQ001,老题\n")
    rows = question_bank.read_questions(ws)
    question_bank.write_questions(rows, ws)
    written = question_bank.read_questions(ws)
    assert set(written[0]) == set(tracker.QUESTION_FIELDS)
    assert written[0]["答案要点"] == ""       # 补的是空串，不是 None


def test_next_question_id_increments(ws):
    assert question_bank.next_question_id([]) == "Q001"
    _add(ws, "A")
    rows = question_bank.read_questions(ws)
    assert question_bank.next_question_id(rows) == "Q002"


# --- 2/4. 校验与预览 ---------------------------------------------------------


def test_preview_add_rejects_bad_status(ws):
    errors, plan = question_bank.preview_add_fields(
        {"题目": "A", "状态": "学会了"}, ws)
    assert plan is None
    assert any("状态" in e for e in errors)


def test_preview_add_rejects_duplicate(ws):
    _add(ws, "同一道题", "技术面")
    errors, plan = question_bank.preview_add_fields({"题目": "同一道题", "领域": "技术面"}, ws)
    assert plan is None
    assert any("已存在" in e for e in errors)


# --- 3. 1a：Markdown 只读解析 ------------------------------------------------


def test_scan_skips_templates_and_readme(ws):
    _write_md(ws, "README.md", "# 说明\n\n不是题。\n")
    _write_md(ws, "行为面/_模板_行为故事.md", "# 行为故事：模板\n\n留空。\n")
    _write_md(ws, "技术面/tcp.md", "# 讲讲 TCP 三次握手\n\n正文。\n")
    items = question_bank.scan_markdown(ws)
    assert [i["题目"] for i in items] == ["讲讲 TCP 三次握手"]
    assert items[0]["领域"] == "技术面"


def test_scan_falls_back_to_filename_without_heading(ws):
    _write_md(ws, "技术面/网络/udp.md", "没有一级标题的一段话。\n")
    items = question_bank.scan_markdown(ws)
    assert items[0]["题目"] == "udp"
    assert items[0]["科目"] == "网络"          # 领域=技术面，科目=下一级目录


def test_scan_strips_code_fences_and_tables(ws):
    _write_md(ws, "技术面/x.md", "# 题目 X\n\n```python\nprint(1)\n```\n\n| a | b |\n|---|---|\n\n正文要点。\n")
    items = question_bank.scan_markdown(ws)
    assert "print(1)" not in items[0]["答案要点"]
    assert "| a | b |" not in items[0]["答案要点"]
    assert "正文要点" in items[0]["答案要点"]


def test_scan_on_missing_module_dir_returns_empty(ws):
    assert question_bank.scan_markdown(ws) == []


# --- 3. 1a：两段式导入 -------------------------------------------------------


def test_import_preview_does_not_touch_disk(ws):
    _write_md(ws, "技术面/tcp.md", "# TCP\n\n要点。\n")
    errors, plan = question_bank.preview_import(ws)
    assert not errors
    assert "导入 1 道题" in plan["summary"]
    assert not os.path.exists(question_bank.question_path(ws))   # 预览不落盘


def test_import_apply_writes_rows(ws):
    _write_md(ws, "技术面/tcp.md", "# TCP\n\n要点。\n")
    _write_md(ws, "技术面/udp.md", "# UDP\n\n要点。\n")
    _errors, plan = question_bank.preview_import(ws)
    result = question_bank.apply_approved_import(plan["payload"], ws)
    assert result["written"] == 2
    rows = question_bank.read_questions(ws)
    assert [r["题目"] for r in rows] == ["TCP", "UDP"]
    assert all(r["来源"] == "导入" for r in rows)
    assert all(r["最近复习"] == "" for r in rows)   # 导入不等于复习过


def test_second_import_reports_nothing_new(ws):
    _write_md(ws, "技术面/tcp.md", "# TCP\n\n要点。\n")
    _errors, plan = question_bank.preview_import(ws)
    question_bank.apply_approved_import(plan["payload"], ws)
    errors, second = question_bank.preview_import(ws)
    assert second is None
    assert any("都已入题库" in e for e in errors)


def test_import_of_only_templates_is_rejected(ws):
    _write_md(ws, "行为面/_模板_行为故事.md", "# 模板\n")
    errors, plan = question_bank.preview_import(ws)
    assert plan is None
    assert any("没有可导入" in e for e in errors)


def test_apply_rejects_empty_payload(ws):
    with pytest.raises(tracker.ConflictError):
        question_bank.apply_approved_import({"items": []}, ws)


def test_apply_rejects_all_duplicate_payload(ws):
    """预览之后题库被别人写满同名题 → 落盘段必须整体拒绝，而不是静默写 0 条。"""
    _add(ws, "TCP", "技术面")
    with pytest.raises(tracker.ConflictError):
        question_bank.apply_approved_import(
            {"items": [{"题目": "TCP", "领域": "技术面"}]}, ws)


def test_update_changes_status_and_stamps_review_date(ws):
    """状态改为「会了」时自动记最近复习——复习过就该有日期，不靠用户另填一次。"""
    _add(ws, "TCP", "技术面")
    errors, plan = question_bank.preview_update_fields("Q001", {"状态": "会了"}, ws)
    assert not errors, errors
    question_bank.apply_approved_update(plan["payload"], ws)
    row = question_bank.read_questions(ws)[0]
    assert row["状态"] == "会了"
    assert row["最近复习"]


def test_update_rejects_unknown_id(ws):
    errors, plan = question_bank.preview_update_fields("Q999", {"状态": "看过"}, ws)
    assert plan is None
    assert any("找不到" in e for e in errors)


def test_scan_reports_unreadable_and_empty_files(ws):
    """读不动 / 没有正文的文件必须进跳过清单——在"预览即承诺"的两段式里，
    少给题比报错更危险（用户会以为就这些）。"""
    _write_md(ws, "技术面/tcp.md", "# TCP\n\n要点。\n")
    _write_md(ws, "技术面/empty.md", "")
    skipped = []
    items = question_bank.scan_markdown(ws, skipped=skipped)
    assert [i["题目"] for i in items] == ["TCP"]
    assert any("empty.md" in path for path, _reason in skipped)
