# -*- coding: utf-8 -*-
"""共享写入原语（tools/workspace_io.py）的回归测试。

批 8 目标：CLI / MCP / 后端（桌面端）四端共用同一套"原子写 + 指纹 + 锁名"，
本文件钉住这套原语的对外承诺：
- 原子写三类（text / bytes / csv）真字节落盘、无临时残留；
- Windows 下 os.replace 被占用时按重试次数退避重试，超限才抛；
- 目录指纹只看 size+mtime（不做全内容哈希），文件增删改都会使它变化；
- 锁名工厂与四端既有路径逐字一致（tracker / jobs / resume / imap / provider）。
"""
from __future__ import annotations

import csv
import io
import os
import sys

import pytest

# 自插 sys.path：不能指望"别的测试模块先被导入时顺手插好"——单独跑本文件也要能过
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

from jobws_core import workspace_io  # noqa: E402


# --- 原子写 ---------------------------------------------------------------


def test_atomic_write_text_roundtrip(tmp_path):
    target = tmp_path / "sub" / "note.md"
    workspace_io.atomic_write_text(str(target), "第一行\n第二行\n")
    with io.open(str(target), "r", encoding="utf-8", newline="") as handle:
        assert handle.read() == "第一行\n第二行\n"
    # 目录被自动创建、无临时残留
    assert os.listdir(str(target.parent)) == ["note.md"]


def test_atomic_write_bytes_roundtrip(tmp_path):
    target = tmp_path / "out" / "blob.bin"
    payload = bytes(range(256))
    workspace_io.atomic_write_bytes(str(target), payload)
    with open(str(target), "rb") as handle:
        assert handle.read() == payload
    assert os.listdir(str(target.parent)) == ["blob.bin"]


def test_atomic_write_csv_bom_and_restval(tmp_path):
    target = tmp_path / "tracker.csv"
    rows = [{"id": "A001", "公司": "云帆", "备注": None}]
    workspace_io.atomic_write_csv(str(target), rows, ["id", "公司", "备注"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    assert text.startswith("id,公司,备注")
    # None 落盘为空串，不是 "None"；BOM 让 Excel 直接可读
    with open(str(target), "rb") as handle:
        assert handle.read(3) == b"\xef\xbb\xbf"
    assert "None" not in text


@pytest.mark.parametrize("danger", ["=1+1", "+HYPERLINK(\"http://x\")", "-2+3",
                                    "@SUM(A1:A9)"])
def test_atomic_write_csv_neutralizes_formula_prefixes(tmp_path, danger):
    """`= + - @` 开头的单元格会被 Excel / WPS 当公式算——导出文件被人打开即中招。

    追踪表里的「备注」「公司」等字段是用户手填的，也可能来自粘贴进来的邮件原文；
    把它们原样写进 CSV，等于给表格软件递一段可执行的公式。缓解办法是在危险前缀
    前加一个单引号——表格软件会按文本显示它，代价只有一个字符。
    """
    target = tmp_path / "tracker.csv"
    workspace_io.atomic_write_csv(str(target), [{"备注": danger}], ["备注"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        cell = list(csv.reader(handle))[1][0]
    assert cell.startswith("'"), "危险前缀必须以单引号中和：%r" % cell
    assert danger in cell


def test_csv_cells_round_trip_restores_the_quote(tmp_path):
    """读回时要还原写侧为主和公式而加的单引号（批末独立审查抓出的漏项）。

    只做写侧中和、读侧不还原，用户数据里就会永久多一个引号：备注 `- 二面待定`
    落盘成 `'- 二面待定`，界面、CLI、导出、下一次写回都带着它——"写进去什么、
    读出来什么"是这份数据最基本的承诺。
    """
    from jobws_core.csv_cells import csv_cell, csv_read_cell

    for danger in ("=1+1", "+HYPERLINK(\"http://x\")", "- 二面待定", "@SUM(A1)"):
        assert csv_read_cell(csv_cell(danger)) == danger


def test_csv_read_cell_keeps_a_real_apostrophe(tmp_path):
    """否定验证：用户真正想留的引号不能被吃掉（只有紧跟公式前缀才还原）。"""
    from jobws_core.csv_cells import csv_read_cell

    assert csv_read_cell("'这是引用'") == "'这是引用'"
    assert csv_read_cell("'") == "'"


def test_csv_cells_round_trip_keeps_a_leading_apostrophe(tmp_path):
    """用户真想留的「引号 + 公式前缀」也要能原样往返（二轮审计）。

    只做一层转义时这里会失守：写 `'- 待定` 不加层，读侧就把它当转义还原成 `- 待定`
    ——用户看到自己写的内容被改掉。写侧对"已是转义形态"的文本再补一层，写读即可逆。
    """
    from jobws_core.csv_cells import csv_cell, csv_read_cell

    for raw in ("'- 待定", "'=SUM(A1)", "'+86 13800000000"):
        assert csv_read_cell(csv_cell(raw)) == raw, raw
    # 幂等：往返后的值再走一轮，结果不变（不会每存一次多一个引号）
    for raw in ("'- 待定", "=1+1", "'引用'"):
        once = csv_read_cell(csv_cell(raw))
        assert csv_read_cell(csv_cell(once)) == once, raw


def test_tracker_round_trip_keeps_remark_unchanged(tmp_path):
    """落盘再读回，备注逐字符相同（追踪表是最容易踩这个坑的那张表）。"""
    from jobws_core import tracker

    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "05_投递追踪"))
    row = {field: "" for field in tracker.FIELDS}
    row.update({"id": "A001", "公司": "示例公司", "岗位": "示例岗位",
                "备注": "- 二面待定；详情见邮件"})
    tracker.write_rows([row], ws)

    assert tracker.read_rows(ws)[0]["备注"] == "- 二面待定；详情见邮件"


def test_atomic_write_csv_leaves_plain_values_untouched(tmp_path):
    """否定验证：中和不能变成对所有单元格动刀——普通中文一个字都不许改。"""
    target = tmp_path / "tracker.csv"
    rows = [{"公司": "云帆科技", "备注": "2026-09-25 内推"}]
    workspace_io.atomic_write_csv(str(target), rows, ["公司", "备注"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        row = list(csv.reader(handle))[1]
    assert row == ["云帆科技", "2026-09-25 内推"]


def test_atomic_write_replaces_old_content(tmp_path):
    target = tmp_path / "data.csv"
    workspace_io.atomic_write_csv(str(target), [{"a": "1"}], ["a"])
    workspace_io.atomic_write_csv(str(target), [{"a": "2"}], ["a"])
    with io.open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "2"}]


# --- Windows 共享冲突重试 --------------------------------------------------


def test_replace_retries_on_permission_error(tmp_path, monkeypatch):
    """os.replace 第一次抛 PermissionError（被 Excel 之类占用），重试后应成功。"""
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "being used by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(workspace_io.os, "replace", flaky)
    target = tmp_path / "busy.csv"
    workspace_io.atomic_write_text(str(target), "ok", sleep=lambda _s: None)
    assert calls["n"] == 2
    assert target.read_text(encoding="utf-8") == "ok"


def test_replace_raises_after_retries_exhausted(tmp_path, monkeypatch):
    def always_busy(src, dst):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(workspace_io.os, "replace", always_busy)
    with pytest.raises(PermissionError):
        workspace_io.atomic_write_text(
            str(tmp_path / "x.txt"), "ok", retries=2, sleep=lambda _s: None
        )


# --- 目录指纹 --------------------------------------------------------------


def _age_mtime(path, delta_ns=3_000_000_000):
    """把路径的 mtime 显式往前推，让"变更可检出"是写死的条件、而不是等时钟前进。

    此前这里用 time.sleep(0.01)：在 mtime 粒度粗的介质（exFAT / SMB 以秒计）上，
    "等 10ms"可能落在同一粒度里，断言就会偶发假红。delta 取 3s 是为了越过这类粒度；
    本文件多数断言其实还能靠 size 变化或"新文件"破门，推 mtime 是把另一半写显式。
    （2026-09-22 审查 MINOR；独立审查指出原注释把 delta 说大了，此处按实际口径改写。）
    """
    stat = os.stat(str(path))
    os.utime(str(path), ns=(stat.st_atime_ns, stat.st_mtime_ns + delta_ns))


def test_dir_fingerprint_changes_on_write(tmp_path):
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\nA001\n", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    (tracking / "tracker.csv").write_text("id\nA001\nA002\n", encoding="utf-8")
    _age_mtime(tracking / "tracker.csv")
    second = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])
    assert first != second


def test_dir_fingerprint_ignores_temp_and_lock(tmp_path):
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\n", encoding="utf-8")
    base = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    (tracking / (workspace_io.TMP_PREFIX + "tracker.csv")).write_text("half", encoding="utf-8")
    (tracking / "tracker.lock").write_text("", encoding="utf-8")
    assert workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"]) == base


def test_dir_fingerprint_missing_workspace_is_stable(tmp_path):
    empty = workspace_io.dir_fingerprint(str(tmp_path / "nope"), rel_dirs=["05_投递追踪"])
    again = workspace_io.dir_fingerprint(str(tmp_path / "nope"), rel_dirs=["05_投递追踪"])
    assert empty == again and len(empty) == 16


def test_default_tracked_dirs_include_fact_base(tmp_path):
    """00_事实库 纳入默认指纹（素材库去债批，2026-09-18）：素材库与笔记同为
    只读浏览——外部生成/更新的事实卡，切回来也要能看到（不补就永远看旧内容）。"""
    assert "00_事实库" in workspace_io.DEFAULT_TRACKED_DIRS

    workspace = tmp_path / "ws"
    facts = workspace / "00_事实库"
    facts.mkdir(parents=True)
    (facts / "事实卡.md").write_text("# 一", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace))  # 不带 rel_dirs → 默认集合

    (facts / "事实卡.md").write_text("# 一\n# 二", encoding="utf-8")
    _age_mtime(facts / "事实卡.md")
    assert workspace_io.dir_fingerprint(str(workspace)) != first


def test_dir_fingerprint_short_circuits_when_unchanged(tmp_path, monkeypatch):
    """P 批：两级门都过时不再走目录扫描（10s 轮询的成本大头），指纹不变。"""
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\nA001\n", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    calls = {"n": 0}
    real_walk = os.walk

    def counting_walk(*args, **kwargs):
        calls["n"] += 1
        return real_walk(*args, **kwargs)

    monkeypatch.setattr(workspace_io.os, "walk", counting_walk)
    again = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    assert again == first
    assert calls["n"] == 0, "状态未变时不该再走目录扫描（两级短路失效）"


def test_dir_fingerprint_detects_in_place_append(tmp_path):
    """in-place 追加不改目录 mtime：二级门（逐文件 stat）必须兜住这类改动。"""
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    path = tracking / "history.csv"
    path.write_text("时间,id\n", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    with io.open(str(path), "a", encoding="utf-8") as handle:
        handle.write("2026-09-21,A001\n")
    _age_mtime(path)

    assert workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"]) != first


def test_dir_fingerprint_detects_new_file_in_subdir(tmp_path):
    """缓存之后，子目录里新落一个文件也必须被发现（一级门：目录 mtime）。"""
    workspace = tmp_path / "ws"
    notes = workspace / "03_面试准备" / "技术面"
    notes.mkdir(parents=True)
    (notes / "tcp.md").write_text("# TCP", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["03_面试准备"])

    (notes / "udp.md").write_text("# UDP", encoding="utf-8")
    _age_mtime(notes)

    assert workspace_io.dir_fingerprint(str(workspace), rel_dirs=["03_面试准备"]) != first


def test_dir_fingerprint_ttl_forces_rescan_when_dir_mtime_lies(tmp_path, monkeypatch):
    """目录 mtime 不可信时，TTL 是最后一道防线（独立审查 M2）。

    一级门把「有没有增删文件」押在目录 mtime 上；在 SMB / exFAT 这类介质上它可能
    根本不动。这里手工把目录 mtime 按回原值，模拟那种说谎的介质：
    - 有 TTL → 过期后强制全量重扫，新增文件一定被发现；
    - 没有 TTL → 指纹停在旧值，外部改动再也不触发刷新（最坏情况不是延迟，是停摆）。

    顺带断言另一件事：TTL 未过期**且**两级门都通过时仍然短路（缓存不是被废掉）。
    """
    monkeypatch.setattr(workspace_io, "_FP_CACHE_TTL", 0.0)  # 每轮都全量
    workspace = tmp_path / "ws"
    notes = workspace / "03_面试准备"
    notes.mkdir(parents=True)
    (notes / "tcp.md").write_text("# TCP", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["03_面试准备"])

    frozen = os.stat(str(notes)).st_mtime_ns
    (notes / "udp.md").write_text("# UDP", encoding="utf-8")
    os.utime(str(notes), ns=(frozen, frozen))  # 目录 mtime 说谎：装作没变过

    assert workspace_io.dir_fingerprint(str(workspace), rel_dirs=["03_面试准备"]) != first


def test_dir_fingerprint_cache_still_short_circuits_within_ttl(tmp_path, monkeypatch):
    """TTL 之内且状态未变：仍然一次 walk 都不走（缓存没有被 TTL 废掉）。"""
    workspace = tmp_path / "ws"
    tracking = workspace / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text("id\nA001\n", encoding="utf-8")
    first = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    calls = {"n": 0}
    real_walk = os.walk

    def counting_walk(*args, **kwargs):
        calls["n"] += 1
        return real_walk(*args, **kwargs)

    monkeypatch.setattr(workspace_io.os, "walk", counting_walk)
    again = workspace_io.dir_fingerprint(str(workspace), rel_dirs=["05_投递追踪"])

    assert again == first
    assert calls["n"] == 0, "TTL 之内状态未变，不该回退到全量扫描"


# --- 锁名工厂 --------------------------------------------------------------


def test_lock_path_names_match_four_ends(tmp_path):
    ws = str(tmp_path / "personal")
    assert workspace_io.lock_path(ws, "tracking").replace("\\", "/").endswith(
        "/05_投递追踪/tracker.lock"
    )
    assert workspace_io.lock_path(ws, "jobs").replace("\\", "/").endswith(
        "/01_岗位池/.jobs.lock"
    )
    assert workspace_io.lock_path(ws, "resume").replace("\\", "/").endswith(
        "/02_简历工坊/resume.lock"
    )
    assert workspace_io.lock_path(ws, "imap").replace("\\", "/").endswith("/config/imap.lock")
    assert workspace_io.lock_path(ws, "provider").replace("\\", "/").endswith(
        "/config/provider.lock"
    )
    # prep：笔记勾选框写回（2026-09-18）——03/04 共用一把锁，落在 config
    # （与 imap / provider 同款）：写 04 时不会凭空建出 03_面试准备 目录
    assert workspace_io.lock_path(ws, "prep").replace("\\", "/").endswith(
        "/config/prep.lock"
    )


def test_lock_path_unknown_kind_raises(tmp_path):
    with pytest.raises(ValueError):
        workspace_io.lock_path(str(tmp_path), "nope")


def test_lock_path_does_not_create_dirs(tmp_path):
    """锁路径是纯计算：调用方自己决定何时建目录（与既有 tracker._lock_path 对齐）。"""
    ws = str(tmp_path / "personal")
    workspace_io.lock_path(ws, "tracking")
    assert not os.path.exists(os.path.join(ws, "05_投递追踪"))
