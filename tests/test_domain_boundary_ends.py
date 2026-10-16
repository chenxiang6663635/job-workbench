# -*- coding: utf-8 -*-
"""领域层边界判据的三端转译（#307）：Web 与 CLI。

领域层只抛 `WorkspaceBoundaryError`（读/写两侧同一类拒绝）；协议层各自转译：

- **Web**：`boundary.register` 把它映射成 400 `path.escape`——与 `deps.safe_join`
  的越界分支**同一个错误码**（前端语言包不必新增键，文案由领域层给）；
- **CLI**：`jobws.py` 主入口译成退出码 2 + 可读文案（与越界工作区同档）；
- MCP 端见 `mcp/tests/test_tracker_boundary.py`（ok=false 结构）。

T1（`05_投递追踪` 是指向工作区外的 junction）与 T3（`history.csv` 文件级链接到
区外）各一条：读端点 400 / CLI 退出码 2、写端点（approvals apply）400 且外部
文件一个字节都不多。

建链范式照抄 `tests/test_prep_toggle.py`（Windows 无特权时 junction 回退 /
文件链跳过，CI 的 ubuntu 跑真实行为）。
"""

import argparse
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import approval  # noqa: E402
import deps  # noqa: E402
import jobws  # noqa: E402
import tracker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jobws_core.tracker._schema import HISTORY_FIELDS  # noqa: E402

WS = "ws-ok"
TRACKING = "05_投递追踪"


@pytest.fixture()
def tokens(tmp_path, monkeypatch):
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval._shell, "_store_dir", lambda: str(store))
    return store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把应用根指到临时目录——不依赖仓库里真实的 `personal/`（CI 上它不存在）。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （ROOT 改写之后再导入，避免读到真实仓库根）
    return TestClient(main.app)


def _write(path, text, encoding="utf-8"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding=encoding, newline="") as handle:
        handle.write(text)


def _tracker_csv(ws):
    return os.path.join(ws, TRACKING, "tracker.csv")


def _history_csv(ws):
    return os.path.join(ws, TRACKING, "history.csv")


def _ws_dir(tmp_path):
    return str(tmp_path / WS)


def _seed_tracking(ws_dir):
    _write(_tracker_csv(ws_dir),
           ",".join(tracker.FIELDS) + "\n"
           "A001,云帆,后端开发,,,,,,,待投,,,,,,\n", encoding="utf-8-sig")


def _make_dir_link_or_skip(link, target):
    target, link = str(target), str(link)
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        result = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                capture_output=True)
        if result.returncode == 0:
            return
    pytest.skip("本机不能创建目录符号链接 / junction：%s -> %s" % (link, target))


def _make_file_link_or_skip(link, target):
    target, link = str(target), str(link)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建文件符号链接：%s" % exc)


def _replace_dir_with_link_or_skip(link, target):
    """T1 拓扑：`05_投递追踪` 已存在（铺了 tracker.csv），先整体移走再换链接
    ——mklink /J 对已存在的名字报错，先删后建才是「目录被掉包」的现场。"""
    import shutil
    if os.path.isdir(str(link)) and not os.path.islink(str(link)):
        shutil.rmtree(str(link))
    _make_dir_link_or_skip(link, target)


def _snapshot(path):
    st = os.stat(path)
    return (st.st_size, st.st_mtime_ns)


# --- Web 读侧：400 path.escape -----------------------------------------------------

def test_web_applications_refuses_escaped_tracking_dir(client, tmp_path):
    """T1：`GET /api/applications` 显式拒绝（400 path.escape），不是 200 空列表。"""
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    outside = tmp_path / "外部追踪"
    outside.mkdir()
    _write(str(outside / "tracker.csv"),
           ",".join(tracker.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), outside)

    res = client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 400, res.text
    body = res.json()
    assert body["error_code"] == "path.escape"
    assert "越出工作区" in body["detail"]
    assert "外部来客" not in body["detail"], "错误消息不夹带外部数据"


def test_web_dashboard_refuses_escaped_tracking_dir(client, tmp_path):
    """T1（看板同一条链）：/api/dashboard 也走领域层 read_rows + read_history。"""
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    outside = tmp_path / "外部追踪"
    outside.mkdir()
    _write(str(outside / "tracker.csv"),
           ",".join(tracker.FIELDS) + "\n", encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), outside)

    res = client.get("/api/dashboard", params={"ws": WS})

    assert res.status_code == 400
    assert res.json()["error_code"] == "path.escape"


# --- Web 写侧：apply 400 且外部一字节不多 ------------------------------------------

def test_web_apply_refuses_escaped_history_link_without_touching_a_byte(
        client, tmp_path, tokens):
    """T3（写侧）：预览合法 → apply 时 append_history 拒绝；外部时间线一个
    字节都不多（「预览是承诺」的写侧版）。"""
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    _write(_history_csv(ws_dir),
           ",".join(HISTORY_FIELDS) + "\n"
           "2026-10-16 09:00,A001,备注,,已有\n")
    outside = tmp_path / "外部时间线.csv"
    _write(outside, ",".join(HISTORY_FIELDS) + "\n")
    before = _snapshot(str(outside))
    os.remove(_history_csv(ws_dir))
    _make_file_link_or_skip(_history_csv(ws_dir), outside)

    preview = client.post("/api/applications/import", params={"ws": WS},
                         json={"csv": "公司,岗位,方向,批次,当前阶段\n"
                                      "公司A,岗位甲,hvac,正式批,已投\n",
                               "mode": "preview"})
    assert preview.status_code == 200, preview.text
    token = preview.json()["token"]

    res = client.post("/api/approvals/apply", json={"token": token})

    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "path.escape"
    assert _snapshot(str(outside)) == before, "外部文件一个字节都不许动（size + mtime_ns）"


# --- CLI 侧：退出码 2 + 可读文案 ---------------------------------------------------

def test_cli_track_list_refuses_escaped_tracking_dir(tmp_path, capsys):
    """T1（读侧）：`jobws track list` 显式拒绝（退出码 2 + 文案），不打印空表。"""
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    outside = tmp_path / "外部追踪"
    outside.mkdir()
    _write(str(outside / "tracker.csv"),
           ",".join(tracker.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), outside)

    code = jobws.main(["track", "--workspace", ws_dir, "list"])

    assert code == 2
    out = capsys.readouterr()
    assert "越出工作区" in out.out
    assert "外部来客" not in out.out, "错误消息不夹带外部数据"


# --- T4 反向约束：区内链接照常（同步盘分片是合法用法） -----------------------------

def test_web_applications_reads_internal_link(tmp_path, client):
    """T4（Web）：追踪目录链接到**工作区内**另一份真身——照常读到，不误伤。

    真身必须落在工作区**里面**（ws/分片/），落在旁边就成了 T1——这正是 2026-10-16
    自审时第一版写错的地方。
    """
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)          # 先建出 ws 目录（原主表随换链被移走）
    inside_real = os.path.join(ws_dir, "分片", "追踪真身")
    os.makedirs(inside_real)
    _write(os.path.join(inside_real, "tracker.csv"),
           ",".join(tracker.FIELDS) + "\nA001,云帆,后端开发,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), inside_real)

    res = client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert "云帆" in res.text, "区内链接的数据必须照常返回"


def test_cli_track_list_reads_internal_link(tmp_path, capsys):
    """T4（CLI）：同一条反向约束的 CLI 半边——判据改严时这里必须红。"""
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    inside_real = os.path.join(ws_dir, "分片", "追踪真身")
    os.makedirs(inside_real)
    _write(os.path.join(inside_real, "tracker.csv"),
           ",".join(tracker.FIELDS) + "\nA001,云帆,后端开发,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), inside_real)

    code = jobws.main(["track", "--workspace", ws_dir, "list"])

    assert code == 0
    assert "云帆" in capsys.readouterr().out, "区内链接的数据必须照常列出"


def test_cli_apply_refuses_escaped_tracking_dir_without_touching_a_byte(
        tmp_path, tokens, capsys):
    """T1（CLI apply）：退出码 **1**（blocked，与 `ApprovalConflict` 同族），不是 2。

    两档必须各有测试钉住：读路径（上一条）是「这个工作区没法用」→ 2（与越界工作区
    同档）；apply 是「操作被拒」→ 1。没有这条，1/2 的分裂会被当成笔误改掉。
    用 T1（整个追踪目录是 junction）而非 T3（history.csv 文件级链接）：junction 本机
    可建（mklink /J 不要特权），这条在 Windows 上就能真跑；T3 版本见
    `mcp/tests/test_tracker_boundary.py`（apply_approval 结构化拒绝）。
    """
    ws_dir = _ws_dir(tmp_path)
    _seed_tracking(ws_dir)
    args = argparse.Namespace(  # 与 tracker add 子命令参数表一致（少一个会 AttributeError）
        company="示例公司甲", role="示例岗位乙", direction="backend", batch="正式批",
        source=None, deadline=None, applied=None, stage="待投", reason=None,
        next=None, next_date=None, resume=None, score=None, archive=None,
        note=None, link=None, preview=True)
    errors, plan = tracker.preview_add(args, str(ws_dir))
    assert errors == [] and plan, "预览时拓扑还是合法的"
    token = approval.preview("track.add", str(ws_dir), plan["payload"],
                             plan["summary"], plan["diff"], plan["targets"])

    outside = tmp_path / "外部追踪"
    outside.mkdir()
    _write(str(outside / "tracker.csv"),
           ",".join(tracker.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _write(str(outside / "history.csv"), ",".join(HISTORY_FIELDS) + "\n",
           encoding="utf-8-sig")
    before = {p: _snapshot(str(p)) for p in
              (outside / "tracker.csv", outside / "history.csv")}
    _replace_dir_with_link_or_skip(os.path.join(ws_dir, TRACKING), outside)

    code = jobws.main(["apply", token["token"]])

    assert code == 1, "apply 的归属拒绝是 blocked（1）"
    out = capsys.readouterr()
    assert "拒绝" in out.out and "越出工作区" in out.out
    assert "外部来客" not in out.out, "错误消息不夹带外部数据"
    for path, snap in before.items():
        assert _snapshot(str(path)) == snap, \
            "外部文件一个字节都不许动（size + mtime_ns）：%s" % path
