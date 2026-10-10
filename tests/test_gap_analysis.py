# -*- coding: utf-8 -*-
"""JD↔简历差距链路的测试网（2026-10-08 审计 1.2：核心函数与消费端零覆盖）。

链路逐段钉住：

1. **核心** `jd_score.gap_analysis`——三分组的判定依据（JD 提到才有资格；
   简历里有 = matched；简历没有但主版/事实库里有 = injectable（可召回不造假）；
   两处都没有 = missing 真缺口）、词典内去重（首次出现分层生效）、
   英文大小写不敏感、缺输入的**错误口径**（返回 `(None, errors)` 而不是抛）；
2. **后端端点** `GET /api/jobs/{id}/gap`——缺省取简历工坊「最新版本」（文件名序
   末位）、显式 `resume` 优先且能改变结果、404/404/422 三种拒绝码；
3. **MCP 端**在同批的 `mcp/tests/test_tools_batch47.py`（score_jd 差距分支）。
"""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "packages", "jobws-core", "src"))

import deps  # noqa: E402
from jobws_core import jd_score  # noqa: E402

JOB = "云帆_后端"
JD_TEXT = "# 云帆 后端\n\n要求 Python、Kubernetes、ClickHouse、Docker 经验。\n"
LEXICON = ("## Primary（3 分/项）\n\nPython、Kubernetes\n"
           "## Secondary（2 分/项）\n\nClickHouse\n"
           "## Weak（1 分/项）\n\nDocker、Python\n")     # Python 重复：验证去重


def _mk_ws(tmp_path, jd=True, resume=True, lexicon=True, master=True, profile=True):
    """铺一个可供差距分析的最小工作区；返回 (workspace, job_dir)。"""
    ws = tmp_path / "personal"
    job = ws / "01_岗位池" / JOB
    job.mkdir(parents=True)
    if jd:
        (job / "JD原文.md").write_text(JD_TEXT, encoding="utf-8")

    cfg = ws / "config"
    cfg.mkdir()
    if profile:
        (cfg / "profile.md").write_text("# 档案\n", encoding="utf-8")
    if lexicon:
        (cfg / "lexicon.md").write_text(LEXICON, encoding="utf-8")
    directions = cfg / "directions"
    directions.mkdir()
    (directions / "datacenter.md").write_text("# 方向：数据中心\n", encoding="utf-8")

    src = ws / "02_简历工坊" / "source"
    src.mkdir(parents=True)
    if resume:
        (src / "resume_hvac.json").write_text(
            json.dumps({"技能": ["Python"], "项目": [{"描述": "微服务"}]},
                       ensure_ascii=False), encoding="utf-8")
    if master:
        (ws / "02_简历工坊" / "简历_主版_v1.0.md").write_text(
            "# 主版\n\nKubernetes 集群运维。\n", encoding="utf-8")
    return str(ws), str(job)


def _analyze(ws, job, version="hvac"):
    return jd_score.gap_analysis(ws, os.path.join(job, "解析卡.md"), version)


# --- 核心：三分组 -------------------------------------------------------------

def test_gap_groups_three_ways_by_evidence(tmp_path):
    """matched / injectable / missing 各自的证据判据——这是「凭什么这么分」。"""
    ws, job = _mk_ws(tmp_path)
    result, errors = _analyze(ws, job)

    assert errors == [] and result is not None
    # 简历里有 = matched；主版里有 = 可召回（不构成编造）；两处都没有 = 真缺口
    assert [item["term"] for item in result["matched"]] == ["Python"]
    assert result["matched"][0]["level"] == "Primary"
    assert result["injectable"] == ["Kubernetes"]
    assert result["missing"] == ["ClickHouse", "Docker"]
    assert result["counts"] == {"matched": 1, "injectable": 1, "missing": 2}
    # 来源路径全部是工作区内的相对 POSIX 路径（前端直接展示）
    assert result["jd"] == "01_岗位池/%s/JD原文.md" % JOB
    assert result["resume"] == "source/resume_hvac.json"
    assert result["lexicon"] == "config/lexicon.md"
    # detail 组与扁平组同源（前端用 detail 渲染层级标签）
    assert result["matchedDetail"] == result["matched"]
    assert result["injectableDetail"] == [{"term": "Kubernetes", "level": "Primary"}]


def test_gap_dedups_lexicon_terms(tmp_path):
    """词典里重复出现的词条只算一次，且以**首次出现**的分层为准（Primary 胜 Weak）。"""
    ws, job = _mk_ws(tmp_path)
    result, errors = _analyze(ws, job)

    assert errors == []
    terms = [item["term"] for item in result["matched"]]
    assert terms == ["Python"]                              # 不是出现两次
    assert result["matched"][0]["level"] == "Primary"


def test_gap_english_terms_are_case_insensitive(tmp_path):
    """EnergyPlus vs energyplus vs ENERGYPLUS：同一个词（`_contains` 统一小写）。"""
    ws, job = _mk_ws(tmp_path)
    job_dir = os.path.join(ws, "01_岗位池", JOB)
    with open(os.path.join(job_dir, "JD原文.md"), "w", encoding="utf-8") as fh:
        fh.write("# JD\n\n熟悉 energyplus 仿真。\n")
    with open(os.path.join(ws, "config", "lexicon.md"), "w", encoding="utf-8") as fh:
        fh.write("## Primary（3 分/项）\n\nEnergyPlus\n")
    with open(os.path.join(ws, "02_简历工坊", "source", "resume_hvac.json"),
              "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"技能": ["ENERGYPLUS"]}, ensure_ascii=False))

    result, errors = _analyze(ws, job_dir)

    assert errors == []
    assert [item["term"] for item in result["matched"]] == ["EnergyPlus"]


# --- 核心：错误口径（返回 (None, errors)，不抛） ------------------------------

def test_gap_missing_jd_reports_error(tmp_path):
    ws, job = _mk_ws(tmp_path, jd=False)
    result, errors = _analyze(ws, job)
    assert result is None
    assert any("JD 原文" in e for e in errors)


def test_gap_missing_resume_reports_error(tmp_path):
    ws, job = _mk_ws(tmp_path, resume=False)
    result, errors = _analyze(ws, job)
    assert result is None
    assert any("简历数据" in e for e in errors)


def test_gap_empty_lexicon_reports_error(tmp_path):
    ws, job = _mk_ws(tmp_path, lexicon=False)
    result, errors = _analyze(ws, job)
    assert result is None
    assert any("词典为空" in e for e in errors)


def test_gap_without_workspace_profile_surfaces_warning(tmp_path):
    """工作区没有档案、又未传 --domain：警告（修法提示）随 errors 一起回传——
    否则调用方只看到「词典为空」，不知道根因是档案缺失。"""
    ws, job = _mk_ws(tmp_path, profile=False, lexicon=False)
    result, errors = _analyze(ws, job)
    assert result is None
    assert any("词典为空" in e for e in errors)
    assert any("--domain" in e for e in errors)


# --- 端点：GET /api/jobs/{id}/gap --------------------------------------------

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _seed_endpoint_ws(tmp_path):
    """两个简历版本（a 缺 Kubernetes、b 全有）+ 一份最小词典。"""
    ws = tmp_path / WS
    job = ws / "01_岗位池" / JOB
    job.mkdir(parents=True)
    (job / "JD原文.md").write_text("# 云帆 后端\n\n要求 Python、Kubernetes 经验。\n",
                                   encoding="utf-8")
    cfg = ws / "config"
    cfg.mkdir()
    (cfg / "profile.md").write_text("# 档案\n", encoding="utf-8")
    (cfg / "lexicon.md").write_text("## Primary（3 分/项）\n\nPython、Kubernetes\n",
                                    encoding="utf-8")
    (cfg / "directions").mkdir()
    (cfg / "directions" / "datacenter.md").write_text("# 方向：数据中心\n", encoding="utf-8")
    src = ws / "02_简历工坊" / "source"
    src.mkdir(parents=True)
    (src / "resume_a.json").write_text(json.dumps({"技能": ["Python"]},
                                                  ensure_ascii=False), encoding="utf-8")
    (src / "resume_b.json").write_text(json.dumps({"技能": ["Python", "Kubernetes"]},
                                                  ensure_ascii=False), encoding="utf-8")


def test_gap_endpoint_defaults_to_last_resume_version(client, tmp_path):
    _seed_endpoint_ws(tmp_path)
    res = client.get("/api/jobs/%s/gap" % JOB, params={"ws": WS})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resumeVersion"] == "b"           # 文件名序末位 = 缺省「当前版」
    assert body["counts"] == {"matched": 2, "injectable": 0, "missing": 0}
    assert body["warnings"] == []


def test_gap_endpoint_explicit_resume_wins_and_changes_result(client, tmp_path):
    _seed_endpoint_ws(tmp_path)
    res = client.get("/api/jobs/%s/gap" % JOB, params={"ws": WS, "resume": "a"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resumeVersion"] == "a"
    assert body["counts"]["matched"] == 1
    assert body["missing"] == ["Kubernetes"]


def test_gap_endpoint_rejects_missing_job_and_missing_versions(client, tmp_path):
    _seed_endpoint_ws(tmp_path)

    res = client.get("/api/jobs/不存在_岗位/gap", params={"ws": WS})
    assert res.status_code == 404
    assert res.json()["error_code"] == "job.notFound"

    src = tmp_path / WS / "02_简历工坊" / "source"
    for item in src.iterdir():
        item.unlink()
    res = client.get("/api/jobs/%s/gap" % JOB, params={"ws": WS})
    assert res.status_code == 404
    assert res.json()["error_code"] == "job.resumeVersionMissing"


def test_gap_endpoint_422_when_inputs_incomplete(client, tmp_path):
    """JD 原文缺失（新建岗位刚粘贴前的中间态）：可读的 422，不是栈。"""
    _seed_endpoint_ws(tmp_path)
    (tmp_path / WS / "01_岗位池" / JOB / "JD原文.md").unlink()

    res = client.get("/api/jobs/%s/gap" % JOB, params={"ws": WS})

    assert res.status_code == 422
    assert res.json()["error_code"] == "job.gapFailed"
