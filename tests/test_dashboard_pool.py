# -*- coding: utf-8 -*-
"""看板的岗位池视角（B3）：高分未投 + 评分档位 × 投递状态分布。

钉住四件事，按重要性排序：

1. **「高分」的下界派生自 `jd_score.THRESHOLDS`**，不是这里另写一份数字——
   两边各写一个 60 迟早会漂。
2. **未评分的岗位不参与分布**：「还没评」不等于最低档，把它塞进「不投」
   是替用户下结论。
3. **有没有投递过的判定复用 jobs 路由的匹配键（目录名）**，看板与岗位池
   对同一个岗位必须给出同一个结论。
4. 档位边界的取值：60 分进「建议投」、59 分进「斟酌」，由 THRESHOLDS 说了算。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
import jd_score  # noqa: E402
import tracker  # noqa: E402
import routers.dashboard as dash  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
JOBS_DIR = "01_岗位池"
TRACKING_DIR = "05_投递追踪"


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


def _card(total, dims):
    """造一张评分自洽的解析卡：四维之和必须等于总分，否则 consistent=False。"""
    assert sum(dims) == total, "夹具自己要先自洽，否则测的是夹具不是实现"
    lines = ["%s: %d/%d" % (name, num, maximum)
             for (name, maximum), num in zip(jd_score.DIMENSIONS, dims)]
    return ("# 解析卡\n\n## 基本信息\n公司: 某公司\n岗位: 某岗位\n\n"
            "## 评分\n" + "\n".join(lines) + "\n总分: %d\n" % total)


def _job(tmp_path, name, card_text=None):
    d = tmp_path / WS / JOBS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "JD原文.md").write_text("JD 正文", encoding="utf-8")
    if card_text:
        (d / "解析卡.md").write_text(card_text, encoding="utf-8")


def _tracking(tmp_path, rows):
    path = tmp_path / WS / TRACKING_DIR
    path.mkdir(parents=True, exist_ok=True)
    with io.open(str(path / "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for row in rows:
            full = {field: "" for field in tracker.FIELDS}
            full.update(row)
            writer.writerow(full)


def test_high_score_floor_is_derived_from_thresholds():
    floor = min(lo for lo, _hi, tier, _a in jd_score.THRESHOLDS if tier == "建议投")
    assert dash.HIGH_SCORE_FLOOR == floor


def test_tier_boundary_follows_thresholds(client, tmp_path):
    """60 分算高分未投、59 分不算——边界由 THRESHOLDS 决定，这里只验证行为。"""
    _job(tmp_path, "公司A_岗位甲", _card(60, (18, 15, 18, 9)))
    _job(tmp_path, "公司B_岗位乙", _card(59, (18, 15, 18, 8)))
    data = client.get("/api/dashboard", params={"ws": WS}).json()
    assert [i["dir"] for i in data["unappliedHigh"]] == ["公司A_岗位甲"]


def test_unapplied_high_excludes_already_applied(client, tmp_path):
    """已投过的不再提醒：匹配键用目录名，与岗位池列表同一个结论。"""
    _job(tmp_path, "公司A_岗位甲", _card(80, (24, 20, 24, 12)))
    _job(tmp_path, "公司B_岗位乙", _card(80, (24, 20, 24, 12)))
    _tracking(tmp_path, [{"id": "A001", "公司": "公司B", "岗位": "岗位乙",
                          "当前阶段": "已投"}])
    data = client.get("/api/dashboard", params={"ws": WS}).json()
    assert [i["dir"] for i in data["unappliedHigh"]] == ["公司A_岗位甲"]
    # 分布图里两条都在，只是落在不同状态桶
    tiers = {t["tier"]: t for t in data["scoreByState"]}
    bucket = tiers["强烈建议投"]
    assert (bucket["unapplied"], bucket["active"]) == (1, 1)


def test_unscored_jobs_are_not_counted_into_any_tier(client, tmp_path):
    """未评分不进任何档位——「还没评」不是最低档。"""
    _job(tmp_path, "公司A_岗位甲", _card(80, (24, 20, 24, 12)))
    _job(tmp_path, "公司B_岗位乙")  # 没有解析卡
    data = client.get("/api/dashboard", params={"ws": WS}).json()
    counted = sum(t["unapplied"] + t["active"] + t["terminal"]
                  for t in data["scoreByState"])
    assert counted == 1
    tiers = {t["tier"]: t for t in data["scoreByState"]}
    assert tiers["强烈建议投"]["unapplied"] == 1
    assert tiers["不投"] == {"tier": "不投", "unapplied": 0, "active": 0, "terminal": 0}


def test_terminal_jobs_count_as_terminal_not_unapplied(client, tmp_path):
    """挂掉了也算「投过」：分布图里进已终态桶，不该再当成未投递去提醒。"""
    _job(tmp_path, "公司A_岗位甲", _card(80, (24, 20, 24, 12)))
    _tracking(tmp_path, [{"id": "A001", "公司": "公司A", "岗位": "岗位甲",
                          "当前阶段": "已挂"}])
    data = client.get("/api/dashboard", params={"ws": WS}).json()
    assert data["unappliedHigh"] == []
    assert data["scoreByState"][0]["terminal"] == 1
