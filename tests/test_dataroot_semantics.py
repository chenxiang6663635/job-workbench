# -*- coding: utf-8 -*-
"""迁移的**工作区语义校验**（B1 的 verify 相里「不只是字节」的那一半）。

spec 决策 5 点名的四项：`tracker.csv` 主键集合与行数、`config/profile.md`、
`config/directions/*.md` 数量、`config/imap.json` / `provider.json` 的**凭据引用**
（凭据本体在系统安全存储，只校验引用可解析）。

两条刻意的边界（都在 `dataroot_semantics` 的 docstring 里写明）：

- 语义项是**源 → 目标**的比对：清单 + 哈希已经保证字节相等，语义比对的职责是
  「这份拷贝还是一个能用的工作区吗」——主键集合丢了、档案没了、方向文件少了、
  凭据引用没搬过来，都是字节相等也看不出的语义退化；
- **凭据引用取不到 ≠ 迁移失败**：引用是 uuid（与路径无关），「引用在手却取不到」
  是迁移**之前**就存在的工作区健康状态（#203 的口径是让界面提示「重新保存」）。
  机器上有系统存储时才判得动（明文形态下没有存储可查）——因此它进 `warnings`
  而不是 `problems`，阻断迁移只会把用户锁在原地。
"""

import io
import json
import os

import pytest

from jobws_core import dataroot_semantics as semantics

WS = "personal"


def _write(root, rel, text):
    path = os.path.join(str(root), rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _make_workspace(root, name=WS, tracker_rows=None, directions=1):
    ws = os.path.join(str(root), name)
    _write(ws, "config/profile.md", "# 档案\n")
    for i in range(directions):
        _write(ws, "config/directions/d%d.md" % i, "方向 %d\n" % i)
    if tracker_rows is not None:
        _write(ws, "05_投递追踪/tracker.csv", "".join(tracker_rows))
    return ws


class _Store:
    """假系统存储：`have` 里有的引用才解析得出来（与 `SecretStore` 同形状）。"""

    kind = "credman"

    def __init__(self, have=()):
        self.have = set(have)

    def get(self, ref):
        return "secret" if ref in self.have else None


# --- 读取原件 ------------------------------------------------------------------

def test_read_tracker_reports_row_count_and_ids(tmp_path):
    ws = _make_workspace(tmp_path, tracker_rows=[
        "id,公司,岗位\n", "1,示例公司A,后端\n", "2,示例公司B,算法\n"])
    assert semantics.read_tracker(ws) == {"rows": 2, "ids": ["1", "2"]}


def test_read_tracker_tolerates_missing_or_broken_file(tmp_path):
    """追踪表不在（还没建）或没有 id 列：如实退化，不抛——语义项不该把迁移炸掉。"""
    ws = _make_workspace(tmp_path, tracker_rows=None)
    assert semantics.read_tracker(ws) is None

    _write(ws, "05_投递追踪/tracker.csv", "公司,岗位\n示例公司A,后端\n")
    assert semantics.read_tracker(ws) == {"rows": 1, "ids": []}


def test_snapshot_collects_profile_directions_and_credential_refs(tmp_path):
    ws = _make_workspace(tmp_path, tracker_rows=["id\n", "1\n"], directions=3)
    _write(ws, "config/imap.json",
           json.dumps({"host": "imap.example.com", "auth_ref": "job-workbench/x/imap"}))
    _write(ws, "config/provider.json",
           json.dumps({"api_key_ref": "job-workbench/y/provider"}))

    snap = semantics.snapshot(ws)
    assert snap["profile"] is True
    assert snap["directions"] == 3
    assert snap["tracker"] == {"rows": 1, "ids": ["1"]}
    assert snap["credentials"] == [
        {"file": "config/imap.json", "key": "auth_ref",
         "ref": "job-workbench/x/imap"},
        {"file": "config/provider.json", "key": "api_key_ref",
         "ref": "job-workbench/y/provider"},
    ]


def test_snapshot_ignores_plaintext_secret_fields(tmp_path):
    """只取**引用**：快照会进 journal（落盘到 state/），明文密文绝不能进这里。"""
    ws = _make_workspace(tmp_path, tracker_rows=None)
    _write(ws, "config/imap.json",
           json.dumps({"password": "明文授权码不该出现在快照里"}))
    assert semantics.snapshot(ws)["credentials"] == []


# --- 源 → 目标比对 --------------------------------------------------------------

def test_compare_passes_for_a_faithful_copy(tmp_path):
    src = _make_workspace(tmp_path / "src", tracker_rows=["id\n", "1\n"], directions=2)
    dst = _make_workspace(tmp_path / "dst", tracker_rows=["id\n", "1\n"], directions=2)
    _write(dst, "config/imap.json", "{}")   # 目标额外的文件不算差异（比对只看源有的）

    result = semantics.compare(semantics.snapshot(src), semantics.snapshot(dst))
    assert result["problems"] == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda dst: os.remove(os.path.join(dst, "config", "profile.md")), "档案"),
    (lambda dst: _write(dst, "05_投递追踪/tracker.csv", "id\n1\n2\n"), "追踪表"),
    (lambda dst: os.remove(os.path.join(dst, "config", "directions", "d1.md")), "方向"),
])
def test_compare_flags_semantic_regressions(tmp_path, mutate, expect):
    src = _make_workspace(tmp_path / "src", tracker_rows=["id\n", "1\n"], directions=2)
    dst = _make_workspace(tmp_path / "dst", tracker_rows=["id\n", "1\n"], directions=2)
    mutate(dst)

    result = semantics.compare(semantics.snapshot(src), semantics.snapshot(dst))
    assert result["problems"], "语义退化必须被点出来"
    assert any(expect in item for item in result["problems"])


def test_compare_flags_lost_credential_reference(tmp_path):
    """凭据引用没搬过来 = 界面会从「重新保存」退化成「还没配置」——算硬问题。"""
    src = _make_workspace(tmp_path / "src", tracker_rows=None)
    _write(src, "config/imap.json", json.dumps({"auth_ref": "job-workbench/x/imap"}))
    dst = _make_workspace(tmp_path / "dst", tracker_rows=None)

    result = semantics.compare(semantics.snapshot(src), semantics.snapshot(dst))
    assert any("凭据引用" in item for item in result["problems"])


# --- 凭据引用能不能解析（warning，不阻断） ---------------------------------------

def test_unresolved_reference_is_a_warning_not_a_failure(tmp_path):
    ws = _make_workspace(tmp_path, tracker_rows=None)
    _write(ws, "config/imap.json", json.dumps({"auth_ref": "job-workbench/x/imap"}))

    warnings = semantics.credential_warnings(ws, store=_Store(have=[]))
    assert len(warnings) == 1 and "取不到" in warnings[0]
    # 同一个工作区、存储里有这条引用时：没有告警
    assert semantics.credential_warnings(
        ws, store=_Store(have=["job-workbench/x/imap"])) == []


def test_plaintext_form_reports_nothing(tmp_path):
    """明文形态没有系统存储可查（`get` 恒 None）——那不算「引用取不到」，不报噪音。"""
    ws = _make_workspace(tmp_path, tracker_rows=None)
    _write(ws, "config/imap.json", json.dumps({"auth_ref": "job-workbench/x/imap"}))

    class _Plain:
        kind = "plaintext"

        def get(self, ref):
            return None

    assert semantics.credential_warnings(ws, store=_Plain()) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
