# -*- coding: utf-8 -*-
"""岗位池 ↔ 追踪表联动（B1）的回归。

覆盖三件事，按重要性排序：

1. **口径只有一处**：(公司, 岗位) 的规范化键必须是同一份实现，否则会出现
   「去重说你已经投过、岗位池说你没投过」这种自相矛盾的结论。
2. **目录名还原是可预测的**：`_dir_name` 与 `_split_dir` 互为逆运算；公司名自带
   下划线时按首个下划线切分（可能偏左），这条分支要钉住，防止有人悄悄改成
   「看起来更聪明」的猜测逻辑。
3. **三态与终态口径跟着 tracker 走**：这里不另立一份终态清单。

排序与容错策略与 applications.py 保持一致（未知 sort/status 静默回退），
因此也对默认行为设了断言。
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
import routers.jobs as jobs_router  # noqa: E402
import tracker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
JOBS_DIR = "01_岗位池"
TRACKING_DIR = "05_投递追踪"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把应用根指到临时目录——不依赖仓库里真实的 `personal/`（CI 上它不存在）。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    # APPDATA 也要隔离：快照目录走系统用户目录，不隔离会读到开发机上的真实快照
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （ROOT 改写之后再导入，避免读到真实仓库根）
    return TestClient(main.app)


def _make_job(tmp_path, name, card_text=None):
    """在工作区里造一个岗位目录；card_text 非空时一并写入解析卡。"""
    d = tmp_path / WS / JOBS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "JD原文.md").write_text("JD 正文", encoding="utf-8")
    if card_text is not None:
        (d / "解析卡.md").write_text(card_text, encoding="utf-8")
    return d


def _make_tracking(tmp_path, rows):
    """写 tracker.csv。缺列一律留空，与真实主表的读取方式一致。"""
    path = tmp_path / WS / TRACKING_DIR
    path.mkdir(parents=True, exist_ok=True)
    with io.open(str(path / "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for row in rows:
            full = {field: "" for field in tracker.FIELDS}
            full.update(row)
            writer.writerow(full)


def _basic_info_card(company, role):
    """带「基本信息」的解析卡：这里填的公司/岗位优先于目录名。"""
    return ("# 解析卡\n\n## 基本信息\n公司: %s\n岗位: %s\n方向: hvac\n批次: 正式批\n\n"
            "## 硬门槛\n学历: pass\n" % (company, role))


def _items(client, **params):
    return client.get("/api/jobs", params=dict({"ws": WS}, **params)).json()["items"]


# --- 目录名还原与规范化键 ----------------------------------------------------

def test_split_dir_reverses_dir_name():
    assert jobs_router._split_dir("某科技公司_暖通研发") == ("某科技公司", "暖通研发")
    # 与 _dir_name 互为逆运算（创建侧已把首尾空格裁掉）；期望写字面量，别用实现推实现
    assert jobs_router._split_dir(jobs_router._dir_name("  某科技公司 ", " 暖通研发 ")) == (
        "某科技公司", "暖通研发")


def test_split_dir_takes_first_underscore():
    # 公司名自带下划线时会还原偏左——刻意选的可预测口径，不是可以「优化」的 bug
    assert jobs_router._split_dir("A_B_C") == ("A", "B_C")
    # 完全没有下划线时岗位为空，匹配键不成立 → 显示为「未投递」
    assert jobs_router._split_dir("单独一段") == ("单独一段", "")


def test_dedup_key_is_trim_and_case_insensitive():
    rows = [{"id": "A001", "公司": "ACME", "岗位": "Engineer", "当前阶段": "一面"}]
    dup, terminal = tracker.find_duplicate(rows, "  acme ", " ENGINEER ")
    assert dup is not None and dup["id"] == "A001"
    assert terminal is False
    # 中间的空格不是「格式差异」，是两个不同的岗位
    assert tracker.find_duplicate(rows, "ACME", "Engineer II")[0] is None


def test_card_basic_info_wins_over_dir_name(client, tmp_path):
    """目录名可能被文件系统限制改过；卡片里填的才是给用户看的真值。"""
    _make_job(tmp_path, "已被改坏的名字_看不出公司",
              card_text=_basic_info_card("真公司", "真岗位"))
    item = _items(client)[0]
    assert item["company"] == "真公司"
    assert item["role"] == "真岗位"


def test_falls_back_to_dir_name_when_card_has_no_basic_info(client, tmp_path):
    _make_job(tmp_path, "某公司_某岗位", card_text="# 解析卡\n\n## 评分\n")
    item = _items(client)[0]
    assert (item["company"], item["role"]) == ("某公司", "某岗位")


def test_matching_uses_dir_name_even_when_card_differs(client, tmp_path):
    """真实数据的形态：目录名 / 追踪表用短名，卡片「基本信息」是给人看的详细名。

    匹配键必须取目录名（与追踪表同源），卡片值只用于展示——否则会出现
    「明明投过、去重也认，岗位池却显示未投递」的自相矛盾。
    """
    _make_job(tmp_path, "TCL空调事业部_性能工程师",
              card_text=_basic_info_card("TCL（空调事业部）", "性能工程师"))
    _make_tracking(tmp_path, [{"id": "A001", "公司": "TCL空调事业部",
                               "岗位": "性能工程师", "当前阶段": "一面"}])
    item = _items(client)[0]
    assert item["applyState"] == "流程中"
    assert item["applicationId"] == "A001"
    # 展示名仍取卡片真值
    assert item["company"] == "TCL（空调事业部）"


# --- 关联与三态 --------------------------------------------------------------

def test_linking_matches_by_normalized_key(client, tmp_path):
    """大小写与首尾空格的差异必须照样命中——两份实现各自 trim 迟早漂移。"""
    _make_job(tmp_path, "ACME_Engineer")
    _make_tracking(tmp_path, [{"id": "A001", "公司": "  acme ", "岗位": "ENGINEER",
                               "当前阶段": "一面"}])
    item = _items(client)[0]
    assert item["applyState"] == "流程中"
    assert item["stage"] == "一面"
    assert item["applicationId"] == "A001"


def test_state_covers_three_states_including_all_terminal_stages(client, tmp_path):
    _make_job(tmp_path, "A_甲")
    _make_job(tmp_path, "B_乙")
    _make_job(tmp_path, "C_丙")
    _make_job(tmp_path, "D_丁")
    _make_tracking(tmp_path, [
        {"id": "A001", "公司": "A", "岗位": "甲", "当前阶段": "一面"},
        # 「我拒绝的 offer」是双向选择，但在这里同样算终态——口径跟 tracker 走
        {"id": "A002", "公司": "B", "岗位": "乙", "当前阶段": "我拒绝的 offer"},
        {"id": "A003", "公司": "D", "岗位": "丁", "当前阶段": "已挂"},
    ])
    items = {i["dir"]: i for i in _items(client)}
    assert items["A_甲"]["applyState"] == "流程中"
    assert items["B_乙"]["applyState"] == "已终态"
    assert items["D_丁"]["applyState"] == "已终态"
    # 没有任何记录 → 未投递，且不伪造 id
    assert items["C_丙"]["applyState"] == "未投递"
    assert items["C_丙"]["applicationId"] is None


def test_job_detail_carries_the_same_state_as_the_list(client, tmp_path):
    """详情与列表不能说两套话：单条查询不传索引时要就地建，而不是默认「未投递」。"""
    _make_job(tmp_path, "ACME_Engineer")
    _make_tracking(tmp_path, [{"id": "A001", "公司": "ACME", "岗位": "Engineer",
                               "当前阶段": "已挂"}])
    detail = client.get("/api/jobs/ACME_Engineer", params={"ws": WS}).json()
    assert detail["applyState"] == "已终态"
    assert detail["applicationId"] == "A001"


def test_missing_tracking_dir_means_unapplied(client, tmp_path):
    """刚初始化的工作区还没有追踪表：不算异常，全部显示「未投递」。"""
    _make_job(tmp_path, "A_甲")
    assert [i["applyState"] for i in _items(client)] == ["未投递"]


def test_status_filter(client, tmp_path):
    _make_job(tmp_path, "A_甲")
    _make_job(tmp_path, "B_乙")
    _make_job(tmp_path, "C_丙")
    _make_tracking(tmp_path, [
        {"id": "A001", "公司": "A", "岗位": "甲", "当前阶段": "一面"},
        {"id": "A002", "公司": "B", "岗位": "乙", "当前阶段": "已挂"},
    ])
    assert [i["dir"] for i in _items(client, status="active")] == ["A_甲"]
    assert [i["dir"] for i in _items(client, status="terminal")] == ["B_乙"]
    assert [i["dir"] for i in _items(client, status="unapplied")] == ["C_丙"]


def test_duplicate_rows_prefer_the_active_one(client, tmp_path):
    """「挂了再投一次」是同键两行的合法场景：终态行不得盖住仍在流程中的行。"""
    _make_job(tmp_path, "ACME_Engineer")
    _make_tracking(tmp_path, [
        {"id": "A001", "公司": "ACME", "岗位": "Engineer", "当前阶段": "已挂"},
        {"id": "A002", "公司": "ACME", "岗位": "Engineer", "当前阶段": "一面"},
    ])
    item = _items(client)[0]
    assert item["applicationId"] == "A002"
    assert item["stage"] == "一面"
    # 顺序颠倒（活跃行在前、终态行在后）也一样：后到的终态行不得覆盖
    _make_tracking(tmp_path, [
        {"id": "A001", "公司": "ACME", "岗位": "Engineer", "当前阶段": "一面"},
        {"id": "A002", "公司": "ACME", "岗位": "Engineer", "当前阶段": "已挂"},
    ])
    item = _items(client)[0]
    assert item["applicationId"] == "A001"
    assert item["stage"] == "一面"


def test_status_filter_composes_with_sort(client, tmp_path):
    """先筛选后排序的组合路径（任务书点名的覆盖缺口）。"""
    _make_job(tmp_path, "D_丁")
    _make_job(tmp_path, "C_丙")
    _make_job(tmp_path, "B_乙")
    _make_job(tmp_path, "A_甲")
    _make_tracking(tmp_path, [
        {"id": "A001", "公司": "A", "岗位": "甲", "当前阶段": "一面"},
        {"id": "A002", "公司": "B", "岗位": "乙", "当前阶段": "已挂"},
    ])
    assert [i["dir"] for i in _items(client, status="unapplied", sort="dir")] == ["C_丙", "D_丁"]
    # 未评分在 score 排序里沉底并列，按目录名决胜
    assert [i["dir"] for i in _items(client, status="unapplied", sort="score")] == ["C_丙", "D_丁"]
    assert [i["dir"] for i in _items(client, status="terminal", sort="recent")] == ["B_乙"]


def test_unknown_sort_and_status_fall_back_silently(client, tmp_path):
    """前端传参可能来自 URL：未知值回退默认，而不是 400（与 applications 同策略）。"""
    _make_job(tmp_path, "B_乙")
    _make_job(tmp_path, "A_甲")
    assert [i["dir"] for i in _items(client)] == ["A_甲", "B_乙"]
    assert [i["dir"] for i in _items(client, sort="nope", status="nope")] == ["A_甲", "B_乙"]


# --- 四排序 ------------------------------------------------------------------

def _stub(dirname, score=None, state="未投递", mtime=1):
    return {"dir": dirname, "score": score, "applyState": state, "mtime": mtime}


def test_sort_dir_and_unknown_key():
    items = [_stub("b"), _stub("a"), _stub("c")]
    assert [i["dir"] for i in jobs_router._sort_jobs(items, "dir")] == ["a", "b", "c"]
    assert [i["dir"] for i in jobs_router._sort_jobs(items, "不存在的键")] == ["a", "b", "c"]


def test_sort_score_puts_unscored_last():
    items = [_stub("无分数"), _stub("高分", 95), _stub("低分", 60)]
    assert [i["dir"] for i in jobs_router._sort_jobs(items, "score")] == ["高分", "低分", "无分数"]


def test_sort_state_orders_state_then_score():
    items = [_stub("终态高分", 99, "已终态"), _stub("未投低分", 10, "未投递"),
             _stub("流程中", 50, "流程中"),
             _stub("未投高分", 88, "未投递"), _stub("未投无分", None, "未投递")]
    # 二级键也要有断言：同状态内评分降序、未评分沉底，不能三种状态各一条就算测过
    assert [i["dir"] for i in jobs_router._sort_jobs(items, "state")] == [
        "未投高分", "未投低分", "未投无分", "流程中", "终态高分"]


def test_sort_recent_puts_undated_last():
    items = [_stub("旧", mtime=100), _stub("新", mtime=300), _stub("无时间", mtime=None)]
    assert [i["dir"] for i in jobs_router._sort_jobs(items, "recent")] == ["新", "旧", "无时间"]


# --- 一键投递的写入（B2）-----------------------------------------------------

def _apply(client, **body):
    payload = {"公司": "A公司", "岗位": "甲岗位", "方向": "other", "批次": "正式批"}
    payload.update(body)
    return client.post("/api/applications", params={"ws": WS}, json=payload)


def _written_rows(tmp_path):
    path = tmp_path / WS / TRACKING_DIR / "tracker.csv"
    with io.open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_apply_from_job_pool_is_matched_back_by_dir_name(client, tmp_path):
    """一键投递写进去的记录，必须能被岗位池的匹配逻辑命中。

    写入值与匹配键都取目录名拆分（`_split_dir`），两边同源；写卡片展示名会导致
    「投过了却显示未投递」——这是 B1 独立审查抓出的真问题，此处钉住闭环。
    """
    _make_job(tmp_path, "A公司_甲岗位")
    r = _apply(client)
    assert r.status_code == 200, r.text
    item = _items(client)[0]
    assert item["applyState"] == "流程中"
    assert item["applicationId"] == r.json()["id"]


def test_apply_without_score_leaves_score_blank(client, tmp_path):
    """未评分不写 0：0 分是一个具体判断，「还没评分」不是。"""
    _make_job(tmp_path, "A公司_甲岗位")
    assert _apply(client).status_code == 200
    assert _written_rows(tmp_path)[0]["评分"] == ""


def test_apply_with_score_rounds_to_int(client, tmp_path):
    """解析卡允许小数维度分（如 24.5/30 → 87.5），追踪表这一列是整数。"""
    _make_job(tmp_path, "A公司_甲岗位")
    assert _apply(client, 评分=88).status_code == 200
    assert _written_rows(tmp_path)[0]["评分"] == "88"
