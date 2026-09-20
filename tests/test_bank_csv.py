# -*- coding: utf-8 -*-
"""`jobws bank export --csv` / `bank import-csv`：题库 CSV 往返的钉住用例。

钉住四条：
1. **导出**：表头与工作区一字不差（`QUESTION_FIELDS`）、utf-8-sig、**不覆盖**已存在文件；
2. **导入预览**：缺「题目」列 → 明确报错；空题目行 / 不合法行 / 重复行在预览里
   列出并跳过（CSV 是外部输入，**预览期就把校验做完**——预览说"能落"却在 apply
   被拒是最糟的体验）；未知列忽略且注明；
3. **两段式**：预览不落盘、凭令牌才写；落盘走 `question.import` 同一条通道；
4. **往返幂等**：导出再导入 = 全部「已存在，跳过」（判重键不含题目id）。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import _cli_bank  # noqa: E402
from jobws_core import approval  # noqa: E402
from jobws_core import question_bank  # noqa: E402
from jobws_core import tracker  # noqa: E402


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "ws" / "05_投递追踪").mkdir(parents=True)
    return tmp_path / "ws"


def _seed(ws, rows):
    path = ws / "05_投递追踪" / "questions.csv"
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tracker.QUESTION_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _question(qid, title, domain="技术面", subject="Redis"):
    row = dict((f, "") for f in tracker.QUESTION_FIELDS)
    row.update({"题目id": qid, "题目": title, "领域": domain, "科目": subject,
                "状态": "未看", "答案要点": "要点", "创建日期": "2026-09-19"})
    return row


def _ext_csv(path, header, rows):
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _apply_plan(plan, ws):
    result = approval.preview("question.import", str(ws), plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    return approval.apply(result["token"])


# --- 导出 -------------------------------------------------------------------


def test_export_writes_full_header_and_rows(ws, tmp_path):
    _seed(ws, [_question("Q001", "缓存雪崩"), _question("Q002", "TCP 握手")])
    out = tmp_path / "out.csv"

    count = question_bank.export_csv(str(ws), str(out))

    assert count == 2
    with io.open(str(out), "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert list(rows[0].keys()) == list(tracker.QUESTION_FIELDS)
    assert rows[0]["题目"] == "缓存雪崩"
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # utf-8-sig：Excel 双击不乱码


def test_export_refuses_to_overwrite_and_cli_exits_one(ws, tmp_path, capsys):
    _seed(ws, [_question("Q001", "缓存雪崩")])
    out = tmp_path / "out.csv"
    out.write_text("占位", encoding="utf-8")

    with pytest.raises(FileExistsError):
        question_bank.export_csv(str(ws), str(out))
    assert out.read_text(encoding="utf-8") == "占位"  # 一个字节都不动

    assert _cli_bank.main(["export", "--csv", str(out), "--workspace", str(ws)]) == 1
    assert "已存在" in capsys.readouterr().out


def test_export_cli_success_prints_count(ws, tmp_path, capsys):
    _seed(ws, [_question("Q001", "缓存雪崩")])
    out = tmp_path / "out.csv"
    assert _cli_bank.main(["export", "--csv", str(out), "--workspace", str(ws)]) == 0
    assert "已导出 1 道题" in capsys.readouterr().out


def test_export_requires_csv_option(ws):
    with pytest.raises(SystemExit) as exc:
        _cli_bank.main(["export", "--workspace", str(ws)])
    assert exc.value.code == 2


# --- 导入预览 ---------------------------------------------------------------


def test_import_preview_requires_title_column(ws, tmp_path):
    bad = _ext_csv(tmp_path / "bad.csv", ["领域", "科目"], [["技术面", "Redis"]])
    errors, plan = question_bank.preview_import_csv(str(bad), str(ws))
    assert plan is None
    assert any("「题目」列" in e for e in errors)


def test_import_preview_lists_new_and_skips(ws, tmp_path):
    _seed(ws, [_question("Q001", "缓存雪崩")])
    good = _ext_csv(
        tmp_path / "in.csv",
        ["题目", "领域", "科目", "状态"],
        [
            ["新题一", "技术面", "网络", "未看"],       # 新增
            ["缓存雪崩", "技术面", "Redis", "未看"],    # 已存在
            ["", "技术面", "网络", "未看"],             # 空题目
            ["坏状态", "技术面", "网络", "乱写的"],      # 字段不合法
        ],
    )

    errors, plan = question_bank.preview_import_csv(str(good), str(ws))

    assert errors == []
    assert [item["题目"] for item in plan["payload"]["items"]] == ["新题一"]
    merged = "\n".join(plan["diff"])
    assert "已存在，跳过" in merged
    assert "第 4 行没有题目，跳过" in merged
    assert "第 5 行跳过" in merged


def test_import_preview_notes_unknown_columns(ws, tmp_path):
    good = _ext_csv(tmp_path / "in.csv", ["题目", "心情"], [["一道题", "开心"]])
    _errors, plan = question_bank.preview_import_csv(str(good), str(ws))
    assert "忽略了未知列 心情" in "\n".join(plan["diff"])


def test_import_preview_missing_file(ws, tmp_path):
    errors, plan = question_bank.preview_import_csv(str(tmp_path / "nope.csv"), str(ws))
    assert plan is None and any("不存在" in e for e in errors)


# --- 两段式与幂等 -----------------------------------------------------------


def test_preview_touches_nothing_then_apply_writes(ws, tmp_path):
    seed_path = _seed(ws, [_question("Q001", "缓存雪崩")])
    before = seed_path.read_bytes()
    good = _ext_csv(tmp_path / "in.csv", ["题目", "领域", "科目"],
                    [["新题一", "技术面", "网络"]])

    errors, plan = question_bank.preview_import_csv(str(good), str(ws))
    assert errors == []
    assert seed_path.read_bytes() == before  # 预览一个字节都不写

    result = _apply_plan(plan, ws)

    assert result["written"] == 1
    rows = question_bank.read_questions(str(ws))
    assert [r["题目"] for r in rows] == ["缓存雪崩", "新题一"]
    # 题目id 由题库分配（输入里没有 id 列）；来源补枚举内的默认值
    assert rows[1]["题目id"] and rows[1]["来源"] == "导入"


def test_roundtrip_export_then_import_is_idempotent(ws, tmp_path):
    """导出 → 再导入 = 全部「已存在，跳过」：judge 键不含 id，不会一题两号。"""
    _seed(ws, [_question("Q001", "缓存雪崩"), _question("Q002", "TCP 握手")])
    out = tmp_path / "out.csv"
    question_bank.export_csv(str(ws), str(out))

    errors, plan = question_bank.preview_import_csv(str(out), str(ws))

    assert plan is None
    assert any("没有可新增的题目" in e and "已存在" in e for e in errors)


def test_apply_conflict_when_csv_rows_already_landed(ws, tmp_path):
    """预览之后这些题已入题库 → 落盘整批拒绝（与 Markdown 导入同一条冲突路径）。"""
    _seed(ws, [])
    good = _ext_csv(tmp_path / "in.csv", ["题目", "领域", "科目"],
                    [["新题一", "技术面", "网络"]])
    errors, plan = question_bank.preview_import_csv(str(good), str(ws))
    assert errors == []

    # 模拟"预览之后别人先落了同一道题"
    question_bank.write_questions(
        [_question("Q001", "新题一", "技术面", "网络")], str(ws))

    # 领域层抛 ConflictError，协议层 apply() 统一转译成 ApprovalConflict
    with pytest.raises(approval.ApprovalConflict):
        _apply_plan(plan, ws)
