# -*- coding: utf-8 -*-
"""筛选校准（E 批）：契约测试，先红后绿。

对应设计文档 `docs/specs/2026-10-15-score-calibration-design.md` §八 六条判据里
**核心层能独立证明的五条**（四端同源那条在 `test_score_calibration_ends.py`）：

1. 分母口径：同档位 1 投 + 2 未投 → 分母是 1（不是 3）；
2. 未评分不入档：不出现在 ① 的任何档里，但出现在 ② 的构成里；
3. 样本下限：某档投递数 < MIN_CLUSTER_SAMPLES → shown=false + noteCode，且**不输出百分比**；
4. 反目标：调用本特性**不产生任何写请求**（整个工作树逐字节不变）；
6. 匹配键说明：输出携带「首个下划线切分」的已知取舍说明。

另钉两条设计文档的硬约束：结论句一律「数据显示 + 可能」（不写祈使句），
两套评分互不校验的说明必须在输出里。
"""

import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"),
           os.path.join(ROOT_DIR, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from jobws_core import jd_score, job_pool, report, score_calibration  # noqa: E402
from jobws_core.tracker import dedup_key  # noqa: E402

WS = "personal"
TIER_HIGH = "强烈建议投"      # THRESHOLDS[0]
TIER_MID = "斟酌"             # THRESHOLDS[2]
MIN = report.MIN_CLUSTER_SAMPLES


def _row(rid, company, score, stage="已投"):
    """一条追踪表行（最小字段集：本特性只读 评分/公司/岗位/当前阶段）。"""
    return {"id": rid, "公司": company, "岗位": "后端", "当前阶段": stage,
            "评分": "" if score is None else str(score)}


def _pool_entry(name, score, gate, applied):
    company, role = name.split("_", 1)
    return {"dir": name, "company": company, "role": role,
            "displayCompany": company, "displayRole": role,
            "score": score, "level": jd_score.verdict(score)[0] if score is not None else None,
            "consistent": score is not None, "gate": gate, "applied": applied}


def _tiers(result):
    return {t["tier"]: t for t in result["tiers"]}


# --- 判据 1：分母 = 该档位里「投过」的岗位数 --------------------------------------

def test_denominator_counts_only_applied_jobs():
    """同档位 3 个岗位：1 个有追踪行（投过）、2 个只在岗位池（没投）。

    分母必须是 1——把没投的算进去，等于把「我筛掉了它」混进「它转化好不好」。
    """
    rows = [_row("A001", "已投科技", 80)]
    pool = [
        _pool_entry("已投科技_后端", 80, "通过", True),
        _pool_entry("没投甲_后端", 82, "通过", False),
        _pool_entry("没投乙_后端", 78, "通过", False),
    ]

    out = score_calibration.calibrate(rows, pool, [], None, WS)

    assert _tiers(out)[TIER_HIGH]["applied"] == 1


def test_unapplied_jobs_never_enter_the_conversion_chain():
    """没投的岗位不进 ① 的链路：它们没有结局可谈（② 才回答它们的规模）。"""
    rows = [_row("A%03d" % i, "已投科技%d" % i, 80, stage="已投")
            for i in range(MIN)]
    pool = ([_pool_entry("已投科技%d_后端" % i, 80, "通过", True)
             for i in range(MIN)]
            + [_pool_entry("没投甲_后端", 80, "通过", False)])

    out = score_calibration.calibrate(rows, pool, [], None, WS)

    reached = {c["stage"]: c["reached"]
               for c in _tiers(out)[TIER_HIGH]["conversion"]}
    assert reached.get("已投") == MIN, "没投的岗位被算进转化链路了"


# --- 判据 2：未评分不入档，但进 ② 的构成 ----------------------------------------

def test_unscored_jobs_join_no_tier_but_are_counted_in_unapplied():
    """未评分 = 空评分列。它不该被塞进任何档（「还没评」不等于最低档），
    但在 ② 的构成里必须露面——否则「窄」的代价被藏起来。"""
    rows = [_row("A%03d" % i, "已投科技%d" % i, 80) for i in range(MIN)]
    rows.append(_row("U001", "未评分科技", None, stage="已投"))   # 空评分的 tracker 行
    pool = ([_pool_entry("已投科技%d_后端" % i, 80, "通过", True)
             for i in range(MIN)]
            + [_pool_entry("没评分_后端", None, "通过", False)])

    out = score_calibration.calibrate(rows, pool, [], None, WS)

    # ① 的总人口 = 投过且已评分的行数；未评分行（tracker 或岗位池）不占任何档位
    assert sum(t["applied"] for t in out["tiers"]) == MIN, "未评分行进档了"
    assert _tiers(out)[TIER_HIGH]["applied"] == MIN
    assert out["unapplied"]["unscored"] == 1
    assert out["unapplied"]["total"] == 1


# --- 判据 3：样本下限——不硬凑数字，且不输出百分比 --------------------------------

def test_tier_below_sample_floor_is_hidden_and_carries_note_code():
    """投递数 < MIN_CLUSTER_SAMPLES：shown=false + noteCode + 不输出百分比。"""
    rows = [_row("A%03d" % i, "公司%d" % i, 80) for i in range(MIN - 1)]
    pool = [_pool_entry("公司%d_后端" % i, 80, "通过", True) for i in range(MIN - 1)]

    out = score_calibration.calibrate(rows, pool, [], None, WS)
    tier = _tiers(out)[TIER_HIGH]

    assert tier["applied"] == MIN - 1
    assert tier["shown"] is False
    assert tier["noteCode"] == "too_few_samples"
    assert tier["noteParams"] == {"total": MIN - 1, "min": MIN}
    assert tier["conversion"] == [], "样本不足还不肯空手，等于拿噪声当趋势"


def test_tier_at_sample_floor_shows_rates():
    rows = [_row("A%03d" % i, "公司%d" % i, 80) for i in range(MIN)]
    pool = [_pool_entry("公司%d_后端" % i, 80, "通过", True) for i in range(MIN)]

    out = score_calibration.calibrate(rows, pool, [], None, WS)
    tier = _tiers(out)[TIER_HIGH]

    assert tier["shown"] is True
    assert tier["noteCode"] is None
    assert any(c["rate"] is not None for c in tier["conversion"])


# --- 反目标：一句结论不许写成祈使句 ----------------------------------------------

def test_conclusion_never_reads_as_an_instruction():
    """结论句只能是「数据显示 + 可能」；出现「应该 / 建议你 / 必须」即越界
    （设计文档 §四.2：替用户下判断就是越界）。"""
    rows = [_row("A%03d" % i, "高分%d" % i, 80, stage="offer") for i in range(MIN)]
    rows += [_row("B%03d" % i, "低分%d" % i, 50, stage="已挂") for i in range(MIN)]
    pool = ([_pool_entry("高分%d_后端" % i, 80, "通过", True) for i in range(MIN)]
            + [_pool_entry("低分%d_后端" % i, 50, "通过", True) for i in range(MIN)])

    out = score_calibration.calibrate(rows, pool, [], None, WS)
    text = out["conclusion"]["text"]

    for banned in ("应该", "建议你", "必须", "快去", "赶紧", "务必"):
        assert banned not in text, text
    assert ("数据显示" in text) or ("样本不足" in text), text


def test_conclusion_admits_when_samples_are_too_thin():
    """可比较档位不足两个时，结论必须是「样本不足」而不是硬编一句话。"""
    rows = [_row("A001", "只有一个档", 80)]
    pool = [_pool_entry("只有一个档_后端", 80, "通过", True)]

    out = score_calibration.calibrate(rows, pool, [], None, WS)

    assert "样本不足" in out["conclusion"]["text"]
    assert out["conclusion"]["basis"] == []


# --- 判据 6：已知取舍必须写进输出 ------------------------------------------------

def test_output_carries_the_underscore_tradeoff_note():
    """匹配键 = 目录名首个下划线拆分；公司名自带下划线会误判「未投递」——
    这条已知取舍必须随输出给出，不能装作精确。"""
    rows = []
    pool = [_pool_entry("甲_乙_后端", 70, "通过", False)]

    out = score_calibration.calibrate(rows, pool, [], None, WS)

    notes = "\n".join(out["notes"])
    assert "下划线" in notes, notes


def test_output_carries_the_two_score_sources_note():
    """追踪表「评分」列与解析卡总分各自独立填写——按追踪表列 join 这件事
    必须说明，否则用户会以为两边是同一份数。"""
    out = score_calibration.calibrate([], [], [], None, WS)
    notes = "\n".join(out["notes"])

    assert "解析卡" in notes and "追踪表" in notes, notes


# --- 判据 4：反目标——整个工作树逐字节不变 --------------------------------------

def _make_workspace(tmp_path):
    ws = tmp_path / WS
    (ws / "01_岗位池" / "已投科技_后端").mkdir(parents=True)
    (ws / "01_岗位池" / "没投甲_后端").mkdir(parents=True)
    (ws / "01_岗位池" / "没评分_后端").mkdir(parents=True)
    (ws / "05_投递追踪").mkdir(parents=True)
    # 维度名/满分/取值格式照 `jd_score`（`分子/满分`，如 `24/30`）；
    # 加权和必须等于总分，否则卡片不一致（consistent=False → 不计分）
    card = """## 基本信息
公司: 已投科技
岗位: 后端

## 评分
技术匹配: 24/30
经历匹配: 20/25
方向契合: 24/30
培养与稳定性: 12/15
总分: 80

## 硬门槛
门槛结论: 通过
"""
    for name in ("已投科技_后端", "没投甲_后端"):
        with io.open(str(ws / "01_岗位池" / name / "解析卡.md"), "w", encoding="utf-8") as fh:
            fh.write(card)
    tracker = ("id,公司,岗位,当前阶段,评分\n"
               "A001,已投科技,后端,已投,80\n")
    with io.open(str(ws / "05_投递追踪" / "tracker.csv"), "w", encoding="utf-8-sig") as fh:
        fh.write(tracker)
    return ws


def _snapshot(root):
    out = {}
    for base, _dirs, files in os.walk(str(root)):
        for fn in files:
            full = os.path.join(base, fn)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, str(root))] = fh.read()
    return out


def test_calibration_writes_nothing(tmp_path, monkeypatch):
    """反目标（设计文档 §八.4）：本特性是只读的——不写配置、不写 tracker、
    不生成投递动作。用整个工作树逐字节快照钉死，比 mock 写口更硬。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    ws = _make_workspace(tmp_path)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))

    before = _snapshot(tmp_path)

    pool = job_pool.load_job_pool(str(ws))
    from jobws_core import tracker
    rows = tracker.read_rows(str(ws))
    out = score_calibration.calibrate(rows, pool, [], None, str(ws))

    assert out["tiers"], "空输入不该让整件事静默失败"
    assert _snapshot(tmp_path) == before, "本特性写了工作区"


# --- load_job_pool：一次读取、口径与既有实现同源 --------------------------------

def test_load_job_pool_reads_each_card_once(tmp_path, monkeypatch):
    """每张解析卡只读一次（看板同请求两处消费，读放大由 test_read_amplification 守）。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    ws = _make_workspace(tmp_path)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))

    reads = []
    real_open = io.open

    def counting_open(path, *a, **kw):
        if str(path).endswith("解析卡.md"):
            reads.append(str(path))
        return real_open(path, *a, **kw)

    monkeypatch.setattr(io, "open", counting_open)
    pool = job_pool.load_job_pool(str(ws))

    assert len(pool) == 3
    # 读放大判据：每个目录的解析卡**只读一次**（三个目录各一次尝试；
    # 没建卡的目录读不到属正常，重复读同一路径才算放大）
    assert len(reads) == len(set(reads)) == 3, reads


def test_load_job_pool_marks_applied_by_dir_name_key(tmp_path, monkeypatch):
    """applied 的匹配键 = 目录名首个下划线拆分（与追踪表同源）；
    公司名自带下划线时会误判——这条已知取舍由 notes 说明，不由代码装作精确。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    ws = _make_workspace(tmp_path)
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))

    pool = {p["dir"]: p for p in job_pool.load_job_pool(str(ws))}

    assert pool["已投科技_后端"]["applied"] is True
    assert pool["没投甲_后端"]["applied"] is False
    assert pool["已投科技_后端"]["company"] == "已投科技"
    assert pool["已投科技_后端"]["role"] == "后端"
    assert pool["已投科技_后端"]["score"] == 80.0
    assert pool["已投科技_后端"]["gate"] == "通过"
    assert pool["没评分_后端"]["score"] is None
