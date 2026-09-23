# -*- coding: utf-8 -*-
"""门禁加固的回归网（2026-09-23 二轮审计，笔 3）。

这一批修的都是"闸门本身漏了"，所以每条都得有"绕过写法被检出"的用例——否则下一次
又会以同样的方式漏掉：

1. 四端检查的反向那一半此前只覆盖 MCP 工具与插件**命令**，`agents/` 完全不参与；
2. 规模预算整片跳过 `mcp/` 与 `scripts/`（MCP 包能无限膨胀而检查报 OK）；
3. `fixture` / `allowlist` 这类词是**子串**匹配，路径里凑巧含词即可把预算放大 5 倍；
4. 分发脚本 docstring 写着"含版本号一致性"，实现里却没有那一步；
5. MCP 列表工具的 `limit<=0` 被当"不限制"——一步就能拉全表。
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import check_four_ends  # noqa: E402
import check_size  # noqa: E402


def _load_by_path(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- 1. 四端反向检查：agents 也要有归属 ---------------------------------------

def _actual(plugin):
    return {"mcp": [], "plugin": plugin}


def test_unregistered_agent_is_reported():
    """`agents/` 里放一个子代理而不登记进矩阵 → 必须被报出来（此前全绿）。"""
    problems = check_four_ends._check_registration(
        _actual({"commands": [], "declared_commands": [],
                 "agents": ["cross-end-audit"], "declared_agents": ["cross-end-audit.md"]}),
        [], [])
    assert any("子代理" in p for p in problems), problems


def test_registered_agent_via_exception_passes():
    """否定验证：显式登记进例外清单的子代理要放行（不然这条闸门没人过得去）。"""
    problems = check_four_ends._check_registration(
        _actual({"commands": [], "declared_commands": [],
                 "agents": ["cross-end-audit"], "declared_agents": ["cross-end-audit.md"]}),
        [], [{"end": "plugin", "item": "cross-end-audit", "reason": "维护者自用"}])
    assert problems == []


def test_agent_declared_but_missing_on_disk_is_reported():
    problems = check_four_ends._check_registration(
        _actual({"commands": [], "declared_commands": [],
                 "agents": [], "declared_agents": ["ghost.md"]}),
        [], [])
    assert any("不存在于 agents/" in p for p in problems), problems


def test_agent_on_disk_but_not_declared_is_reported():
    problems = check_four_ends._check_registration(
        _actual({"commands": [], "declared_commands": [],
                 "agents": ["ghost"], "declared_agents": []}),
        [], [{"end": "plugin", "item": "ghost", "reason": "x"}])
    assert any("未在 plugin.json" in p for p in problems), problems


# ---- 2. 规模预算：mcp/ 与 scripts/ 必须在扫描范围内 --------------------------

def test_scan_dirs_cover_mcp_and_scripts():
    assert "mcp" in check_size.SCAN_DIRS
    assert "scripts" in check_size.SCAN_DIRS


def test_mcp_source_files_are_actually_walked():
    rels = [rel for rel, _full in check_size.iter_source_files()]
    assert any(rel.startswith("mcp/") for rel in rels)
    assert any(rel.startswith("scripts/") for rel in rels)


# ---- 3. 数据型分类：不要再靠子串巧合 ------------------------------------------

@pytest.mark.parametrize("rel", [
    "web/backend/routers/fixture_api.py",   # 路径里含 fixture 的业务文件
    "web/frontend/src/lib/allowlist.ts",
    "tools/check_size.py",
])
def test_lookalike_paths_stay_logic(rel):
    assert check_size.classify(rel) == "logic", rel


@pytest.mark.parametrize("rel", [
    "tests/test_x.py",
    "mcp/tests/test_tools.py",
    "web/frontend/src/i18n/locales/zh-CN.ts",
    "web/backend/tests/fixtures/seed.py",
])
def test_real_data_files_stay_data(rel):
    assert check_size.classify(rel) == "data", rel


# ---- 4. 分发前的校验必须包含版本号一致性 --------------------------------------

def test_install_validate_rejects_version_drift(monkeypatch):
    install_skills = _load_by_path("install_skills_under_test", "tools/install_skills.py")
    import skill_rules

    monkeypatch.setattr(install_skills, "inspect_skills", lambda _p: [])
    monkeypatch.setattr(install_skills, "describe", lambda _r: "")
    monkeypatch.setitem(sys.modules, "check_plugin_assets",
                        type("stub", (), {"inspect_plugin_assets": staticmethod(lambda _r: [])}))
    monkeypatch.setattr(skill_rules, "version_problems",
                        lambda _root, _skills: ["插件壳版本 1.0.0 与应用 2.0.0 不一致"])

    assert install_skills._validate(ROOT) is False


def test_install_validate_passes_when_everything_agrees(monkeypatch):
    """否定验证：三向一致时必须放行（闸门不许变成"一律拒绝分发"）。"""
    install_skills = _load_by_path("install_skills_under_test2", "tools/install_skills.py")
    import skill_rules

    monkeypatch.setattr(install_skills, "inspect_skills", lambda _p: [])
    monkeypatch.setattr(install_skills, "describe", lambda _r: "")
    monkeypatch.setitem(sys.modules, "check_plugin_assets",
                        type("stub", (), {"inspect_plugin_assets": staticmethod(lambda _r: [])}))
    monkeypatch.setattr(skill_rules, "version_problems", lambda _root, _skills: [])

    assert install_skills._validate(ROOT) is True


# ---- 5. MCP 列表工具：limit 不许被解释成"不限制" ------------------------------

@pytest.fixture()
def mcp_limits():
    return _load_by_path("mcp_limits_under_test", "mcp/jobws_mcp/limits.py")


def test_zero_and_negative_clamp_to_one(mcp_limits):
    rows = list(range(50))
    assert mcp_limits.limit_rows(rows, 0) == [0]
    assert mcp_limits.limit_rows(rows, -5) == [0]


def test_over_large_limit_clamps_to_max(mcp_limits):
    rows = list(range(1000))
    assert len(mcp_limits.limit_rows(rows, 10 ** 6)) == mcp_limits.MAX_LIMIT


def test_normal_limit_is_respected(mcp_limits):
    rows = list(range(50))
    assert len(mcp_limits.limit_rows(rows, 7)) == 7
    assert len(mcp_limits.limit_rows(rows, None)) == mcp_limits.DEFAULT_LIMIT
