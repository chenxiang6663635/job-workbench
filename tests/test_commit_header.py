# -*- coding: utf-8 -*-
"""提交信息 / PR 标题校验的锁死测试。

这套规则有两个容易「写了等于没写」的失效方式，都用真实翻车案例钉住：

1. **语言规则写成许可而不是要求**：原钩子只写「subject 允许中文」，
   于是英文照过。本文件用两条真的落进过 main 的英文 subject 当回归用例。
2. **只管提交信息、不管 PR 标题**：squash 合并会把 PR 标题变成主干 subject，
   本地钩子看不到它。所以 CI 侧必须有独立入口（check_pr_title）。

测试同时覆盖「该过的必须过」——规则过严会逼开发者习惯性 --no-verify，
那等于把整套护栏废掉。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import check_pr_title  # noqa: E402
import commit_header  # noqa: E402


def _errors(message):
    return commit_header.validate(message)


# 真实落进 main 的两条英文 subject（PR #15 / #16 的标题）——这就是当时没拦住的输入
LANDED_ENGLISH_SUBJECTS = [
    "feat(ui): C2 batch B — Jobs & Resume migration to UI primitives",
    "feat(ui): batch C — finish the shared UI primitive migration "
    "(Progress/Library/Settings + last 5 dialogs)",
]


@pytest.mark.parametrize("message", LANDED_ENGLISH_SUBJECTS)
def test_english_subjects_that_actually_landed_are_rejected(message):
    errors = _errors(message)
    assert errors, "英文 subject 必须被拦下：%s" % message
    assert any("中文" in e for e in errors)


def test_chinese_subject_passes():
    assert _errors("feat(tools): init_workspace.py --demo —— 一条命令得到满数据工作区") == []


def test_ascii_only_subject_is_rejected_with_rewrite_hint():
    errors = _errors("chore: bump electron to 31.0.0")
    assert errors and any("中文" in e for e in errors)
    # 报错要能直接照着改，而不是只说「不对」
    assert any("chore:" in e for e in errors)


def test_fullwidth_punctuation_does_not_count_as_chinese():
    """全角标点不算中文：这条防的是「半英文混过去」（全角句号 U+3002 不在汉字区）。"""
    errors = _errors("fix: resolve timeout。（ascii only, fullwidth period）")
    assert errors and any("中文" in e for e in errors)


def test_reports_every_violation_at_once():
    """一条标题同时违反语言与长度时要两条都报，别让人改完再撞一次。"""
    errors = _errors("feat(ui): " + "x" * 120)
    assert len(errors) == 2, "应同时报出超长与缺中文，实际：%s" % errors


def test_format_violation_is_reported():
    errors = _errors("feat finish the migration")
    assert errors and any("type(scope): subject" in e for e in errors)


def test_unknown_type_is_reported():
    errors = _errors("feature(ui): 加一个按钮")
    assert errors and any("未知 type" in e for e in errors)


def test_header_length_limit():
    errors = _errors("feat(ui): " + "字" * 100)
    assert errors and any("超过" in e for e in errors)


def test_bang_is_allowed_for_breaking_change():
    assert _errors("feat(api)!: 移除旧版接口") == []


def test_scope_is_optional():
    assert _errors("docs: 补一句说明") == []


def test_empty_message_is_rejected():
    assert _errors("   "), "空白提交信息必须拦下"


@pytest.mark.parametrize("message", [
    'Merge branch "main" into feat/x',
    "Revert \"feat(ui): 加了点东西\"",
    "fixup! feat(ui): 加了点东西",
    "Squashed commit of the following:",
])
def test_git_generated_headers_are_exempt(message):
    assert _errors(message) == []


def test_pr_title_does_not_get_commit_exemptions():
    """PR 标题永远是人工写的，不该享受 git 生成头的豁免。

    否则把标题写成「Merge xxx」（纯英文）就能整条绕过语言闸——豁免白名单
    直接变成旁路。
    """
    title = 'Merge branch "cleanup" into main'
    assert commit_header.validate(title, source=commit_header.SOURCE_COMMIT) == []
    errors = commit_header.validate(title, source=commit_header.SOURCE_PR_TITLE)
    assert errors, "PR 标题不该继承提交信息的豁免"


@pytest.mark.parametrize("subject", [
    "設定を変更",          # 日文：汉字 + 假名
    "設定変更を行った",     # 日文：汉字 + 假名
    "설정을 변경",          # 韩文：谚文
])
def test_japanese_and_korean_are_not_accepted_as_chinese(subject):
    """汉字区与日文汉字共享码位，逐字无法区分，故用假名/谚文排除。"""
    errors = _errors("feat(ui): " + subject)
    assert errors, "日文/韩文不该被当作中文放行：%s" % subject
    assert any("假名" in e or "谚文" in e for e in errors)


def test_pure_han_japanese_is_a_known_gap():
    """纯汉字书写的日文无法与中文区分——这是已知缺口，钉住它是为了别再假装能拦。"""
    assert _errors("feat(ui): 設定変更") == []


# --- CI 入口：PR 标题校验 -------------------------------------------------

def test_pr_title_reads_env(monkeypatch, capsys):
    monkeypatch.setenv("PR_TITLE", "feat(ui): 迁移到新原语")
    assert check_pr_title.main([]) == 0
    assert "[pr-title][OK]" in capsys.readouterr().out


def test_pr_title_rejects_english(monkeypatch, capsys):
    monkeypatch.setenv("PR_TITLE", LANDED_ENGLISH_SUBJECTS[1])
    assert check_pr_title.main([]) == 1
    out = capsys.readouterr().out
    assert "中文" in out
    # 报错要告诉人怎么改
    assert "gh pr edit" in out


def test_pr_title_missing_is_config_error_not_pass(monkeypatch, capsys):
    """拿不到标题时不能静默算通过——那等于这道闸悄悄失效。"""
    monkeypatch.delenv("PR_TITLE", raising=False)
    assert check_pr_title.main([]) == 2


def test_pr_title_argv_overrides_env(monkeypatch, capsys):
    monkeypatch.setenv("PR_TITLE", "chore: no chinese here")
    assert check_pr_title.main(["--title", "fix: 中文标题"]) == 0
    assert "[pr-title][OK]" in capsys.readouterr().out
