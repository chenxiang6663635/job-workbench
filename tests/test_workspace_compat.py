# -*- coding: utf-8 -*-
"""工作区兼容性排练（issue #208）：版本化旧工作区 → 打开·读·改·重读·校验。

背景：`docs/support-and-compatibility.md` 承诺「升级不要求手动迁移数据」，
而支撑它的长期只有文档与零散测试。本文件把承诺变成**可执行断言**，夹具是
`tests/fixtures/workspaces/` 下三组版本化样本：

- `v0.3-shape/`：按 v0.3.0 的表头（16 列，**无「链接」**——那是后来加的列）
- `legacy-missing-columns/`：当前列集删掉两个后加的列（链接 / 归档目录）
- `malformed/`：三份坏输入（引号不闭合 / 空文件 / GBK 字节），各成一个最小工作区

纪律：夹具全部**假数据**；测试一律先 `copytree` 到 tmp 再操作——夹具本体只读
（下面有「读路径不改文件」的断言守着这条）。
"""

import io
import os
import shutil
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "packages", "jobws-core", "src"))

from jobws_core import tracker  # noqa: E402
from jobws_core.tracker import FIELDS  # noqa: E402

FIXTURES = os.path.join(ROOT_DIR, "tests", "fixtures", "workspaces")


def _stage(name, tmp_path):
    """把夹具复制到 tmp 再操作（夹具本体绝不被测试改写）。"""
    dst = os.path.join(str(tmp_path), "ws")
    shutil.copytree(os.path.join(FIXTURES, *name.split("/")), dst)
    return dst


def _csv_path(ws):
    return os.path.join(ws, "05_投递追踪", "tracker.csv")


def _header(ws):
    with io.open(_csv_path(ws), "r", encoding="utf-8-sig", newline="") as handle:
        return handle.readline().strip().split(",")


def _blank_row(**overrides):
    row = {field: "" for field in FIELDS}
    row.update(overrides)
    return row


def test_v03_shape_reads_with_new_columns_empty(tmp_path):
    """v0.3 时代的工作区（表头 16 列、无「链接」）：读得出，缺的新列按空。"""
    ws = _stage("v0.3-shape", tmp_path)

    rows = tracker.read_rows(ws)

    assert len(rows) == 2
    assert rows[0]["公司"] == "示例科技"
    assert not (rows[0].get("链接") or ""), "老工作区缺的列要按空读，而不是报错或丢行"


def test_v03_shape_write_upgrades_header_without_manual_migration(tmp_path):
    """核心剧本：老工作区**原地**可改，一次写回就把表头补齐到当前列集。"""
    ws = _stage("v0.3-shape", tmp_path)
    rows = tracker.read_rows(ws)
    rows.append(_blank_row(id="A003", 公司="星河数据", 岗位="热管理工程师",
                           方向="software-backend"))

    tracker.write_rows(rows, ws)

    again = tracker.read_rows(ws)
    assert len(again) == 3
    assert any(row.get("公司") == "星河数据" for row in again)
    assert _header(ws) == FIELDS, "写回应把表头升级到当前列集——用户无需手动迁移"


def test_legacy_missing_columns_round_trip(tmp_path):
    """缺两列（链接 / 归档目录）的老表：读→改→重读 全链不丢数据。"""
    ws = _stage("legacy-missing-columns", tmp_path)

    rows = tracker.read_rows(ws)
    assert len(rows) == 1
    assert rows[0]["公司"] == "示例科技"
    assert not (rows[0].get("链接") or "") and not (rows[0].get("归档目录") or "")

    rows[0]["备注"] = "改过的备注"
    tracker.write_rows(rows, ws)

    again = tracker.read_rows(ws)
    assert again[0]["备注"] == "改过的备注"
    assert again[0]["公司"] == "示例科技", "其余列一个都不能丢"
    assert _header(ws) == FIELDS


@pytest.mark.parametrize("case", ["unclosed-quote", "empty", "bad-encoding"])
def test_malformed_read_never_modifies_the_file(case, tmp_path):
    """坏输入：**读路径任何情况下都不许改文件**（不静默覆盖掉用户的原始数据）。

    三种坏法的失败形态不同（引号不闭合可能被 csv 宽容读成畸形行、空文件读出
    零行、非法字节直接抛）——但「文件字节不变」对三者都成立，这是这里要钉的。
    """
    ws = _stage("malformed/" + case, tmp_path)
    path = _csv_path(ws)
    with io.open(path, "rb") as handle:
        before = handle.read()

    try:
        tracker.read_rows(ws)
    except Exception:  # noqa: BLE001 —— 报错是允许的（下方单独钉住 bad-encoding）
        pass

    with io.open(path, "rb") as handle:
        assert handle.read() == before, "读操作改动了文件——这是最危险的一类缺陷"


def test_bad_encoding_fails_loudly(tmp_path):
    """非法字节：宁可响亮报错，也不静默读成乱码再写回去覆盖原数据。"""
    ws = _stage("malformed/bad-encoding", tmp_path)

    with pytest.raises(UnicodeDecodeError):
        tracker.read_rows(ws)


def test_empty_file_reads_as_no_rows(tmp_path):
    """空文件 → 零行（而不是崩溃）：用户手工清空过 CSV 的真实场景。"""
    ws = _stage("malformed/empty", tmp_path)

    assert tracker.read_rows(ws) == []


def test_fixtures_are_read_only():
    """夹具本体自检：三组都在、且 v0.3 样本的表头确实**没有**「链接」列。

    最后一条是防「夹具被改成当前形状」——那会让兼容性测试变成自说自话。
    """
    v03_header = _header(os.path.join(FIXTURES, "v0.3-shape"))
    assert "链接" not in v03_header, "v0.3-shape 夹具必须保持历史表头（无「链接」）"
    assert len(v03_header) == 16

    legacy_header = _header(os.path.join(FIXTURES, "legacy-missing-columns"))
    assert "链接" not in legacy_header and "归档目录" not in legacy_header

    for case in ("unclosed-quote", "empty", "bad-encoding"):
        assert os.path.isfile(os.path.join(FIXTURES, "malformed", case,
                                           "05_投递追踪", "tracker.csv"))
