# -*- coding: utf-8 -*-
"""`jobws_core.containment` 锁死测试（2026-09-25 发布前收口批）。

覆盖两层：
1. 已落盘原语的既有语义（包含关系 / 排除根自身 / 字符串前缀误判 / 三类越界写法）；
2. 本批新增与接线的行为：`is_within_or_equal`（浏览与拼接场景的「含等于」语义
   ——`ro_files.inside` 与 `deps.safe_join` 的迁移目标）、symlink 逃逸 fail-closed、
   链接目标仍在根内时不误拒。

Windows 上创建目录符号链接需要开发者模式：拿不到权限时跳过链接用例并明说
（CI 在 ubuntu 上跑真实行为，本地无权限不会假绿）。
"""

import os

import pytest

from jobws_core import containment


def _make_symlink_or_skip(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建目录符号链接：%s" % exc)


# --- is_within：基本包含 / 根自身 / 前缀误判 --------------------------------------

def test_is_within_basic(tmp_path):
    root = tmp_path / "root"
    child = root / "ws" / "sub"
    child.mkdir(parents=True)
    assert containment.is_within(str(child), str(root)) is True


def test_root_itself_is_not_within(tmp_path):
    """恰好等于根 → 越界（放开它等于允许枚举根的直属子项）。"""
    root = tmp_path / "root"
    root.mkdir()
    assert containment.is_within(str(root), str(root)) is False


def test_sibling_with_shared_prefix_is_not_within(tmp_path):
    """字符串前缀的经典误判：`…/a/bc` 以 `…/a/b` 为前缀但不在其内部。"""
    root = tmp_path / "a" / "b"
    sibling = tmp_path / "a" / "bc"
    root.mkdir(parents=True)
    sibling.mkdir(parents=True)
    assert containment.is_within(str(sibling), str(root)) is False


def test_within_any_checks_all_roots(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "x").mkdir(parents=True)
    b.mkdir()
    assert containment.within_any(str(a / "x"), [str(b), str(a)]) is True
    assert containment.within_any(str(tmp_path / "c"), [str(a), str(b)]) is False


# --- is_within_or_equal：浏览 / 拼接场景（本批新增） ------------------------------

def test_is_within_or_equal_allows_root_itself(tmp_path):
    """`ro_files.inside` 与 `deps.safe_join` 的语义：目标**可以是基目录自身**
    （浏览素材库根、`safe_join(ws)` 无片段拼接）。"""
    root = tmp_path / "root"
    root.mkdir()
    assert containment.is_within_or_equal(str(root), str(root)) is True


def test_is_within_or_equal_still_rejects_outside(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    assert containment.is_within_or_equal(str(outside), str(root)) is False


def test_is_within_or_equal_rejects_sibling_with_shared_prefix(tmp_path):
    root = tmp_path / "a" / "b"
    sibling = tmp_path / "a" / "bc"
    root.mkdir(parents=True)
    sibling.mkdir(parents=True)
    assert containment.is_within_or_equal(str(sibling), str(root)) is False


def test_strictly_within_any_rejects_root_itself_even_nested(tmp_path):
    """等于任一允许根 → 拒绝，哪怕它恰好在**另一个根**内部。

    数据根 ⊆ 应用根（JOBWS_DATA_DIR 指向仓库内目录）的真实拓扑：
    `?ws=ws-in/../` normpath 到数据根本身，只按「在应用根内部」判定就会
    200 服务「所有工作区的父目录」（独立审查 MINOR-1）。`is_within` 只排除
    「等于同一个根」，跨根相等要靠本函数的「不等于任何根」兜住。
    """
    app_root = tmp_path / "app"
    data_root = app_root / ".data"
    (data_root / "ws").mkdir(parents=True)
    roots = [str(app_root), str(data_root)]
    assert containment.strictly_within_any(str(data_root), roots) is False
    assert containment.strictly_within_any(str(data_root / "ws"), roots) is True
    # 对照（形态记录）：单根语义会把数据根视为「在应用根内部」——
    # 所以工作区解析必须用 strictly 版本，而不是删掉任何一侧检查。
    assert containment.within_any(str(data_root), roots) is True


# --- symlink 逃逸（发布前审计 P1-B 的核心回归） -----------------------------------

def test_symlink_escape_is_rejected(tmp_path):
    """根内链接指向根外 → 越界（fail-closed）；链接下的文件同样按真实目标判定。"""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    _make_symlink_or_skip(link, outside)
    assert containment.is_within(str(link), str(root)) is False
    assert containment.is_within_or_equal(str(link / "f.txt"), str(root)) is False


def test_symlink_inside_is_accepted(tmp_path):
    """链接目标仍在根内 → 不误拒（合法用法：把工作区分区做成 junction）。"""
    root = tmp_path / "root"
    real_dir = root / "real"
    real_dir.mkdir(parents=True)
    link = root / "alias"
    _make_symlink_or_skip(link, real_dir)
    assert containment.is_within(str(link), str(root)) is True
    assert containment.is_within_or_equal(str(link / "note.md"), str(root)) is True


# --- escape_reason：三类越界写法 ---------------------------------------------------

@pytest.mark.parametrize("name,reason", [
    ("/etc/passwd", "是绝对路径"),
    ("../evil", "含 .. 段"),
    ("a/../../b", "含 .. 段"),
    ("C:foo", "含盘符"),
    ("a/C:foo/b", "含盘符"),
    ("", "为空"),
    ("   ", "为空"),
])
def test_escape_reason_flags(name, reason):
    assert containment.escape_reason(name) == reason


def test_escape_reason_windows_absolute_is_flagged():
    """`C:\\Windows`：Windows 上是绝对路径、POSIX 上按盘符段判——两者都是越界写法。

    不断言具体原因词，是为了让本用例在两个平台上都表达同一条规则。
    """
    assert containment.escape_reason("C:\\Windows") in ("是绝对路径", "含盘符")


@pytest.mark.parametrize("name", ["personal", "./personal", "a/b/c", "中文工作区", "a b"])
def test_escape_reason_allows_normal_names(name):
    assert containment.escape_reason(name) is None
