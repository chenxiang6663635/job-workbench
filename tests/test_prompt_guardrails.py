# -*- coding: utf-8 -*-
"""反编造护栏的锁死测试。

核心断言：提示词里的反编造条款**必须存在**，删句即测试失败——
参照 Resume-Matcher 的 test_prompt_guardrails.py 思路，把「诚实红线」
从文档约定变成可执行的工程约束。

本地校验器五项（对应实施计划）：
  1. 空改动        —— 建议与原文全等，说明模型什么都没做
  2. section 漂移  —— 结构（列表条目数）变了，属于结构性改动而非措辞润色
  3. 身份字段被改  —— 姓名/电话/邮箱/地点被模型动了，绝对禁止
  4. 字数爆炸      —— 单段文字暴增，大概率是往里塞了新内容
  5. 新增数字      —— 建议里出现原文没有的数字/百分比，编造数据的典型特征
"""

import io
import os
import sys
import zipfile

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "web", "backend")
sys.path.insert(0, BACKEND)

import resume_guard  # noqa: E402
import resume_import  # noqa: E402

# 造最小 docx 的 XML 骨架（docx 本质是 zip + word/document.xml）
DOCX_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body>'
    '<w:p><w:r><w:t>张三</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>某大学 人工环境工程 硕士</w:t></w:r></w:p>'
    '</w:body></w:document>'
)


@pytest.fixture
def docx_path(tmp_path):
    p = tmp_path / "sample.docx"
    with zipfile.ZipFile(str(p), "w") as z:
        z.writestr("word/document.xml", DOCX_XML)
    return str(p)


# ---------------------------------------------------------------------------
# 提示词条款锁死：删句即失败
# ---------------------------------------------------------------------------

def test_guardrail_clause_exists():
    clause = resume_guard.GUARDRAIL_CLAUSE
    assert clause and clause.strip(), "反编造条款不能为空"


def test_guardrail_clause_forbids_fabrication():
    clause = resume_guard.GUARDRAIL_CLAUSE
    # 条款必须同时说清三件事：禁止编造、只许改写既有事实、经得起追问
    assert "编造" in clause or "虚构" in clause, "条款必须明确禁止编造"
    assert "事实" in clause, "条款必须锚定已有事实"
    assert "追问" in clause, "条款必须提到面试追问（这是红线的现实代价）"


def test_prompt_template_contains_clause():
    # 生成改写提示词的函数必须拼入条款，单独维护一份提示词却漏掉条款 = 编造放行
    prompt = resume_guard.build_rewrite_prompt(
        {"basics": {"name": "测试"}, "projects": []}, "突出制冷方向")
    assert resume_guard.GUARDRAIL_CLAUSE in prompt


# ---------------------------------------------------------------------------
# 本地校验器五项
# ---------------------------------------------------------------------------

def _sample():
    return {
        "basics": {"name": "张三", "phone": "13800000000", "email": "z@x.com",
                   "location": "广州"},
        "education": [{"school": "某大学", "major": "人工环境", "degree": "硕士",
                       "period": "2024.09 — 至今", "note": ""}],
        "projects": [
            {"title": "制冷循环分析", "tag": "", "points": [
                "围绕蒸气压缩循环分析蒸发器与冷凝器传热",
                "用 EnergyPlus 完成负荷计算"]},
        ],
        "work": [{"org": "某公司", "role": "实习生", "period": "2024.07 — 2024.08",
                  "points": ["参与冷冻水系统现场检查"]}],
        "skills": [{"group": "仿真", "items": "EnergyPlus、CFD"}],
        "extras": {"research": [], "awards": "", "certificates": ""},
    }


def test_rejects_no_change():
    ok, issues = resume_guard.validate_rewrite(_sample(), _sample())
    assert not ok
    assert any("没有" in i or "空" in i for i in issues)


def test_rejects_section_drift():
    orig = _sample()
    sugg = _sample()
    # 偷偷加一个项目：结构性改动，不是润色
    sugg["projects"].append({"title": "新项目", "tag": "", "points": ["编的"]})
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok
    assert any("结构" in i or "条目" in i for i in issues)


def test_rejects_identity_change():
    orig = _sample()
    sugg = _sample()
    sugg["basics"]["name"] = "李四"
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok
    assert any("身份" in i for i in issues)


def test_rejects_identity_location_change():
    orig = _sample()
    sugg = _sample()
    sugg["basics"]["location"] = "深圳"
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok


def test_rejects_length_explosion():
    orig = _sample()
    sugg = _sample()
    sugg["projects"][0]["points"][0] = (
        "围绕蒸气压缩循环，系统性地分析蒸发器与冷凝器的传热机理，"
        "建立了完整的换热模型框架，深入研究了流态分布对整体传热系数的影响规律，"
        "并结合工程实际提出了多项优化改进建议，形成了体系化的分析方法论与实施路径")
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok
    assert any("字数" in i or "长度" in i for i in issues)


def test_rejects_new_numbers():
    orig = _sample()
    sugg = _sample()
    # 编造数据：原文没有 "30"，建议里出现了
    sugg["projects"][0]["points"][0] = "围绕蒸气压缩循环分析传热，效率提升30%"
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok
    assert any("数字" in i for i in issues)


def test_rejects_new_amount():
    orig = _sample()
    sugg = _sample()
    sugg["work"][0]["points"][0] = "参与冷冻水系统现场检查，管理500万项目"
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert not ok
    assert any("数字" in i for i in issues)


def test_accepts_safe_rewording():
    orig = _sample()
    sugg = _sample()
    # 措辞润色：结构不变、身份不变、无新数字、长度相近
    sugg["projects"][0]["points"][0] = "围绕蒸气压缩循环，分析蒸发器与冷凝器的传热表现"
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert ok, "安全改写不应被拦：" + "；".join(issues)


def test_accepts_reordering_words_only():
    orig = _sample()
    sugg = _sample()
    sugg["skills"][0]["items"] = "CFD、EnergyPlus"  # 只调顺序
    ok, issues = resume_guard.validate_rewrite(orig, sugg)
    assert ok, "纯排序调整不应被拦：" + "；".join(issues)


# ---------------------------------------------------------------------------
# 简历一键导入护栏（第一批）
#
# 与改写场景的根本差别：导入是「抽取」不是「生成」。模型只允许把文件里
# 已有的文字搬进字段，缺失留空，绝不补全。可溯源校验就是这条红线的执行者：
# 每个字段值都必须能在原文里找到，否则标为疑似补全交由用户核对。
# ---------------------------------------------------------------------------

SOURCE_TEXT = (
    "张三\n"
    "电话：13800000000　邮箱：zhangsan@example.com\n"
    "某大学　人工环境工程　硕士　2024.09 — 至今\n"
    "项目：制冷循环分析。围绕蒸气压缩循环分析蒸发器与冷凝器，效率提升 12%\n"
)


def test_import_clause_exists():
    assert resume_import.IMPORT_CLAUSE and resume_import.IMPORT_CLAUSE.strip()


def test_import_clause_forbids_completion():
    clause = resume_import.IMPORT_CLAUSE
    # 条款必须同时说清：只抽取、缺失留空、禁止补全推测美化数字
    assert "抽取" in clause, "条款必须限定为「抽取」"
    assert "留空" in clause, "条款必须要求缺失字段留空"
    assert "补全" in clause or "推测" in clause, "条款必须禁止补全与推测"
    assert "数字" in clause, "条款必须点名禁止美化数字"


def test_import_prompt_contains_clause():
    prompt = resume_import.build_import_prompt(SOURCE_TEXT)
    assert resume_import.IMPORT_CLAUSE in prompt


def test_traceable_accepts_values_found_in_source():
    data = {
        "basics": {"name": "张三", "phone": "13800000000"},
        "projects": [{"points": ["围绕蒸气压缩循环分析蒸发器与冷凝器"]}],
    }
    issues = resume_import.traceable_issues(SOURCE_TEXT, data)
    assert issues == [], "原文里都有的值不应被标：" + "；".join(issues)


def test_traceable_flags_value_missing_from_source():
    data = {"projects": [{"points": ["主导了整个数据中心冷却系统的改造"]}]}
    issues = resume_import.traceable_issues(SOURCE_TEXT, data)
    assert issues, "原文没有的内容必须被标出"
    assert any("未在原文" in i or "补全" in i for i in issues)


def test_traceable_flags_number_not_in_source():
    # 原文只有 12%，写 30% 就是编数字
    data = {"projects": [{"points": ["效率提升 30%"]}]}
    issues = resume_import.traceable_issues(SOURCE_TEXT, data)
    assert issues, "原文没有的数字必须被标出"


def test_traceable_tolerates_whitespace_and_punctuation():
    # 全角/半角与空白差异应被归一化掉，否则会误报
    data = {"basics": {"email": "zhangsan@example.com"}}
    issues = resume_import.traceable_issues(
        SOURCE_TEXT.replace("：", ":").replace("　", " "), data)
    assert issues == [], "标点与空白差异不应误报：" + "；".join(issues)


def test_traceable_ignores_empty_values():
    # 留空是合规的（正是条款要求的），不该被当成问题
    data = {"basics": {"name": "张三", "location": ""}}
    issues = resume_import.traceable_issues(SOURCE_TEXT, data)
    assert issues == []


def test_extract_text_reads_docx(docx_path):
    text = resume_import.extract_text(docx_path, ".docx")
    assert "张三" in text
    assert "人工环境工程" in text


def test_extract_text_reads_plain_text(tmp_path):
    p = tmp_path / "resume.txt"
    with io.open(str(p), "w", encoding="utf-8") as f:
        f.write(SOURCE_TEXT)
    text = resume_import.extract_text(str(p), ".txt")
    assert "张三" in text


def test_extract_text_rejects_unknown_ext(tmp_path):
    p = tmp_path / "a.bin"
    with io.open(str(p), "wb") as f:
        f.write(b"\x00\x01")
    with pytest.raises(ValueError):
        resume_import.extract_text(str(p), ".bin")
