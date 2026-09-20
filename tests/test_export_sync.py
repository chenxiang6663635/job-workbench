# -*- coding: utf-8 -*-
"""`jobws export --sync-to`：把新快照镜像进固定的 Obsidian 库目录。

钉住四条：
1. **首次同步 = 全量复制**，且库里的 `.obsidian/`（插件与复习进度）与白名单外的
   用户文件**一个字节都不动**；
2. **幂等**：同一份快照再同步一次 = 0 新增 / 0 更新 / 0 删除；
3. **镜像语义**：源里删掉的文件，库里对应文件也会删（删除清单打印）——白名单
   目录是「托管目录」，用户往里放的文件也会被清掉（这是设计，不是事故）；
4. **守卫**：目标不存在 / 在工作区内 → 拒绝；`--dry-run` 一个字节都不写。
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


def _names():
    """CLI 实际会传的白名单（八张表 + 两份说明文件；本文件不开 --notes）。"""
    return [name for name, _c, _r, _f in _cli_export.TABLES] + ["README.md", "jobws.base"]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "ws" / TRACKING).mkdir(parents=True)
    return tmp_path / "ws"


@pytest.fixture()
def vault(tmp_path):
    """一个「已在用」的库：.obsidian（插件 + 进度）+ 一篇用户自己的笔记。"""
    target = tmp_path / "phone-vault"
    plugin_dir = target / ".obsidian" / "plugins" / "obsidian-spaced-repetition"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        '{"schedule": {"题库/a.md": [1, 2]}}', encoding="utf-8")
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
    lines = _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))

    assert any("同步计划：新增" in line for line in lines)
    assert os.path.isfile(os.path.join(str(vault), "README.md"))
    assert os.path.isfile(os.path.join(str(vault), "jobws.base"))
    assert len(os.listdir(os.path.join(str(vault), "题库"))) == 2
    # `.obsidian/`（插件与复习进度）与用户自己的笔记一个字节都不动
    sentinel = vault / ".obsidian" / "plugins" / "obsidian-spaced-repetition" / "data.json"
    assert "schedule" in sentinel.read_text(encoding="utf-8")
    assert "我自己的笔记" in (vault / "我的笔记.md").read_text(encoding="utf-8")


def test_second_sync_of_same_snapshot_is_a_noop(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))
    before = _tree(vault)

    lines = _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))

    assert "同步计划：新增 0 / 更新 0 / 删除 0" in lines
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
    _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))

    _seed_questions(ws, [("题目 A", "改过的答案要点"), ("题目 B", "要点 B")])
    root2 = _snapshot(ws, tmp_path, 2)
    lines = _cli_export_sync.sync_to_vault(root2, str(vault), _names(), str(ws))

    updated = [line for line in lines if line.strip().startswith("更新")]
    assert any("题目 A" in line for line in updated), lines
    note = io.open(os.path.join(str(vault), "题库", "题目 A.md"),
                   encoding="utf-8").read()
    assert "改过的答案要点" in note


def test_stale_note_is_removed_from_vault(ws, vault, tmp_path):
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))
    os.remove(os.path.join(root, "题库", "题目 B.md"))  # 模拟"题库里少了一道题"

    lines = _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))

    assert any(line.strip().startswith("删除") and "题目 B" in line for line in lines), lines
    assert not os.path.exists(os.path.join(str(vault), "题库", "题目 B.md"))
    assert os.path.exists(os.path.join(str(vault), "题库", "题目 A.md"))


def test_managed_dirs_are_mirrored_even_if_user_added_files(ws, vault, tmp_path):
    """白名单目录是「托管目录」：用户放进去的额外文件也在镜像范围内（设计如此）。"""
    _seed_questions(ws, [("题目 A", "要点 A"), ("题目 B", "要点 B")])
    root = _snapshot(ws, tmp_path, 1)
    _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))
    (vault / "题库" / "随手记.md").write_text("# 不属于题库的内容\n", encoding="utf-8")

    lines = _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))

    assert any(line.strip().startswith("删除") and "随手记" in line for line in lines), lines
    assert not os.path.exists(os.path.join(str(vault), "题库", "随手记.md"))


def test_dry_run_touches_nothing(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    _cli_export_sync.sync_to_vault(root, str(vault), _names(), str(ws))
    before = _tree(vault)
    _seed_questions(ws, [("题目 A", "dry-run 期间不该出现的新答案"), ("题目 B", "要点 B")])
    root2 = _snapshot(ws, tmp_path, 2)

    lines = _cli_export_sync.sync_to_vault(root2, str(vault), _names(), str(ws),
                                           dry_run=True)

    assert any("同步计划" in line for line in lines)
    assert any("--dry-run" in line for line in lines)
    assert _tree(vault) == before, "dry-run 改了库目录"


def test_missing_target_is_refused(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    with pytest.raises(RuntimeError) as err:
        _cli_export_sync.sync_to_vault(root, str(tmp_path / "nope"), _names(), str(ws))
    assert "不存在" in str(err.value)


def test_target_inside_workspace_is_refused(ws, vault, tmp_path):
    root = _snapshot(ws, tmp_path, 1)
    inside = ws / "vault"
    inside.mkdir()
    with pytest.raises(RuntimeError) as err:
        _cli_export_sync.sync_to_vault(root, str(inside), _names(), str(ws))
    assert "工作区之外" in str(err.value)
