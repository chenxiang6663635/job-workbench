# -*- coding: utf-8 -*-
"""check_domains 的回归护栏。

与 test_check_skills 同款结构：合成目录测每条校验的**正反例**，外加一条
「真仓库必须合规」——后者防的是「合成全绿、真仓库红」的盲区。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from check_domains import describe, inspect_domains  # noqa: E402

GOOD_LEXICON = """# 词典

## Primary（3 分/项）

数据结构、算法

## Secondary（1.5 分/项）

Redis、Kafka

## Weak（登记不扣分）

大规模分布式调优
"""

GOOD_KEYWORDS = """# 注释行
简历与匹配度=简历,匹配
竞争与名额=竞争,名额
"""


def _problems_text(item):
    return "\n".join(item["problems"])


def _make(tmp_path, dirname="demo-domain", profile_id=None, lexicon=None,
          keywords=GOOD_KEYWORDS, omit=(), empty_direction=False):
    """在 tmp_path/profiles/<dirname> 下造一个合规插件，再按参数注入问题。"""
    root = tmp_path / "profiles"
    dom = root / dirname
    (dom / "directions").mkdir(parents=True)

    if "profile.md" not in omit:
        pid = profile_id if profile_id is not None else dirname
        (dom / "profile.md").write_text(
            "# 领域插件\n\n| 项 | 值 |\n|---|---|\n| 插件 ID | `%s` |\n| 名称 | 演示 |\n"
            "| 内置方向 | `x` |\n" % pid, encoding="utf-8")
    if "lexicon.md" not in omit:
        (dom / "lexicon.md").write_text(lexicon or GOOD_LEXICON, encoding="utf-8")
    if "failure_keywords.txt" not in omit:
        (dom / "failure_keywords.txt").write_text(keywords, encoding="utf-8")
    (dom / "directions" / "x.md").write_text(
        "" if empty_direction else "## 锚点\n\n- 词\n", encoding="utf-8")
    return root


def test_good_domain_is_clean(tmp_path):
    item = inspect_domains(str(_make(tmp_path)))[0]
    assert item["problems"] == []


def test_bad_directory_id_is_reported(tmp_path):
    root = _make(tmp_path, dirname="Demo_Domain")
    item = inspect_domains(str(root))[0]
    assert "目录 ID 不合规" in _problems_text(item)


def test_missing_required_files_are_reported(tmp_path):
    root = _make(tmp_path, omit=("lexicon.md", "failure_keywords.txt"))
    item = inspect_domains(str(root))[0]
    assert "缺少 lexicon.md" in _problems_text(item)
    assert "缺少 failure_keywords.txt" in _problems_text(item)


def test_lexicon_missing_a_level_is_reported(tmp_path):
    two_levels = GOOD_LEXICON.replace("## Weak（登记不扣分）\n\n大规模分布式调优\n", "")
    root = _make(tmp_path, lexicon=two_levels)
    item = inspect_domains(str(root))[0]
    assert "缺少 `Weak` 层" in _problems_text(item)


def test_unparseable_lexicon_is_reported(tmp_path):
    root = _make(tmp_path, lexicon="# 没有分层标题\n\n一些词\n")
    item = inspect_domains(str(root))[0]
    assert "解析不出任何词条" in _problems_text(item)


def test_bad_failure_keywords_line_is_reported(tmp_path):
    root = _make(tmp_path, keywords="# 注释\n类别一=词,词\n没有等号的一行\n空值=\n")
    item = inspect_domains(str(root))[0]
    assert "第 3 行不是" in _problems_text(item)
    assert "第 4 行" in _problems_text(item)


def test_comma_only_keywords_are_reported(tmp_path):
    """`类别=,,,` 在消费端（report 聚类）分词后是空类别——校验层必须拦住。"""
    root = _make(tmp_path, keywords="# 注释\n类别一=,,,\n")
    item = inspect_domains(str(root))[0]
    assert "没有任何有效关键词" in _problems_text(item)


def test_profile_id_mismatch_is_reported(tmp_path):
    root = _make(tmp_path, profile_id="some-other-id")
    item = inspect_domains(str(root))[0]
    assert "与目录名" in _problems_text(item)
    assert "不一致" in _problems_text(item)


def test_missing_directions_is_reported(tmp_path):
    root = _make(tmp_path)
    import shutil
    shutil.rmtree(str(root / "demo-domain" / "directions"))
    item = inspect_domains(str(root))[0]
    assert "缺少 directions/ 目录" in _problems_text(item)


def test_empty_direction_file_is_reported(tmp_path):
    root = _make(tmp_path, empty_direction=True)
    item = inspect_domains(str(root))[0]
    assert "空文件" in _problems_text(item)


def test_empty_root_returns_empty_list(tmp_path):
    assert inspect_domains(str(tmp_path / "nothing")) == []


def test_describe_mentions_counts(tmp_path):
    root = _make(tmp_path)
    text = describe(inspect_domains(str(root)))
    assert "已检查 1 个领域插件，0 个不合规" in text


def test_repo_domains_are_compliant():
    """真实 template/profiles/ 必须合规——合成全绿、真仓库却红是这类测试最大的盲区。"""
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "template", "profiles")
    results = inspect_domains(root)
    assert len(results) >= 2  # software-backend 与 hvac-cooling
    bad = [item for item in results if item["problems"]]
    assert not bad, describe(results)
