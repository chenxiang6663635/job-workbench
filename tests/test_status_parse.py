# -*- coding: utf-8 -*-
"""原文 → 状态建议的规则层（B11 轻量版）。

这一层是纯函数，所以这里钉的是**判断口径**而不是 IO：

1. **单调优先级**：只有更强的状态才建议覆盖；拒信不能覆盖 offer；终态不回退。
   这三条是这一批的红线，改坏了用户会看到「offer 被一封拒信打回」这种事。
2. **宁可漏不可错**：「感谢您的投递，简历已收到」这类回执不能被判成拒信——
   词表里刻意没有收「感谢您的关注」这种两边都出现的句子。
3. **只出建议不改数据**：`suggest()` 不得修改传入的 rows，也不得碰文件系统。
"""

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import status_parse  # noqa: E402


def _row(id_, company, role, stage):
    return {"id": id_, "公司": company, "岗位": role, "当前阶段": stage}


def _suggest(text, rows, **kw):
    return status_parse.suggest(text, rows, **kw)


# --- 1. 信号识别 --------------------------------------------------------------

def test_reject_mail_suggests_terminal():
    parsed = status_parse.parse("感谢您的参与。经过综合评估，我们很遗憾地通知您，本次不再推进。")
    assert [s["stage"] for s in parsed["signals"]] == ["已挂"]
    assert parsed["signals"][0]["evidence"], "建议必须留下原文证据，否则用户无法复核"


def test_offer_mail_suggests_offer():
    parsed = status_parse.parse("恭喜！现向您发出录用意向书，请确认薪资方案。")
    assert [s["stage"] for s in parsed["signals"]] == ["offer"]


def test_receipt_mail_is_not_mistaken_for_a_rejection():
    """回执类邮件常带「感谢」措辞——不能被判成拒信，也不能越级到面试。"""
    parsed = status_parse.parse("感谢您的投递，我们已收到您的简历，正在评估中。")
    assert [s["stage"] for s in parsed["signals"]] == ["已投"]


def test_round_is_detected_from_strongest_keyword():
    assert status_parse.parse("邀请您参加第二轮面试")["signals"][0]["stage"] == "二面"
    assert status_parse.parse("邀请您参加终面")["signals"][0]["stage"] == "三面"
    assert status_parse.parse("HR 邀请您沟通薪酬细节")["signals"][0]["stage"] == "HR面"
    # 大小写不该成为漏判的理由（同一批词里中英混排）
    assert status_parse.parse("HR面：邀您参加面试")["signals"][0]["stage"] == "HR面"


def test_common_invitation_phrasings_are_recognised():
    """最常见的那句「邀请您参加面试」必须认出来（早期只收了无「请」字的写法）。"""
    assert status_parse.parse("邀请您参加面试")["signals"][0]["stage"] == "一面"
    assert status_parse.parse("诚邀您参加面试")["signals"][0]["stage"] == "一面"
    assert status_parse.parse("面试邀请：本周内安排")["signals"][0]["stage"] == "一面"


def test_weak_words_alone_do_not_count_as_an_interview_invite():
    """弱词必须与邀请类措辞共现。

    「人力资源部的薪酬制度」这类正文单独出现「人力 / 薪酬」时判成 HR 面，
    会让用户第一次试用就失去信任——宁可漏，不可错。
    """
    assert status_parse.parse("关于人力资源部的薪酬制度说明")["signals"] == []
    assert status_parse.parse("分享一下上次技术面的复盘心得")["signals"] == []


def test_written_test_mail_suggests_test_stage():
    parsed = status_parse.parse("请于 3 天内完成在线测评，测评链接见下。")
    assert [s["stage"] for s in parsed["signals"]] == ["笔试"]


def test_contradictory_mail_gives_no_stage():
    """同一段原文里既有拒信又有 offer 措辞 → 不给建议，只报矛盾。"""
    parsed = status_parse.parse("很遗憾地通知您未能通过本次筛选；同时我们也向您发出录用意向书。")
    assert parsed["ambiguous"] is True
    assert parsed["signals"] == []


# --- 2. 单调优先级（本批红线）------------------------------------------------

@pytest.mark.parametrize("current", ["offer", "签约"])
def test_rejection_cannot_override_an_offer(current):
    """红线：拒信不得把 offer 及以上打回。

    这是本层代价最大的误判——拿到 offer 之后收到的「很遗憾」多半来自另一条流程。
    """
    rows = [_row("A001", "示例公司", "示例岗位", current)]
    got = _suggest("示例公司：很遗憾地通知您，本次不再推进。", rows)
    assert got["matches"][0]["建议阶段"] == "已挂"
    assert got["matches"][0]["可覆盖"] is False
    assert "不覆盖" in got["matches"][0]["原因"]


def test_rejection_can_still_land_on_a_normal_stage():
    """拒信对正常流转阶段照常可落——防的是「打回 offer」，不是禁止拒信。"""
    got = _suggest("示例公司：很遗憾地通知您，本次不再推进。",
                   [_row("A001", "示例公司", "示例岗位", "一面")])
    assert got["matches"][0]["可覆盖"] is True


def test_weaker_stage_cannot_override_a_stronger_one():
    rows = [_row("A001", "示例公司", "示例岗位", "三面")]
    got = _suggest("示例公司邀请您参加一面。", rows)
    assert got["matches"][0]["可覆盖"] is False
    assert "不强于" in got["matches"][0]["原因"]


def test_stronger_stage_can_override():
    rows = [_row("A001", "示例公司", "示例岗位", "一面")]
    got = _suggest("示例公司邀请您参加终面。", rows)
    assert got["matches"][0]["建议阶段"] == "三面"
    assert got["matches"][0]["可覆盖"] is True


@pytest.mark.parametrize("current", ["已挂", "已放弃", "我拒绝的 offer"])
def test_any_terminal_current_blocks_every_suggestion(current):
    """终态不回退：三个终态各自都要挡住，不能只测「已挂」。"""
    rows = [_row("A001", "示例公司", "示例岗位", current)]
    got = _suggest("示例公司向您发出录用意向书。", rows)
    assert got["matches"][0]["可覆盖"] is False


def test_company_name_prefix_match_is_resolved_toward_the_more_specific_one():
    """表里同时有「华为」和「华为云」时，正文写「华为云」只该命中后者。

    子串匹配的天然缺陷；能救的那一半在这里做（丢掉是别人前缀的那个）。
    """
    rows = [_row("A001", "华为", "后端开发", "已投"),
            _row("A002", "华为云", "云平台开发", "已投")]
    got = _suggest("华为云邀请您参加二面。", rows)
    assert [m["id"] for m in got["matches"]] == ["A002"]


def test_can_override_is_the_single_implementation():
    assert status_parse.can_override("一面", "二面")[0] is True
    assert status_parse.can_override("二面", "一面")[0] is False
    assert status_parse.can_override("已挂", "offer")[0] is False
    assert status_parse.can_override("一面", "已挂")[0] is True


def test_unknown_current_stage_blocks_any_override():
    """表外未知值（手改坏了、旧版本留下的）要**显式拒绝**。

    交给 rank 去比的话，未知值会落到列表末尾——语义上等于「比谁都强」，
    这种「反过来的默认」正是最容易出错的地方。
    """
    ok, why = status_parse.can_override("端面", "二面")
    assert ok is False
    assert "不在已知阶段里" in why


def test_empty_current_stage_allows_any_override():
    """空阶段 = 记录还没有阶段（新建成空），任何建议都该能落。"""
    assert status_parse.can_override("", "已投")[0] is True


# --- 3. 匹配既有记录 ----------------------------------------------------------

def test_matches_by_company_name_in_the_text():
    rows = [_row("A001", "示例科技", "后端开发", "已投"),
            _row("A002", "云帆智算", "算法工程师", "一面")]
    got = _suggest("示例科技邀请您参加第二轮面试。", rows)
    assert [m["id"] for m in got["matches"]] == ["A001"]
    assert got["matches"][0]["命中"] == "公司"


def test_multiple_matches_are_flagged_for_human_choice():
    rows = [_row("A001", "示例科技", "后端开发", "已投"),
            _row("A002", "示例科技", "算法工程师", "已投")]
    got = _suggest("示例科技邀请您参加面试。", rows)
    assert got["ambiguous_match"] is True
    assert len(got["matches"]) == 2


def test_unmatched_text_says_so_instead_of_guessing():
    got = _suggest("某家没在表里的公司发来了面试邀请。", [_row("A001", "示例科技", "后端", "已投")])
    assert got["unmatched"] is True
    assert got["matches"] == []
    assert any("没有出现" in n for n in got["notes"])


# --- 4. 日期与纯函数性 --------------------------------------------------------

def test_dates_are_extracted_in_both_writings():
    """固定 today，不跟着系统时钟走——否则这条断言只是复述实现口径。"""
    got = _suggest("请于 2026-09-20 前确认；另一场安排在 9月25日。", [],
                   today=datetime.date(2026, 9, 12))
    assert got["dates"] == ["2026-09-20", "2026-09-25"]


def test_suggest_does_not_touch_the_input_rows_or_the_filesystem():
    rows = [_row("A001", "示例科技", "后端开发", "已投")]
    before = [dict(r) for r in rows]
    status_parse.suggest("示例科技邀请您参加二面。", rows)
    assert rows == before, "建议层不得修改传入的记录"

    # 本模块不该有任何写文件的路径：导入它之后模块里不该出现 open/os.rename 之类
    assert not hasattr(status_parse, "write_rows")
    assert not hasattr(status_parse, "append_history")


def test_no_signals_still_returns_a_usable_suggestion():
    """原文没给出线索时也要能落到「人工指定阶段」，而不是抛异常或返回空。"""
    got = _suggest("示例科技 发来一封邮件。", [_row("A001", "示例科技", "后端开发", "已投")])
    assert got["signals"] == []
    assert got["matches"][0]["建议阶段"] == ""
    assert got["matches"][0]["可覆盖"] is False
    assert any("没有识别出" in n for n in got["notes"])
