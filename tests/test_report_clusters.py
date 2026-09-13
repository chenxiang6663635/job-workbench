# -*- coding: utf-8 -*-
"""失败聚类的 noteCode 结构化字段（i18n 第三块拼图）。

note 原文是 CLI 契约（逐字节不变）；noteCode/noteParams 是英文界面按 code
拼句的结构化形态。这里锁住三条路径：样本太少 / 未配置关键词表 / 正常。
"""

import os
import sys

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools")
sys.path.insert(0, TOOLS)

import report  # noqa: E402


def _fail_row(stage="已挂", company="示例科技", reason="技术深度不足"):
    return {"当前阶段": stage, "公司": company, "状态原因": reason}


def _fail_rows(n):
    return [_fail_row(company="公司%d" % i) for i in range(n)]


def test_too_few_samples_carries_structured_note(tmp_path):
    """样本不足：shown=False，noteCode=too_few_samples，params 带 total/min。"""
    out = report.cluster_failures(_fail_rows(2), workspace=str(tmp_path))
    assert out["shown"] is False
    assert out["noteCode"] == "too_few_samples"
    assert out["noteParams"] == {"total": 2, "min": report.MIN_CLUSTER_SAMPLES}
    # note 原文是 CLI 契约：中文逐字不变
    assert "样本太少" in out["note"] and str(report.MIN_CLUSTER_SAMPLES) in out["note"]


def test_no_keywords_carries_structured_note(tmp_path):
    """样本够但没有关键词表：shown=True 退化为频次统计，noteCode=no_keywords。"""
    out = report.cluster_failures(_fail_rows(report.MIN_CLUSTER_SAMPLES + 1),
                                  workspace=str(tmp_path))
    assert out["shown"] is True
    assert out["source"] == "reason"
    assert out["noteCode"] == "no_keywords"
    assert out["noteParams"] == {}
    assert "failure_keywords" in out["note"]


def test_keywords_path_has_no_note_code(tmp_path):
    """配置了关键词表：正常聚类，note 为空、无 noteCode。"""
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    (cfg / "failure_keywords.txt").write_text(
        "技术深度=深度, 算法\n", encoding="utf-8")
    out = report.cluster_failures(_fail_rows(report.MIN_CLUSTER_SAMPLES + 1),
                                  workspace=str(tmp_path))
    assert out["shown"] is True
    assert out["source"] == "keywords"
    assert out["noteCode"] is None
    assert out["note"] == ""
