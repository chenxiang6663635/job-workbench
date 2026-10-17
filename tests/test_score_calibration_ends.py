# -*- coding: utf-8 -*-
"""筛选校准的**端到端同源**（设计文档 §八.5）：core（唯一实现）与 Web API
（`/api/dashboard` 的 `calibration` 字段）必须给出逐字段相同的结果。

MCP 那一条腿在 `mcp/tests/test_score_calibration.py`——MCP SDK 只装在 MCP venv
里，主套件 import 不到（`mcp.types`）。两条腿各自跑在自己的 venv，合起来覆盖三端。

判据是**逐字段比对**，不是"都包含某个 key"——后者在两端口径悄悄分叉时照样绿。
"""

import io
import os
import sys
from datetime import date

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"),
           os.path.join(ROOT_DIR, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jobws_core import jd_score, job_pool, score_calibration, tracker  # noqa: E402

WS = "personal"
JOB_DIR = "01_岗位池"
TRACK_DIR = "05_投递追踪"
_DIMENSIONS = jd_score.DIMENSIONS


def _card(total_dims):
    """一张自愈解析卡：四维按给定分子填，总分 = 加权和。"""
    names = [n for n, _m in _DIMENSIONS]
    lines = ["%s: %d/%d" % (name, num, _DIMENSIONS[i][1])
             for i, (name, num) in enumerate(zip(names, total_dims))]
    return ("## 基本信息\n公司: 校准科技\n岗位: 后端\n\n"
            "## 评分\n" + "\n".join(lines) + "\n总分: %d\n\n"
            "## 硬门槛\n门槛结论: 通过\n" % sum(total_dims))


from jobws_core import jd_score  # noqa: E402

_DIMENSIONS = jd_score.DIMENSIONS


def _seed(tmp_path, n_high, n_mid):
    """同一份数据：n_high 个高分档投递 + n_mid 个中档投递 + 1 个未投递。"""
    ws = tmp_path / WS
    (ws / JOB_DIR).mkdir(parents=True)
    (ws / TRACK_DIR).mkdir(parents=True)

    rows = []
    for i in range(n_high):
        name = "高分%d_后端" % i
        (ws / JOB_DIR / name).mkdir()
        with io.open(str(ws / JOB_DIR / name / "解析卡.md"), "w", encoding="utf-8") as fh:
            fh.write(_card([24, 20, 24, 12]))            # 80 → 强烈建议投
        rows.append({"id": "H%03d" % i, "公司": "高分%d" % i, "岗位": "后端",
                     "当前阶段": "offer" if i % 2 else "已投", "评分": "80"})
    for i in range(n_mid):
        name = "中分%d_后端" % i
        (ws / JOB_DIR / name).mkdir()
        with io.open(str(ws / JOB_DIR / name / "解析卡.md"), "w", encoding="utf-8") as fh:
            fh.write(_card([15, 12, 15, 8]))             # 50 → 斟酌
        rows.append({"id": "M%03d" % i, "公司": "中分%d" % i, "岗位": "后端",
                     "当前阶段": "已挂", "评分": "50"})
    # 时间线：中档那些行进过「已投」再挂——没有它，转化率按"当前存量"算会把
    # 已投的到达数记成 0（rate=None），该档就退化成"不可比较"。
    with io.open(str(ws / TRACK_DIR / "history.csv"), "w", encoding="utf-8-sig") as fh:
        fh.write("时间,id,字段,原值,新值\n")
        for i in range(n_mid):
            fh.write("2026-10-01 10:00,M%03d,当前阶段,已投,已挂\n" % i)
    # 一个没投的高分岗位：进 ② 的记账，不进 ① 的分母
    (ws / JOB_DIR / "没投_后端").mkdir()
    with io.open(str(ws / JOB_DIR / "没投_后端" / "解析卡.md"), "w", encoding="utf-8") as fh:
        fh.write(_card([24, 20, 24, 12]))

    tracker.write_rows(rows, str(ws))
    return ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    import main  # noqa: E402
    return TestClient(main.app)


def _core(ws):
    rows = tracker.read_rows(str(ws))
    # today 必须给真值：report.retrospective 用它算停留天数（None 会炸）
    return score_calibration.calibration_data(rows, date.today(), str(ws))


def test_api_and_core_agree_field_by_field(tmp_path, monkeypatch, client):
    """core（唯一实现）与 Web API：同一份数据的校准结果逐字段相同。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    ws = _seed(tmp_path, n_high=4, n_mid=4)

    expected = _core(ws)
    assert expected["tiers"], "夹具没造出可比较的档位，这条断言会空转"

    res = client.get("/api/dashboard", params={"ws": WS})
    assert res.status_code == 200, res.text
    api = res.json()["calibration"]

    assert api == expected, "API 与 core 漂移"

    # 关键字段再显式钉一次（上面全等已覆盖，这里是失败时可读性）
    tiers = {t["tier"]: t for t in api["tiers"]}
    assert tiers["强烈建议投"]["applied"] == 4
    assert tiers["斟酌"]["applied"] == 4
    assert api["unapplied"]["total"] == 1
    assert api["unapplied"]["gatePassed"] == 1
    assert "数据显示" in api["conclusion"]["text"]


def test_calibration_endpoint_writes_nothing(tmp_path, monkeypatch, client):
    """四端都一样只读：API 调一次，工作树逐字节不变（反目标在端到端层再钉一次）。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    ws = _seed(tmp_path, n_high=3, n_mid=3)

    def snapshot():
        out = {}
        for base, _dirs, files in os.walk(str(tmp_path)):
            for fn in files:
                full = os.path.join(base, fn)
                with open(full, "rb") as fh:
                    out[os.path.relpath(full, str(tmp_path))] = fh.read()
        return out

    before = snapshot()
    res = client.get("/api/dashboard", params={"ws": WS})
    assert res.status_code == 200, res.text
    assert snapshot() == before, "看板接口写了工作区"
