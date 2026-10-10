# -*- coding: utf-8 -*-
"""读放大收口（2026-10-08 审计 1.3；2026-10-09 桶二·耗时批）。

三处「同一份文件在同一请求里被读两遍以上」的病，各钉一条结构网
（断言方式沿用 P 批 `test_list_scan_indexing.py`：**计数 + 值断言**——
防止"少读了文件、也少给了数据"这种假绿）：

1. 岗位列表 / 详情：解析卡被读 2~3 次——`_parse_card` 一次、展示名
   （`_card_basic_info`）又一次、详情端还保留了一次原文；读一次、三处复用；
2. 看板：`tracker.csv` 整表读两次（`dashboard()` 一次、`job_pool_overview` →
   `applications_by_key` 又一次）；
3. 逾期筛选：同一行 `parse_iso_date` 调两次（条件里两次相同的调用）。
"""
import os
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import jd_score  # noqa: E402
from jobws_core import tracker  # noqa: E402
from routers import jobs as jobs_router  # noqa: E402

WS = "ws-ok"
JOB = "云帆_后端"


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


def _card():
    """评分自洽（四维之和 = 总分）且带「基本信息」的解析卡。"""
    dims = [24, 20, 24, 10]                      # 30 / 25 / 30 / 15 → 总分 78
    lines = ["%s: %d/%d" % (name, num, maximum)
             for (name, maximum), num in zip(jd_score.DIMENSIONS, dims)]
    assert sum(dims) == 78
    return ("## 基本信息\n\n公司: 云帆\n岗位: 后端开发\n\n"
            "## 评分\n" + "\n".join(lines) + "\n总分: 78\n")


def _row(app_id, stage, **extra):
    row = dict((field, "") for field in tracker.FIELDS)
    row.update({"id": app_id, "公司": "云帆", "岗位": "后端",
                "方向": "backend", "批次": "正式批", "当前阶段": stage})
    row.update(extra)
    return row


def _seed_job(root, name=JOB):
    job = root / WS / "01_岗位池" / name
    job.mkdir(parents=True)
    (job / "JD原文.md").write_text("# JD\n\n示例正文。\n", encoding="utf-8")
    (job / "解析卡.md").write_text(_card(), encoding="utf-8")


def _count_card_reads(monkeypatch):
    """接住 `_read_in_workspace` 的每次调用（相对路径清单）。"""
    seen = []
    real = jobs_router._read_in_workspace

    def counting(workspace, *parts):
        seen.append("/".join(parts))
        return real(workspace, *parts)

    monkeypatch.setattr(jobs_router, "_read_in_workspace", counting)
    return seen


def _card_calls(seen):
    return [p for p in seen if p.endswith(jobs_router.CARD_FILE)]


def _expected_card_call():
    return "01_岗位池/%s/%s" % (JOB, jobs_router.CARD_FILE)


# --- 1. 岗位列表 / 详情：解析卡读一次 ------------------------------------------

def test_job_list_reads_each_card_once(client, tmp_path, monkeypatch):
    _seed_job(tmp_path)
    seen = _count_card_reads(monkeypatch)

    res = client.get("/api/jobs", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert _card_calls(seen) == [_expected_card_call()], _card_calls(seen)
    item = res.json()["items"][0]
    assert item["score"] == 78, "解析卡只读一次，但数据不能少"
    assert (item["company"], item["role"]) == ("云帆", "后端开发"), \
        "展示名仍来自卡片的「基本信息」（不是目录名回退）"


def test_job_detail_reads_card_once(client, tmp_path, monkeypatch):
    _seed_job(tmp_path)
    seen = _count_card_reads(monkeypatch)

    res = client.get("/api/jobs/%s" % JOB, params={"ws": WS})

    assert res.status_code == 200, res.text
    assert _card_calls(seen) == [_expected_card_call()], _card_calls(seen)
    body = res.json()
    assert body["card"]["total"] == 78
    assert body["cardRaw"].startswith("## 基本信息")
    assert (body["company"], body["role"]) == ("云帆", "后端开发")


# --- 2. 看板：tracker.csv 整表读一次 ------------------------------------------

def test_dashboard_reads_tracker_once(client, tmp_path, monkeypatch):
    _seed_job(tmp_path)
    tracker.write_rows([_row("A001", "已挂")], str(tmp_path / WS))
    reads = {"n": 0}
    real = tracker.read_rows

    def counting(*args, **kwargs):
        reads["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tracker, "read_rows", counting)

    res = client.get("/api/dashboard", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1
    assert reads["n"] == 1, "看板同一请求里 tracker.csv 应整表只读一次"


def test_dashboard_reads_each_card_once(client, tmp_path, monkeypatch):
    """高分未投的岗位要出展示名——此前这份解析卡会被读第二遍。"""
    _seed_job(tmp_path)
    seen = _count_card_reads(monkeypatch)

    res = client.get("/api/dashboard", params={"ws": WS})

    assert res.status_code == 200, res.text
    assert _card_calls(seen) == [_expected_card_call()], _card_calls(seen)
    assert res.json()["unappliedHigh"][0]["company"] == "云帆"


# --- 3. 逾期筛选：每行日期只解析一次 -------------------------------------------

def test_overdue_filter_parses_each_row_once(client, tmp_path, monkeypatch):
    ws_dir = str(tmp_path / WS)
    today = date.today()
    overdue_day = (today - timedelta(days=1)).isoformat()
    tracker.write_rows([
        _row("A001", "待投", 截止日期=overdue_day),
        _row("A002", "待投", 截止日期="待定"),      # 解析不出：也要只解析一次
    ], ws_dir)

    parsed = []
    real = tracker.parse_iso_date

    def counting(value):
        parsed.append(value)
        return real(value)

    monkeypatch.setattr(tracker, "parse_iso_date", counting)

    res = client.get("/api/applications", params={"ws": WS, "overdue": "1"})

    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1, "只有 A001 真的过期"
    assert parsed.count(overdue_day) == 1, "同一行的截止日期被解析了两次（旧病）"
    assert parsed.count("待定") == 1
