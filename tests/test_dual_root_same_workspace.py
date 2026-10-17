# -*- coding: utf-8 -*-
"""双数据根 + 同名工作区（外部审计 P2，复核升 P0）的**取证**测试。

复核指出的组合风险：`deps.allowed_roots()` 的顺序是「应用根 → 数据根」，
`list_workspaces()` 按此顺序扫描、同名工作区只留第一个；而 `?ws=<name>` 的
解析是「数据根优先、应用根兜底」，前端 `X-Jobws-Workspace` 只校验工作区
**名**、不校验数据根**身份**。于是 A（历史根）与 B（当前数据根）都有
`personal` 时：列表可能按 A 判 `isDefault=false`、业务接口却读 B；更敏感的
形态是 B 可访问但其中 `personal` 已不存在时，显式 `?ws=personal` 会**静默
回落到 A 的旧副本**——而回显头里只有名字，用户无从察觉。

本文件最初是**取证**（2026-10-16，红即缺陷证据）；同日收口后转为**契约回归网**：
「工作区只从当前数据根解析、不跨根兜底、写不落到非当前根、重启不漂移」。
若再次变红，意味着「哪个根」又被引入第二个真源。

夹具照 `tests/test_data_root_api.py` 的隔离范式（APPDATA / XDG_DATA_HOME 指到
tmp、`monkeypatch.setattr(deps, "ROOT", ...)` 之后再导入 main）；B 的选定走仓库
既有的持久化机制 `POST /api/system/data-root`（写
`<user_data_dir>/state/data-root.json`，与 CLI / 设置页同一条解析链）。
"""

import csv
import io
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

import deps  # noqa: E402
from jobws_core import dataroot, jd_score, tracker  # noqa: E402

WS = "personal"
JOBS = "01_岗位池"
TRACK = "05_投递追踪"
CARD = "解析卡.md"

# 两个根各自的「可区分内容」标记：出现在追踪表公司与岗位目录名里
TAG_A, TAG_B = "A_ONLY", "B_ONLY"
# 解析卡四维（30/25/30/15）：A=30 分、B=88 分，读侧据此分辨落在哪个根
DIMS_A, DIMS_B = (9, 7, 9, 5), (26, 22, 27, 13)


def _card(dims):
    """评分自洽的最小解析卡（写法照 tests/test_dashboard_pool.py）。"""
    lines = ["%s: %d/%d" % (name, num, maximum)
             for (name, maximum), num in zip(jd_score.DIMENSIONS, dims)]
    return "# 解析卡\n\n## 评分\n" + "\n".join(lines) + "\n总分: %d\n" % sum(dims)


def _mk_root(root, tag, dims):
    """造一个含 `personal` 工作区的数据根，内容带 tag 标记（区分 A / B）。"""
    ws = os.path.join(str(root), WS)
    os.makedirs(os.path.join(ws, "config"), exist_ok=True)
    with io.open(os.path.join(ws, "config", "profile.md"), "w", encoding="utf-8") as fh:
        fh.write("# 档案（%s）\n" % tag)
    csv_path = os.path.join(ws, TRACK, "tracker.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with io.open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=tracker.FIELDS)
        writer.writeheader()
        row = {field: "" for field in tracker.FIELDS}
        row.update({"id": tag + "001", "公司": tag, "岗位": "示例岗位",
                    "方向": "other", "当前阶段": "待投", "备注": tag})
        writer.writerow(row)
    job = os.path.join(ws, JOBS, "%s_示例岗位" % tag)
    os.makedirs(job, exist_ok=True)
    for name, text in (("JD原文.md", "JD（%s）\n" % tag), (CARD, _card(dims))):
        with io.open(os.path.join(job, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    return ws


def _bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _tracker(root):
    return os.path.join(str(root), WS, TRACK, "tracker.csv")


@pytest.fixture()
def dual(tmp_path, monkeypatch):
    """A＝应用根（历史副本）、B＝当前数据根；两个根都有同名 `personal`。"""
    a, b = tmp_path / "app", tmp_path / "data"
    _mk_root(a, TAG_A, DIMS_A)
    _mk_root(b, TAG_B, DIMS_B)

    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(a))

    import main  # noqa: E402  （ROOT 改写之后再导入）
    with TestClient(main.app) as client:
        # 既有的持久化选择机制（控制面端点 = CLI / 设置页同一条链）把 B 设为当前根
        picked = client.post("/api/system/data-root", json={"path": str(b)})
        assert picked.status_code == 200, picked.text
        yield SimpleNamespace(client=client, a=str(a), b=str(b), tmp=tmp_path)


# --- 夹具自检：先证明「B 确实被设为当前数据根」，否则本文件全部结论无效 ---------

def test_fixture_really_selects_b_as_current_data_root(dual):
    sel = dataroot.read_persisted_selection()
    assert sel["readable"] is True and sel["path"] == dual.b, sel
    assert os.path.normpath(deps.data_root()) == dual.b
    assert os.path.normpath(deps.resolve_default_workspace()) == os.path.join(dual.b, WS)
    # 收口后「允许根」只有一个：当前数据根（此前是 [A, B]，正是双真源的入口）
    assert [os.path.normpath(r) for r in deps.allowed_roots()] == [dual.b]
    diag = dual.client.get("/api/system/data-root").json()
    assert (diag["path"], diag["source"], diag["state"]) == (dual.b, "persisted", "ok")


# --- 不变量 1：列表与详情一致性 ------------------------------------------------

def test_list_marks_exactly_one_default_and_it_is_the_served_one(dual):
    items = dual.client.get("/api/workspaces").json()["items"]
    assert [i["name"] for i in items] == [WS], "同名工作区只该出现一条：%r" % items
    marked = [i for i in items if i["isDefault"]]
    assert len(marked) == 1, "默认工作区在界面上没有落点：%r" % items
    rows = dual.client.get("/api/applications",
                           params={"ws": marked[0]["name"]}).json()["items"]
    assert [r["公司"] for r in rows] == [TAG_B], rows


# --- 不变量 2：读取一致性（tracker / jd_score 都落在 B） ------------------------

def test_tracker_reads_b_only(dual):
    res = dual.client.get("/api/applications", params={"ws": WS})
    assert res.status_code == 200, res.text
    assert res.headers["X-Jobws-Workspace"] == WS
    assert [r["公司"] for r in res.json()["items"]] == [TAG_B], res.text


def test_jd_score_reads_b_only(dual):
    res = dual.client.get("/api/jobs", params={"ws": WS})
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["dir"] for i in items] == ["%s_示例岗位" % TAG_B], items
    assert items[0]["score"] == sum(DIMS_B), items


# --- 不变量 3：写入隔离性（优先级最高）----------------------------------------

def test_write_changes_only_b_leaving_a_byte_identical(dual):
    before_a, before_b = _bytes(_tracker(dual.a)), _bytes(_tracker(dual.b))

    res = dual.client.patch("/api/applications/%s001" % TAG_B,
                            json={"备注": TAG_B + "-改过"}, params={"ws": WS})
    assert res.status_code == 200, res.text

    assert _bytes(_tracker(dual.a)) == before_a, "A（历史快照）的追踪表被改动了"
    after_b = _bytes(_tracker(dual.b))
    assert after_b != before_b and "改过".encode("utf-8") in after_b


# --- 不变量 4：重启与覆盖语义 --------------------------------------------------

def test_restart_keeps_the_selection_on_b(dual):
    """新进程（真正的重启）重新解析：仍须落在持久化的 B 上，不漂移。"""
    env = dict(os.environ)
    env.pop("JOBWS_DATA_DIR", None)
    env.pop("JOBWS_WORKSPACE", None)
    env["APPDATA"] = str(dual.tmp / "appdata")
    env["XDG_DATA_HOME"] = str(dual.tmp / "appdata")
    code = ("from jobws_core import dataroot;"
            "print(dataroot.resolve_data_root(dataroot.form_for_process(), %r).path)"
            % dual.a)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert os.path.normpath(proc.stdout.strip()) == dual.b, proc.stdout


def test_explicit_env_data_root_without_personal_does_not_fall_back_to_a(
        dual, tmp_path, monkeypatch):
    other = tmp_path / "other-root"
    other.mkdir()
    monkeypatch.setenv("JOBWS_DATA_DIR", str(other))

    res = dual.client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 404, (
        "显式指定的数据根里没有 personal：必须 404，不能静默读 A 的旧副本（%s %s）"
        % (res.status_code, res.text))


def test_missing_personal_in_b_is_not_served_from_a(dual):
    shutil.rmtree(os.path.join(dual.b, WS))

    res = dual.client.get("/api/applications", params={"ws": WS})

    assert res.status_code == 404, (
        "B 里没有 personal 时不得静默回落到 A（%s %s）" % (res.status_code, res.text))


def test_write_when_b_personal_is_gone_leaves_a_byte_identical(dual):
    before_a = _bytes(_tracker(dual.a))
    shutil.rmtree(os.path.join(dual.b, WS))

    res = dual.client.patch("/api/applications/%s001" % TAG_A,
                            json={"备注": "污染"}, params={"ws": WS})

    assert _bytes(_tracker(dual.a)) == before_a, (
        "写到了非预期的历史数据根 A（HTTP %s：%s）" % (res.status_code, res.text))


def test_cleared_selection_falls_back_to_legacy_portable_with_honest_source(dual):
    """清掉选择 → 回到 legacy 判定：本夹具是**便携布局**（应用根里有 personal），
    于是数据根＝应用根，这是解析链的设计行为（`source=legacy_portable`），
    **不是**"已选 B 却静默回退 A"那类跨根兜底——两者在诊断对象里可区分，
    设置页会把来源显示出来（`dataLocSource`）。

    取证版此前把两者混成一条断言（"无选择时不得接管 A"），收口后按契约改写：
    断言的是**来源如实上报 + 服务对象与该来源一致**。
    """
    assert dual.client.delete("/api/system/data-root").status_code == 200
    assert os.path.normpath(deps.data_root()) == dual.a          # 便携布局的 legacy 根

    diag = dual.client.get("/api/system/data-root").json()
    assert diag["path"] == dual.a and diag["source"] == "legacy_portable", diag

    res = dual.client.get("/api/applications", params={"ws": WS})
    assert res.status_code == 200, res.text
    assert [r["公司"] for r in res.json()["items"]] == [TAG_A], res.text
