# -*- coding: utf-8 -*-
"""`jobws export --sync-to`：把新快照镜像进固定的 Obsidian 库目录。

钉住六条：首次同步=全量复制且 .obsidian/ 与白名单外文件零改动；幂等（同快照再计划
=0/0/0）；镜像语义+删除需 --yes 确认（CLI 拒绝执行、退出码 1）；守卫（不存在 /
是文件 / 在工作区内 → 拒绝，--dry-run 零写入）；边界（快照缺失条目跳过不删库里的、
--notes 关掉后材料目录不更新不删除且输出提示）；**复习进度保留**（只差
`<!--SR:-->` 注释的笔记不进计划、不被覆盖；正文真改了仍照常更新）。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import _cli_export  # noqa: E402
import _cli_export_sync  # noqa: E402
from jobws_core import tracker  # noqa: E402

TRACKING = "05_投递追踪"
SENTINEL = "SR-PLUGIN-MARKER"


def _names():
    """CLI 实际会传的白名单（八张表 + 两份说明文件；不带 --notes）。"""
    return [name for name, _c, _r, _f in _cli_export.TABLES] + ["README.md", "jobws.base"]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "ws" / TRACKING).mkdir(parents=True)
    return tmp_path / "ws"


@pytest.fixture()
def vault(tmp_path):
    """一个「已在用」的库：.obsidian（插件与设置）+ 一篇用户自己的笔记。"""
    target = tmp_path / "phone-vault"
    plugin_dir = target / ".obsidian" / "plugins" / "obsidian-spaced-repetition"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(SENTINEL, encoding="utf-8")
    (target / "我的笔记.md").write_text("# 我自己的笔记\n", encoding="utf-8")
    return target


def _seed_questions(ws, rows):
    fields = list(tracker.QUESTION_FIELDS)
    path = ws / TRACKING / "questions.csv"
    with io.open(str(path), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (title, answer) in enumerate(rows, start=1):
            row = dict((f, "") for f in fields)
            row.update({"题目id": "Q%03d" % index, "题目": title,
                        "答案要点": answer, "状态": "未看"})
            writer.writerow(row)
    return path


def _snapshot(ws, tmp_path, out_index):
    out = tmp_path / ("export-%d" % out_index)
    out.mkdir(exist_ok=True)
    root, _total = _cli_export.export_obsidian(str(ws), str(out))
    return root


def _tree(target):
    """库目录当前的全部相对路径 → 内容（.obsidian 除外，单独断言）。"""
    result = {}
    for dirpath, dirnames, filenames in os.walk(str(target)):
        dirnames[:] = [d for d in dirnames if d != ".obsidian"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(target)).replace(os.sep, "/")
            with io.open(full, "rb") as handle:
                result[rel] = handle.read()
    return result


def test_first_sync_copies_snapshot_and_preserves_vault_state(ws, vault, tmp_path):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)

    ops, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    assert any("同步计划：新增" in line for line in lines)
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    assert os.path.isfile(os.path.join(str(vault), "README.md"))
    assert os.path.isfile(os.path.join(str(vault), "jobws.base"))
    assert len(os.listdir(os.path.join(str(vault), "题库"))) == 2
    # `.obsidian/`（插件与设置）与用户自己的笔记一个字节都不动
    sentinel = vault / ".obsidian" / "plugins" / "obsidian-spaced-repetition" / "data.json"
    assert SENTINEL in sentinel.read_text(encoding="utf-8")
    assert "我自己的笔记" in (vault / "我的笔记.md").read_text(encoding="utf-8")


def test_second_sync_of_same_snapshot_is_a_noop(ws, vault, tmp_path):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)
    before = _tree(vault)

    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    assert "同步计划：新增 0 / 更新 0 / 删除 0" in lines
    assert ops2 == []
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops2)
    assert _tree(vault) == before


def test_cli_end_to_end_syncs_and_reports(ws, vault, tmp_path, capsys):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    out = tmp_path / "cli-out"
    out.mkdir()

    assert _cli_export.main(["--obsidian", str(out), "--sync-to", str(vault),
                             "--workspace", str(ws)]) == 0

    printed = capsys.readouterr().out
    assert "已导出" in printed and "已同步" in printed
    assert len(os.listdir(os.path.join(str(vault), "题库"))) == 2


def test_changed_question_is_updated_in_vault(ws, vault, tmp_path):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    _seed_questions(ws, [("题目 A", "改过的答案要点"), ("题目 B", "要点 B")])
    root2 = _snapshot(ws, tmp_path, 2)
    ops2, lines = _cli_export_sync.sync_plan(root2, str(vault), _names(), str(ws))

    updated = [line for line in lines if line.strip().startswith("更新")]
    assert any("题目 A" in line for line in updated), lines
    _cli_export_sync.sync_execute(root2, str(vault), _names(), ops2)
    note = io.open(os.path.join(str(vault), "题库", "题目 A.md"),
                   encoding="utf-8").read()
    assert "改过的答案要点" in note


def test_managed_dirs_are_mirrored_even_if_user_added_files(ws, vault, tmp_path):
    """白名单目录是「托管目录」：用户放进去的额外文件也在镜像范围内（设计如此）。"""
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)
    (vault / "题库" / "随手记.md").write_text("# 不属于题库的内容\n", encoding="utf-8")

    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert any(action == "删除" and "随手记" in rel for action, rel in ops2), ops2
    assert any(line.strip().startswith("删除") and "随手记" in line for line in lines), lines


def test_stale_note_requires_yes_then_is_removed(ws, vault, tmp_path, capsys):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    out1 = tmp_path / "out1"
    out1.mkdir()
    assert _cli_export.main(["--obsidian", str(out1), "--sync-to", str(vault),
                             "--workspace", str(ws)]) == 0

    _seed_questions(ws, [("题目 A", "要点 A")])  # 题库里少了一道题
    out2 = tmp_path / "out2"
    out2.mkdir()
    assert _cli_export.main(["--obsidian", str(out2), "--sync-to", str(vault),
                             "--workspace", str(ws)]) != 0
    assert "同步未执行" in capsys.readouterr().err
    assert os.path.exists(os.path.join(str(vault), "题库", "题目 B.md"))  # 未执行，文件还在

    out3 = tmp_path / "out3"
    out3.mkdir()
    assert _cli_export.main(["--obsidian", str(out3), "--sync-to", str(vault),
                             "--yes", "--workspace", str(ws)]) == 0
    assert not os.path.exists(os.path.join(str(vault), "题库", "题目 B.md"))


def test_dry_run_touches_nothing(ws, vault, tmp_path, capsys):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    out1 = tmp_path / "out1"
    out1.mkdir()
    assert _cli_export.main(["--obsidian", str(out1), "--sync-to", str(vault),
                             "--workspace", str(ws)]) == 0
    before = _tree(vault)
    _seed_questions(ws, [("题目 A", "dry-run 期间不该出现的新答案"), ("题目 B", "要点 B")])
    out2 = tmp_path / "out2"
    out2.mkdir()

    assert _cli_export.main(["--obsidian", str(out2), "--notes", "--sync-to", str(vault),
                             "--dry-run", "--workspace", str(ws)]) == 0

    printed = capsys.readouterr().out
    assert "同步计划" in printed and "--dry-run" in printed
    assert _tree(vault) == before, "dry-run 改了库目录"


def test_missing_entry_in_snapshot_is_skipped_not_deleted(ws, vault, tmp_path):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)
    os.remove(os.path.join(root, "jobws.base"))  # 快照里缺了这个条目

    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert not any(action == "删除" and rel == "jobws.base" for action, rel in ops2), ops2
    assert any("jobws.base" in line for line in lines) or ops2 == []
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops2)
    assert os.path.isfile(os.path.join(str(vault), "jobws.base"))


def test_target_is_file_is_refused(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    not_a_dir = tmp_path / "a-file"
    not_a_dir.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError) as err:
        _cli_export_sync.sync_plan(root, str(not_a_dir), _names(), str(ws))
    assert "不是目录" in str(err.value)


def test_target_inside_workspace_is_refused(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    inside = ws / "vault"
    inside.mkdir()
    with pytest.raises(RuntimeError) as err:
        _cli_export_sync.sync_plan(root, str(inside), _names(), str(ws))
    assert "工作区之外" in str(err.value)


def test_notes_projection_syncs_then_warns_without_notes(ws, vault, tmp_path, capsys):
    material = ws / "03_面试准备" / "技术面"
    material.mkdir(parents=True)
    (material / "材料.md").write_text("# 材料\n\n正文。\n", encoding="utf-8")
    out1 = tmp_path / "out1"
    out1.mkdir()
    assert _cli_export.main(["--obsidian", str(out1), "--notes", "--sync-to", str(vault),
                             "--workspace", str(ws)]) == 0
    assert os.path.isfile(os.path.join(str(vault), "03_面试准备", "技术面", "材料.md"))

    out2 = tmp_path / "out2"
    out2.mkdir()
    assert _cli_export.main(["--obsidian", str(out2), "--sync-to", str(vault),
                             "--workspace", str(ws)]) == 0
    assert "本次没开 --notes" in capsys.readouterr().out
    assert os.path.isfile(os.path.join(str(vault), "03_面试准备", "技术面", "材料.md"))


SR_COMMENT = "<!--SR:!2026-09-21,1,250-->"


def _append_sr_comment(vault, rel, inline=False):
    """模拟手机端插件写回进度：注释插在卡片行后面（默认）或同一行（同行模式）。"""
    path = os.path.join(str(vault), rel)
    text = io.open(path, encoding="utf-8").read().rstrip("\n")
    text = text + (" " + SR_COMMENT if inline else "\n" + SR_COMMENT)
    io.open(path, "w", encoding="utf-8", newline="").write(text + "\n")


def _read(vault, rel):
    return io.open(os.path.join(str(vault), rel), encoding="utf-8").read()


def test_review_progress_comment_is_not_wiped(ws, vault, tmp_path):
    """只差 SR 注释的笔记不进计划、不被覆盖——复习进度就写在注释里。"""
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    _append_sr_comment(vault, "题库/题目 A.md")
    before = _read(vault, "题库/题目 A.md")

    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    assert not any(rel.endswith("题目 A.md") for _action, rel in ops2), ops2
    assert any("保留复习进度：1" in line for line in lines), lines

    _cli_export_sync.sync_execute(root, str(vault), _names(), ops2)
    assert _read(vault, "题库/题目 A.md") == before
    assert SR_COMMENT in _read(vault, "题库/题目 A.md")


def test_inline_review_progress_comment_is_not_wiped(ws, vault, tmp_path):
    """同行模式也认：注释贴在卡片行尾（不独占一行）时同样不覆盖。"""
    _seed_questions(ws, [("题目 A", "要点 A")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    _append_sr_comment(vault, "题库/题目 A.md", inline=True)
    before = _read(vault, "题库/题目 A.md")
    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert ops2 == [], ops2
    assert any("保留复习进度" in line for line in lines), lines
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops2)
    assert _read(vault, "题库/题目 A.md") == before


def test_real_content_change_still_updates_despite_progress(ws, vault, tmp_path):
    """正文真改了要照常更新（代价：这一篇里的卡进度归零——可接受，文档写明）。"""
    _seed_questions(ws, [("题目 A", "要点 A")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)
    _append_sr_comment(vault, "题库/题目 A.md")

    _seed_questions(ws, [("题目 A", "改过的答案要点")])
    root2 = _snapshot(ws, tmp_path, 2)
    ops2, lines = _cli_export_sync.sync_plan(root2, str(vault), _names(), str(ws))

    assert any(rel.endswith("题目 A.md") for _action, rel in ops2), ops2
    _cli_export_sync.sync_execute(root2, str(vault), _names(), ops2)
    note = _read(vault, "题库/题目 A.md")
    assert "改过的答案要点" in note


def test_whitespace_and_extra_comments_are_not_overwritten(ws, vault, tmp_path):
    """空白差异（空行 / 行尾空格）与多条排程注释同样保守不覆盖——规则要能钉住。"""
    _seed_questions(ws, [("题目 A", "要点 A")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    rel = "题库/题目 A.md"
    path = os.path.join(str(vault), rel)
    text = io.open(path, encoding="utf-8").read().rstrip("\n")
    text = text + "  \n\n" + SR_COMMENT + "\n<!--SR:!2026-09-24,4,270-->\n"
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    before = _read(vault, rel)

    ops2, lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert not any(rel2.endswith("题目 A.md") for _action, rel2 in ops2), ops2
    assert any("保留复习进度" in line for line in lines), lines
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops2)
    assert _read(vault, rel) == before


def test_non_sr_comment_change_still_updates(ws, vault, tmp_path):
    """正则只认 `<!--SR:`——普通 HTML 注释的改动是正文差异，必须照常更新（防放宽）。"""
    _seed_questions(ws, [("题目 A", "要点 A")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    rel = "题库/题目 A.md"
    path = os.path.join(str(vault), rel)
    text = io.open(path, encoding="utf-8").read().rstrip("\n")
    io.open(path, "w", encoding="utf-8", newline="").write(
        text + "\n<!-- 我自己的批注 -->\n")

    ops2, _lines2 = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert any(rel2.endswith("题目 A.md") for _action, rel2 in ops2), ops2


def test_unreadable_dst_falls_back_to_bytes(ws, vault, tmp_path):
    """库端那份不是合法 UTF-8 → 回退按字节比（保守方向 = 照旧覆盖，不静默跳过）。"""
    _seed_questions(ws, [("题目 A", "要点 A")])
    root = _snapshot(ws, tmp_path, 1)
    ops, _lines = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))
    _cli_export_sync.sync_execute(root, str(vault), _names(), ops)

    rel = "题库/题目 A.md"
    with io.open(os.path.join(str(vault), rel), "wb") as handle:
        handle.write(b"\xff\xfe not utf8 \x00")

    ops2, _lines2 = _cli_export_sync.sync_plan(root, str(vault), _names(), str(ws))

    assert any(rel2.endswith("题目 A.md") for _action, rel2 in ops2), ops2
