# -*- coding: utf-8 -*-
"""只读工具的单测：不依赖 MCP SDK，Python 3.10+ 起即可跑。

两个刻意的安排：

1. 工作区造在 tmp 下并让 `JOBWS_DATA_DIR` 指向它——否则 `resolve_workspace`
   的「必须落在允许根之内」检查会直接拒绝 tmp 路径，而那条检查本身就是要测的。
2. 数据真实落盘（CSV/解析卡）而不是 mock 掉读取：这些工具的全部价值在于
   **口径与 CLI/Web 同源**，只测 mock 过的调用等于什么都没测。

造数样板沿用 `tests/test_job_linking.py` 与 `test_portability.py`。
"""

import csv
import io
import os
import sys
from datetime import date, timedelta

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from jobws_mcp import paths, tools_readonly  # noqa: E402
from jobws_core import tracker  # noqa: E402  （tools/ 已由 paths.py 加进 sys.path）

TODAY = date(2026, 9, 14)


def _row(**kw):
    row = dict((k, "") for k in tracker.FIELDS)
    row.update(kw)
    return row


def _write_tracker(ws, rows):
    d = os.path.join(ws, "05_投递追踪")
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(os.path.join(d, "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tracker.FIELDS, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_job(ws, dirname, company=None, role=None, total=78, consistent=True):
    """造一个岗位目录。不传 company/role 时「基本信息」段为空，
    用于验证此时回退到目录名切分（与 jobs.py 同口径）。

    consistent=False 时四维之和与总分不符，模拟填了一半的解析卡——
    后端对这种卡片不给档位，MCP 必须一致。
    """
    d = os.path.join(ws, "01_岗位池", dirname)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(os.path.join(d, "JD原文.md"), "w", encoding="utf-8") as f:
        f.write("# JD\n\n示例岗位描述。\n")

    if consistent:
        tech = int(round(total * 0.30))       # 满分 30
        exp = int(round(total * 0.25))        # 满分 25
        fit = int(round(total * 0.30))        # 满分 30
        stable = total - tech - exp - fit     # 满分 15
    else:
        tech, exp, fit, stable = 24, 20, 24, 10   # 和为 78，与 total 无关

    with io.open(os.path.join(d, "解析卡.md"), "w", encoding="utf-8") as f:
        f.write("## 基本信息\n\n")
        if company:
            f.write("公司: %s\n" % company)
        if role:
            f.write("岗位: %s\n" % role)
        f.write("\n## 评分\n\n技术匹配: %d/30\n经历匹配: %d/25\n"
                "方向契合: %d/30\n培养与稳定性: %d/15\n总分: %s\n"
                % (tech, exp, fit, stable, total))


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    """一个初始化过的工作区，且落在允许根之内。"""
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    target = os.path.join(str(tmp_path), "personal")
    os.makedirs(os.path.join(target, "config"))
    with io.open(os.path.join(target, "config", "profile.md"), "w", encoding="utf-8") as f:
        f.write("# 档案\n\n示例档案。\n")
    return target


@pytest.fixture()
def seeded(ws):
    _write_tracker(ws, [
        # 流程中：3 天前投递，2 天后有下一步，5 天后截止 → 进 upcoming，不 stale
        _row(id="1", 公司="示例科技", 岗位="后端开发工程师", 当前阶段="一面",
             投递日期=(TODAY - timedelta(days=3)).isoformat(),
             下次动作="准备二面", 下次动作日期=(TODAY + timedelta(days=2)).isoformat(),
             截止日期=(TODAY + timedelta(days=5)).isoformat(),
             方向="backend", 批次="正式批"),
        # 待投且已过截止 → urgent（进 pending）且进 overdue
        _row(id="2", 公司="云帆智算", 岗位="数据平台开发工程师", 当前阶段="待投",
             截止日期=(TODAY - timedelta(days=1)).isoformat(),
             方向="data", 批次="提前批"),
        # 终态：不参与 active / upcoming / overdue / stale / pending
        _row(id="3", 公司="旧识网络", 岗位="前端工程师", 当前阶段="已挂",
             状态原因="简历未过", 方向="frontend", 批次="正式批"),
    ])
    _write_job(ws, "示例科技_后端开发工程师")          # 无「基本信息」→ 目录切分
    _write_job(ws, "星海智能_算法工程师", company="星海智能", role="算法工程师", total=52)
    _write_job(ws, "_模板_解析卡")                    # 下划线开头：模板，必须跳过
    return ws


# --- list_applications -------------------------------------------------------

def test_list_applications_orders_and_counts(seeded):
    data = tools_readonly.list_applications(seeded)
    assert data["total"] == 3 and data["returned"] == 3
    ids = [i["id"] for i in data["items"]]
    assert ids[0] == "1"        # 非终态在前（按下次动作日期）
    assert ids[-1] == "3"       # 终态沉底
    assert "备注" not in data["items"][0]   # 默认精简字段


def test_list_applications_filters(seeded):
    assert tools_readonly.list_applications(seeded, stage="一面")["total"] == 1
    assert tools_readonly.list_applications(seeded, keyword="云帆")["total"] == 1
    assert tools_readonly.list_applications(seeded, keyword="后端")["total"] == 1
    # 三条记录的岗位都带「工程师」：关键词是子串包含，不是精确匹配
    assert tools_readonly.list_applications(seeded, keyword="工程师")["total"] == 3
    assert tools_readonly.list_applications(seeded, limit=1)["returned"] == 1


def test_list_applications_verbose_gives_all_fields(seeded):
    data = tools_readonly.list_applications(seeded, limit=1, verbose=True)
    assert set(data["items"][0]) == set(tracker.FIELDS)


# --- list_jobs ---------------------------------------------------------------

def test_list_jobs_state_and_score(seeded):
    data = tools_readonly.list_jobs(seeded)
    assert data["total"] == 2, "下划线开头的模板目录必须被跳过"
    by_company = dict((i["公司"], i) for i in data["items"])

    first = by_company["示例科技"]
    assert first["岗位"] == "后端开发工程师"      # 回退到目录名切分
    assert first["状态"] == "流程中"              # 与 id=1 按 dedup_key 匹配上
    assert first["有JD原文"] is True and first["有解析卡"] is True

    second = by_company["星海智能"]
    assert second["状态"] == "未投递"                     # 卡片「基本信息」优先
    assert second["评分"]["total"] == 52
    assert second["评分"]["level"] == "斟酌"              # 52 落在 45–59 档


def test_list_jobs_keyword(seeded):
    data = tools_readonly.list_jobs(seeded, keyword="算法")
    assert data["total"] == 1 and data["items"][0]["公司"] == "星海智能"


# --- dashboard_summary -------------------------------------------------------

def test_dashboard_summary_matches_backend_semantics(seeded):
    data = tools_readonly.dashboard_summary(seeded, today=TODAY)
    assert data["total"] == 3
    assert data["active"] == 2
    assert data["initialized"] is True
    assert [u["id"] for u in data["upcoming"]] == ["1"], "下次动作日期优先于截止日期"
    assert [o["id"] for o in data["overdue"]] == ["2"], "仅「待投」且已过截止算逾期"
    assert [s["id"] for s in data["stale"]] == [], "只停留 3 天，未达 14 天阈值"
    assert [p["id"] for p in data["pending"]] == ["2"], "已过截止仍未投 = urgent"
    assert data["funnel"][0] == {"stage": "待投", "count": 1}
    assert isinstance(data["conversion"], list) and data["conversion"]


# --- 工作区解析（安全边界） --------------------------------------------------

def test_resolve_workspace_default_and_env(ws, monkeypatch):
    assert paths.resolve_workspace() == ws
    monkeypatch.setenv("JOBWS_WORKSPACE", "personal")
    assert paths.resolve_workspace() == ws


def test_resolve_workspace_rejects_path_outside(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    with pytest.raises(paths.WorkspaceError) as exc:
        paths.resolve_workspace(os.path.abspath(os.sep))
    assert "越出允许范围" in str(exc.value)


def test_resolve_workspace_must_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    with pytest.raises(paths.WorkspaceError) as exc:
        paths.resolve_workspace("no-such-workspace", must_exist=True)
    assert "工作区不存在" in str(exc.value)


def test_workspace_profile_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    plain = os.path.join(str(tmp_path), "plain")
    os.makedirs(plain)
    assert paths.workspace_profile(plain) is False


def test_list_jobs_matches_by_dir_name_not_card(tmp_path, monkeypatch):
    """匹配键只用目录名：卡片里的公司名更详细时也要认出「已投递」。

    后端 jobs.py:196-209 明确写了这条（卡片值只用于展示）。拿卡片名当键的话，
    真实数据里会把已投岗位成片判成未投递。
    """
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    ws = os.path.join(str(tmp_path), "personal")
    _write_tracker(ws, [_row(id="1", 公司="示例科技", 岗位="后端开发工程师",
                             当前阶段="一面")])
    _write_job(ws, "示例科技_后端开发工程师",
               company="示例科技（集团）", role="后端开发工程师（社招）")
    item = tools_readonly.list_jobs(ws)["items"][0]
    assert item["状态"] == "流程中", "按目录名匹配才认得出已投递"
    assert item["公司"] == "示例科技（集团）", "展示名仍取卡片"


def test_list_jobs_keeps_active_row_when_same_key_repeats(tmp_path, monkeypatch):
    """同键多行（挂了再投一次）：保留仍在流程中的那行。

    否则同一岗位在网页端显示「流程中」、在 MCP 侧却报「已终态」——
    同键同名两种结论，正是这批要避免的事。
    """
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    ws = os.path.join(str(tmp_path), "personal")
    _write_tracker(ws, [
        _row(id="1", 公司="示例科技", 岗位="后端开发工程师", 当前阶段="已挂"),
        _row(id="2", 公司="示例科技", 岗位="后端开发工程师", 当前阶段="二面"),
    ])
    _write_job(ws, "示例科技_后端开发工程师")
    assert tools_readonly.list_jobs(ws)["items"][0]["状态"] == "流程中"


def test_resolve_workspace_rejects_relative_escape(tmp_path, monkeypatch):
    """相对路径往上逃也要拦住（宿主可能由模型代传 `../..` 这类参数）。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    with pytest.raises(paths.WorkspaceError):
        paths.resolve_workspace(os.path.join("..", "outside"))


def test_card_score_flags_inconsistent_card(tmp_path, monkeypatch):
    """四维之和与总分不符：总分照给，但不给档位（与后端 `_parse_card` 同口径）。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))
    ws = os.path.join(str(tmp_path), "personal")
    _write_job(ws, "星海智能_算法工程师", company="星海智能", role="算法工程师",
               total=52, consistent=False)
    score = tools_readonly.list_jobs(ws)["items"][0]["评分"]
    assert score["total"] == 52
    assert score["consistent"] is False and score["level"] is None
