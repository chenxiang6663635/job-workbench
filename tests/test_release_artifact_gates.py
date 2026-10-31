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


def test_real_repo_is_consistent():
    """集成断言：仓库当前必须通过（落章后跑一次就知道有没有漏改）。"""
    assert crv.check(crv.collect()) == []


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
