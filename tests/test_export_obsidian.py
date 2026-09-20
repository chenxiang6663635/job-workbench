# -*- coding: utf-8 -*-
"""`jobws export --obsidian`：八张 CSV → 每行一笔记 + frontmatter + Bases 视图。

钉住四条：
1. **形态**：每张表一个目录、每行一篇笔记，frontmatter 带上该表全部字段；
2. **写不坏**：值里的引号 / 反斜杠 / 换行在 YAML 里被转义（frontmatter 读坏了
   整篇笔记就废了）；
3. **不覆盖**：导出目录带时间戳，同名已存在就报错而不是覆盖历史导出；
4. **只读工作区**：导出前后 CSV 一个字节都不变（导出是快照，不是同步）；
5. **材料投影（`--notes`）**：目录层级 + frontmatter 记来源、隐藏文件与 `训练卡`
   跳过、超限整份跳过（不截断）、跳过清单进产物 README、目标在工作区内直接拒绝。
"""

import csv
import datetime
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import _cli_export  # noqa: E402
import _cli_export_notes  # noqa: E402
from jobws_core import tracker  # noqa: E402

TRACKING = "05_投递追踪"


@pytest.fixture()
def ws(tmp_path):
    """一个只有目录结构的空工作区（表由用例自己写）。"""
    (tmp_path / "ws" / TRACKING).mkdir(parents=True)
    return tmp_path / "ws"


def _write_table(ws, filename, fields, rows):
    path = ws / TRACKING / filename
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _seed_applications(ws, rows):
    return _write_table(ws, "tracker.csv", list(tracker.FIELDS), rows)


def _seed_questions(ws, rows):
    return _write_table(ws, "questions.csv", list(tracker.QUESTION_FIELDS), rows)


def _row():
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": "T001", "公司": "示例公司", "岗位": "后端",
                "当前阶段": "已投", "方向": "other", "备注": "无"})
    return row


def _question():
    row = dict((field, "") for field in tracker.QUESTION_FIELDS)
    row.update({"题目id": "Q001", "题目": "缓存雪崩是什么",
                "领域": "技术面", "科目": "Redis", "状态": "未看",
                "答案要点": "大量 key 同时过期"})
    return row


# --- 形态 -------------------------------------------------------------------


def test_one_note_per_row_and_index_files(ws, tmp_path):
    _seed_applications(ws, [_row(), _row()])
    _seed_questions(ws, [_question()])
    out = tmp_path / "out"
    out.mkdir()

    root, total = _cli_export.export_obsidian(str(ws), str(out))

    assert total == 3
    assert os.path.basename(root).startswith("obsidian-export-")
    assert len(os.listdir(os.path.join(root, "投递记录"))) == 2
    assert len(os.listdir(os.path.join(root, "题库"))) == 1
    assert os.path.isfile(os.path.join(root, "README.md"))
    assert os.path.isfile(os.path.join(root, "jobws.base"))
    # 空表也建目录：让人一眼看到"这张表是空的"，而不是以为导出漏了
    assert os.path.isdir(os.path.join(root, "面试"))
    assert os.listdir(os.path.join(root, "面试")) == []


def test_frontmatter_carries_every_field(ws, tmp_path):
    _seed_applications(ws, [_row()])
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out))
    note = io.open(
        os.path.join(root, "投递记录", os.listdir(os.path.join(root, "投递记录"))[0]),
        encoding="utf-8",
    ).read()

    assert note.startswith("---\n")
    for field in tracker.FIELDS:
        assert "%s: " % field in note, "frontmatter 少了 %s" % field
    assert "公司: \"示例公司\"" in note


def test_question_note_is_a_spaced_repetition_card(ws, tmp_path):
    _seed_questions(ws, [_question()])
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out))
    note = io.open(
        os.path.join(root, "题库", os.listdir(os.path.join(root, "题库"))[0]),
        encoding="utf-8",
    ).read()

    assert "tags: [flashcard, jobws/题库]" in note
    assert "缓存雪崩是什么:: 大量 key 同时过期" in note


# --- 写不坏 -----------------------------------------------------------------


def test_quotes_newlines_and_illegal_name_chars(ws, tmp_path):
    row = _row()
    row["备注"] = '他说："这里换行\n了"'
    row["公司"] = "A/B: 研发"
    _seed_applications(ws, [row])
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out))
    name = os.listdir(os.path.join(root, "投递记录"))[0]

    # 文件名：Windows 非法字符换成 -（`/` 与 `:` 都在其列）
    assert "/" not in name and ":" not in name
    note = io.open(os.path.join(root, "投递记录", name), encoding="utf-8").read()
    # YAML 双引号内：引号转义、换行变成字面 \n
    assert '\\"' in note and "\\n" in note


def test_duplicate_titles_get_a_suffix_instead_of_overwriting(ws, tmp_path):
    _seed_applications(ws, [_row(), _row()])
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out))
    names = sorted(os.listdir(os.path.join(root, "投递记录")))

    assert len(names) == 2
    # 不依赖排序：`-2` 与 `.md` 的字典序取决于字符编码
    assert any(name.endswith("-2.md") for name in names)


# --- 不覆盖 / 只读 ----------------------------------------------------------


def test_existing_export_dir_is_refused(ws, tmp_path, monkeypatch):
    """同名导出目录已存在 → 报错而不是覆盖（静默覆盖历史导出 = 数据丢失）。"""
    _seed_applications(ws, [_row()])
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(_cli_export, "now_stamp",
                        lambda: datetime.datetime(2026, 9, 19, 15, 30, 0).strftime("%Y%m%d-%H%M%S"))

    _cli_export.export_obsidian(str(ws), str(out))
    with pytest.raises(RuntimeError) as exc:
        _cli_export.export_obsidian(str(ws), str(out))
    assert "已存在" in str(exc.value)


def test_workspace_is_left_untouched(ws, tmp_path):
    """导出是快照：一张表都不该被改。"""
    path = _seed_applications(ws, [_row()])
    before = path.read_bytes()
    out = tmp_path / "out"
    out.mkdir()

    _cli_export.export_obsidian(str(ws), str(out))

    assert path.read_bytes() == before


# --- 命令层 -----------------------------------------------------------------


def test_missing_obsidian_arg_is_usage_error(capsys):
    assert _cli_export.main([]) == 2
    assert "--obsidian" in capsys.readouterr().err


def test_missing_target_dir_exits_one(ws, capsys):
    assert _cli_export.main(["--obsidian", str(ws / "nope"),
                             "--workspace", str(ws)]) == 1
    assert "不存在" in capsys.readouterr().err


def test_export_prints_where_it_wrote(ws, tmp_path, capsys):
    _seed_applications(ws, [_row()])
    out = tmp_path / "out"
    out.mkdir()

    assert _cli_export.main(["--obsidian", str(out), "--workspace", str(ws)]) == 0
    printed = capsys.readouterr().out
    assert "已导出 1 篇笔记" in printed
    assert "obsidian-export-" in printed


# --- 材料投影（`--notes`，2026-09-20）----------------------------------------


def _write_note(ws, rel, text):
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_notes_are_projected_with_structure_and_frontmatter(ws, tmp_path):
    """`--notes`：03/04/00 的 Markdown 原样投影——保留层级 + frontmatter 记来源。"""
    _write_note(ws, "03_面试准备/技术面/a.md", "# 题 A\n\n正文 A。\n")
    _write_note(ws, "04_知识库/液冷/b.md", "# 题 B\n\n正文 B。\n")
    out = tmp_path / "out"
    out.mkdir()

    root, total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    note = io.open(os.path.join(root, "03_面试准备", "技术面", "a.md"),
                   encoding="utf-8").read()
    assert "tags: [jobws/笔记]" in note
    assert '来源目录: "03_面试准备"' in note
    assert '相对路径: "技术面/a.md"' in note
    assert '标题: "题 A"' in note
    assert note.rstrip().endswith("正文 A。")
    assert os.path.isfile(os.path.join(root, "04_知识库", "液冷", "b.md"))
    assert total == 2  # 表都是空的，只有两篇材料


def test_training_cards_are_not_projected_twice(ws, tmp_path):
    """训练卡是题库的卡源：已在「题库/」下以 flashcard 出现，不再投影一遍。"""
    _write_note(ws, "03_面试准备/训练卡/技术面/x.md", "# 卡 X\n\n要点。\n")
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    assert os.path.isdir(os.path.join(root, "03_面试准备"))
    assert not os.path.exists(os.path.join(root, "03_面试准备", "训练卡"))


def test_big_note_is_copied_in_full_not_truncated(ws, tmp_path):
    """256 KB 截断是只读端点的语义；带进导出会把长速记截成半篇。"""
    body = "x" * (300 * 1024)
    _write_note(ws, "00_事实库/big.md", "# 大文件\n\n%s\n\nTAIL-MARKER\n" % body)
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)
    note = io.open(os.path.join(root, "00_事实库", "big.md"), encoding="utf-8").read()

    assert "TAIL-MARKER" in note, "超过 256 KB 的笔记被截断了"
    assert note.count("x") == 300 * 1024


def test_notes_are_off_by_default(ws, tmp_path):
    """新增能力用新增开关承载：不带 --notes 时既有导出行为不变。"""
    _write_note(ws, "03_面试准备/技术面/a.md", "# 题 A\n\n正文。\n")
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out))

    assert not os.path.exists(os.path.join(root, "03_面试准备"))


def test_export_target_inside_workspace_is_refused(ws, tmp_path, capsys):
    """导出目录必须在工作区之外：否则污染工作区，并被材料投影重复收录（嵌套复制）。"""
    _write_note(ws, "04_知识库/a.md", "# A\n\n正文。\n")
    inside = ws / "04_知识库"
    before = sorted(p.name for p in inside.iterdir())

    with pytest.raises(RuntimeError) as err:
        _cli_export.export_obsidian(str(ws), str(inside), include_notes=True)
    assert "工作区之外" in str(err.value)
    assert sorted(p.name for p in inside.iterdir()) == before  # 目录都没建

    assert _cli_export.main(["--obsidian", str(inside), "--notes",
                             "--workspace", str(ws)]) == 1
    assert "工作区之外" in capsys.readouterr().err


def test_hidden_files_are_not_projected(ws, tmp_path):
    """隐藏文件跳过（与只读端点同口径）：草稿、原子写临时名、AppleDouble 都不算材料。"""
    _write_note(ws, "03_面试准备/可见.md", "# 可见\n\n正文。\n")
    _write_note(ws, "03_面试准备/.draft.md", "# 草稿\n\n不该出现。\n")
    _write_note(ws, "03_面试准备/.jobws_tmp_ab12.md", "# 临时\n\n不该出现。\n")
    _write_note(ws, "03_面试准备/._可见.md", "# AppleDouble\n\n不该出现。\n")
    out = tmp_path / "out"
    out.mkdir()

    root, _total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    assert sorted(os.listdir(os.path.join(root, "03_面试准备"))) == ["可见.md"]


def test_unreadable_note_is_skipped_and_listed_in_readme(ws, tmp_path, capsys):
    """读不动的材料：跳过 + 产物 README 点名（别让人以为导出是完整的）。"""
    _write_note(ws, "04_知识库/好.md", "# 好\n\n正文。\n")
    (ws / "04_知识库" / "坏.md").write_bytes(b"# \xbb\xb5\n\n\xff\xfe")
    out = tmp_path / "out"
    out.mkdir()

    root, total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    readme = io.open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert total == 1
    assert "没导出的材料" in readme
    assert "坏.md" in readme
    assert "没导出，已跳过" in capsys.readouterr().err


def test_oversize_note_is_skipped_not_truncated(ws, tmp_path, capsys):
    """超限整份跳过：截断会产出一篇看着完整、实则缺半截的笔记。"""
    big = ws / "00_事实库" / "huge.md"
    big.parent.mkdir(parents=True)
    big.write_text("# 巨\n\n" + "x" * (_cli_export_notes.NOTE_MAX_BYTES + 1),
                   encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    root, total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    assert total == 0
    assert not os.path.exists(os.path.join(root, "00_事实库", "huge.md"))
    readme = io.open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert "huge.md" in readme and "上限" in readme
    assert "没导出，已跳过" in capsys.readouterr().err


def test_name_collision_gets_suffix_not_overwrite():
    """重名加序号：清洗非法字符后撞名时加 `-2`，而不是互相覆盖。"""
    used = {}
    first = _cli_export_notes._note_target_path("/root", "a:b.md", used)
    second = _cli_export_notes._note_target_path("/root", "a?b.md", used)

    assert first.endswith("a-b.md")
    assert second.endswith("a-b-2.md")


def test_main_notes_flag_projects_materials(ws, tmp_path, capsys):
    """`--notes` 的接线（argparse 参数名写错时这条会红）。"""
    _write_note(ws, "03_面试准备/甲.md", "# 甲\n\n正文甲。\n")
    out = tmp_path / "out"
    out.mkdir()

    assert _cli_export.main(["--obsidian", str(out), "--notes",
                             "--workspace", str(ws)]) == 0

    assert "已导出 1 篇笔记" in capsys.readouterr().out
    root = [name for name in os.listdir(str(out))
            if name.startswith("obsidian-export-")][0]
    assert os.path.isfile(os.path.join(str(out), root, "03_面试准备", "甲.md"))
    readme = io.open(os.path.join(str(out), root, "README.md"), encoding="utf-8").read()
    assert "材料笔记" in readme


def test_empty_material_dir_is_zero_not_missing(ws, tmp_path):
    """空材料目录：建目录、报 0 篇——"没有这个目录"与"目录是空的"是两件事。"""
    (ws / "04_知识库").mkdir(parents=True)
    out = tmp_path / "out"
    out.mkdir()

    root, total = _cli_export.export_obsidian(str(ws), str(out), include_notes=True)

    assert total == 0
    assert os.path.isdir(os.path.join(root, "04_知识库"))
    readme = io.open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert "`04_知识库/`：0 篇" in readme
