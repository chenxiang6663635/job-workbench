# -*- coding: utf-8 -*-
"""MCP 端 tracker 读取 / 追加的边界转译（#307 领域层读取与追加边界收口）。

领域层判据的三端之一：`tools_readonly` 的读点在越界时返回 **ok=false + 可读
理由**（显式拒绝，不是空列表——那会把「读不到」误判成「没投过」）；写侧
`apply_approval` 同样拒绝，且外部文件一个字节都不多（「预览是承诺」的写侧版）。

三拓扑（建链范式照抄 `mcp/tests/test_read_boundary.py`；Windows 无建链特权时
跳过，CI 的 ubuntu 跑真实行为——WinError 1314 不是回归）：
- T1 `05_投递追踪/` 是指向工作区外的 junction；
- T3 `history.csv` 文件级链接到工作区外；
- T4 `tracker.csv` 链接到**工作区内**另一份文件（反向约束）。

导入顺序有讲究：`jobws_mcp.tools_readonly` 在导入期经 `paths` 注入应用根，
tracker 导入期才求值 ROOT（同 `test_read_boundary.py` 顶部注释）。
"""

import io
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

# 先导 `paths`：它在导入期注入应用根，本文件的领域层链（tracker 求值 ROOT）才不炸
from jobws_mcp import paths  # noqa: E402,F401
from jobws_mcp import tools_readonly, tools_writable  # noqa: E402
from jobws_core import approval, tracker  # noqa: E402
from jobws_core import workspace_read  # noqa: E402
from jobws_core.tracker._schema import HISTORY_FILE  # noqa: E402

TRACKING = "05_投递追踪"


@pytest.fixture(autouse=True)
def _isolated_token_store(tmp_path, monkeypatch):
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval, "_store_dir", lambda: str(store))


def _ws(tmp_path, with_rows=True):
    ws = str(tmp_path / "personal")
    os.makedirs(os.path.join(ws, TRACKING))
    path = os.path.join(ws, TRACKING, "tracker.csv")
    if with_rows:
        with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(",".join(tracker.FIELDS) + "\n"
                        "A001,云帆,后端开发,,,,,,,待投,,,,,,\n")
    else:
        with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(",".join(tracker.FIELDS) + "\n")
    return ws


def _outside_tracking(tmp_path):
    """一个工作区**外**的追踪目录（T1 拓扑的链接目标）。"""
    outside = tmp_path / "外部追踪"
    outside.mkdir()
    with io.open(str(outside / "tracker.csv"), "w", encoding="utf-8-sig",
                 newline="") as handle:
        handle.write(",".join(tracker.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n")
    return str(outside)


def _make_dir_link_or_skip(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True)
        if result.returncode == 0:
            return
    pytest.skip("本机不能创建目录符号链接 / junction：%s -> %s" % (link, target))


def _make_file_link_or_skip(link, target):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建文件符号链接：%s" % exc)


def _replace_dir_with_link_or_skip(link, target):
    """T1 拓扑：`05_投递追踪` 已存在（夹具铺了 tracker.csv），先整体移走再换链接
    ——mklink /J 对已存在的名字报错，先删后建才是「目录被掉包」的现场。"""
    import shutil
    link = str(link)
    if os.path.isdir(link) and not os.path.islink(link):
        shutil.rmtree(link)
    _make_dir_link_or_skip(link, target)


def _snapshot(path):
    st = os.stat(path)
    return (st.st_size, st.st_mtime_ns)


# --- T1：追踪目录 junction 到区外 —— 读侧显式拒绝 -------------------------------

def test_list_applications_refuses_escaped_tracking_dir(tmp_path):
    ws = _ws(tmp_path)
    _replace_dir_with_link_or_skip(os.path.join(ws, TRACKING), _outside_tracking(tmp_path))

    data = tools_readonly.list_applications(ws)

    assert data["ok"] is False, "显式拒绝，不是空 items（那会误判成「没投过」）"
    assert any("越出工作区" in e for e in data["errors"])
    assert "外部来客" not in str(data), "外部数据一个字都不许透给宿主"


def test_dashboard_summary_refuses_escaped_tracking_dir(tmp_path):
    ws = _ws(tmp_path)
    _replace_dir_with_link_or_skip(os.path.join(ws, TRACKING), _outside_tracking(tmp_path))

    data = tools_readonly.dashboard_summary(ws)

    assert data["ok"] is False
    assert any("越出工作区" in e for e in data["errors"])


# --- T3：history.csv 文件级链接到区外 —— 读侧与写侧都拒绝 ------------------------

def test_dashboard_summary_refuses_escaped_history_file(tmp_path):
    ws = _ws(tmp_path)
    outside = os.path.join(str(tmp_path), "外部时间线.csv")
    with io.open(outside, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(tracker.HISTORY_FIELDS) + "\n"
                    "2026-10-16 09:00,A099,备注,,外部\n")
    real_history = os.path.join(ws, TRACKING, HISTORY_FILE)
    with io.open(real_history, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(tracker.HISTORY_FIELDS) + "\n")
    os.remove(real_history)
    _make_file_link_or_skip(real_history, outside)

    data = tools_readonly.dashboard_summary(ws)

    assert data["ok"] is False
    assert any("越出工作区" in e for e in data["errors"])


def test_apply_approval_refuses_escaped_history_link_without_touching_a_byte(tmp_path):
    """写侧（T3）：两段式的第二步——令牌预览时拓扑合法、确认前链接被换成外部？
    不，这里拓扑在预览**前**就是 T3（单元测试造数）：apply 时 append_history
    显式拒绝，外部文件一个字节都不能多。"""
    ws = _ws(tmp_path)
    outside = os.path.join(str(tmp_path), "外部时间线.csv")
    with io.open(outside, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(tracker.HISTORY_FIELDS) + "\n")
    before = _snapshot(outside)
    real_history = os.path.join(ws, TRACKING, HISTORY_FILE)
    with io.open(real_history, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(tracker.HISTORY_FIELDS) + "\n")
    os.remove(real_history)
    _make_file_link_or_skip(real_history, outside)

    preview = tools_writable.preview_add_application(ws, **{
        "公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
        "批次": "正式批", "当前阶段": "待投"})
    assert preview["ok"] is True, preview

    applied = tools_writable.apply_approval(ws, preview["token"])

    assert applied["ok"] is False, "apply 也显式拒绝（不是抛异常给宿主）"
    assert any("越出工作区" in e for e in applied["errors"])
    assert applied["code"] == "path.escape"
    assert _snapshot(outside) == before, "外部文件一个字节都不许动（size + mtime_ns）"
    with io.open(outside, "r", encoding="utf-8") as handle:
        assert "示例公司甲" not in handle.read()


# --- T4 反向约束：区内链接照常 -----------------------------------------------------

def test_list_applications_reads_internal_link(tmp_path):
    ws = _ws(tmp_path)
    real_csv = os.path.join(ws, TRACKING, "主表真身.csv")
    with io.open(real_csv, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(tracker.FIELDS) + "\n"
                    "A042,星海智能,算法工程师,,,,,,,一面,,,,,,\n")
    _make_file_link_or_skip(os.path.join(ws, TRACKING, "tracker.csv"), real_csv)

    data = tools_readonly.list_applications(ws)

    assert data["total"] == 1
    assert data["items"][0]["id"] == "A042", "区内链接的目标照常读回"
