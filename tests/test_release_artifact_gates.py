"""发布门禁的两个纯函数（2026-10-30 审计 §四 / §五）。

- `tools/check_release_versions.py`：五处版本必须同号（历史 tag 上真漂过）。
- `tools/check_runtime_advisories.py`：用户实际运行的 electron 不低于已知安全基线
  （`npm audit --omit=dev` 覆盖不到它，因为它在 devDependencies 里）。

两者都只测**判据**；「真实仓库当前是否通过」各有一条集成断言，避免判据写完却没人接上。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_release_versions as crv  # noqa: E402
import check_runtime_advisories as cra  # noqa: E402


# ---------- 版本一致性 ----------

def test_versions_all_equal_passes():
    versions = {
        crv.APP: "26.10.0",
        crv.LOCK + " (top)": "26.10.0",
        crv.LOCK + ' (packages[""])': "26.10.0",
        crv.DSH_MAIN: "26.10.0",
        crv.DSH_PLATFORM: "26.10.0",
    }
    assert crv.check(versions) == []


@pytest.mark.parametrize("path", [crv.LOCK + " (top)", crv.LOCK + ' (packages[""])',
                                 crv.DSH_MAIN, crv.DSH_PLATFORM])
def test_any_single_drift_is_reported(path):
    """四处里任何一处漂移都得报——不能只查 lock 或只查 DSH。"""
    versions = {crv.APP: "26.10.0", crv.LOCK + " (top)": "26.10.0",
                crv.LOCK + ' (packages[""])': "26.10.0",
                crv.DSH_MAIN: "26.10.0", crv.DSH_PLATFORM: "26.10.0"}
    versions[path] = "26.9.0"
    problems = crv.check(versions)
    assert len(problems) == 1
    assert path in problems[0]
    assert "26.9.0" in problems[0] and "26.10.0" in problems[0]


def test_missing_version_field_is_reported():
    versions = {crv.APP: "26.10.0", crv.DSH_MAIN: ""}
    problems = crv.check(versions)
    assert any("没有 version 字段" in p for p in problems)


def test_app_version_missing_is_fatal():
    problems = crv.check({crv.APP: "", crv.DSH_MAIN: "26.10.0"})
    assert len(problems) == 1 and "没有 version 字段" in problems[0]


def test_internal_dependency_declaration_must_match():
    """`optionalDependencies` 里的子包版本（审计 2026-10-31 发现 1）。"""
    versions = {crv.APP: "26.11.0"}
    specs = {"integrations/dsh/package.json → optionalDependencies.dsh-job-workbench-win32-x64":
             "26.10.0"}
    problems = crv.check(versions, specs)
    assert len(problems) == 1 and "26.10.0" in problems[0] and "26.11.0" in problems[0]


def test_range_spec_for_internal_dependency_is_rejected():
    """内部依赖必须是精确版本——`^26.11.0` 等于允许主包配旧子包。"""
    versions = {crv.APP: "26.11.0"}
    for spec in ("^26.11.0", "~26.11.0", ">=26.11.0"):
        problems = crv.check(versions, {"dsh → optionalDependencies.x": spec})
        assert problems and "不是精确版本" in problems[0], spec


def test_real_repo_is_consistent():
    """集成断言：仓库当前必须通过（落章后跑一次就知道有没有漏改）。"""
    versions, specs = crv.collect()
    assert crv.check(versions, specs) == []
    # 至少要覆盖到 DSH 主包指向平台子包的那条声明，否则等于没查。
    assert any("optionalDependencies.dsh-job-workbench-win32-x64" in k for k in specs)


# ---------- 运行时安全基线 ----------

def test_runtime_below_baseline_fails():
    problems = cra.check({"electron": "44.4.5"}, {"electron": ("44.9.1", "GHSA-x")})
    assert len(problems) == 1
    assert "44.4.5" in problems[0] and "44.9.1" in problems[0]


def test_runtime_at_or_above_baseline_passes():
    baseline = {"electron": ("44.9.1", "GHSA-x")}
    assert cra.check({"electron": "44.9.1"}, baseline) == []
    assert cra.check({"electron": "44.10.0"}, baseline) == []
    assert cra.check({"electron": "45.0.0"}, baseline) == []


def test_runtime_missing_from_lock_fails():
    problems = cra.check({}, {"electron": ("44.9.1", "GHSA-x")})
    assert problems and "找不到这个运行时" in problems[0]


def test_runtime_version_unparsable_fails():
    problems = cra.check({"electron": "latest"}, {"electron": ("44.9.1", "GHSA-x")})
    assert problems and "无法解析" in problems[0]


def test_real_lock_clears_the_baseline():
    """集成断言：真实 lock 里的 electron 不得低于基线（v26.10.0 时 44.10.0）。"""
    actual = cra.locked_version("electron")
    assert actual, "web/electron/package-lock.json 里应当能读到 electron 版本"
    assert cra.check({"electron": actual}) == []


# ---------- 预发布与发布链接线（2026-10-31 审计） ----------

def test_prerelease_is_rejected_not_truncated():
    """`44.9.1-beta.1` 语义上低于 `44.9.1`，不能截断成同号放行（第一版是乐观截断）。"""
    problems = cra.check({"electron": "44.9.1-beta.1"}, {"electron": ("44.9.1", "GHSA-x")})
    assert problems and "无法解析" in problems[0]


def test_release_workflow_runs_both_gates():
    """tag 链必须自己跑一次（main 的保护不传递到发布）；`publish` 依赖 package，故失败即无 Draft。"""
    path = os.path.join(ROOT, ".github", "workflows", "release.yml")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "tools/check_runtime_advisories.py" in text
    assert "tools/check_release_versions.py" in text
