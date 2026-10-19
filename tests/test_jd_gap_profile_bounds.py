# -*- coding: utf-8 -*-
"""`resolve_profile` 的 `domain` / `direction` 边界：只接受单个目录/文件名。

**为什么有这份测试**：2026-10-18 外部审计质疑「`profile_dir = os.path.join(PROFILES, domain)`
里的 domain 是外部参数，不能仅凭模板目录位于应用根下就视为可信」。先写探针实测，
**确认两个方向都能穿越**：

- `domain="../../outside_plugin"` → 解析到 `template/profiles` 之外的目录，且**无任何警告**；
- `direction="../../../../outside_plugin/directions/x"` → 读到插件目录之外的 `.md`，
  同样**无警告**。

`isdir` / `isfile` 通过即采用 = 静默走错。修法：接上 `containment.escape_reason`
（既有原语）并加"单段"约束，越界显式拒绝。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "packages", "jobws-core", "src"))

from jobws_core import jd_gap  # noqa: E402


@pytest.fixture()
def staged(tmp_path, monkeypatch):
    """把 PROFILES 指到临时目录；外侧放一个"插件"（穿越的目标）。"""
    profiles = tmp_path / "template" / "profiles"
    (profiles / "real_domain" / "directions").mkdir(parents=True)
    (profiles / "real_domain" / "directions" / "ok.md").write_text(
        "正常方向", encoding="utf-8")
    monkeypatch.setattr(jd_gap, "PROFILES", str(profiles))
    monkeypatch.setattr(jd_gap, "ROOT", str(tmp_path / "template"))

    outside = tmp_path / "outside_plugin"
    (outside / "directions").mkdir(parents=True)
    (outside / "directions" / "x.md").write_text("外侧方向文件", encoding="utf-8")

    ws = tmp_path / "ws"
    ws.mkdir()
    return {"profiles": profiles, "outside": outside, "ws": ws}


def _resolved_within(path, root):
    if not path:
        return None
    return os.path.commonpath([os.path.abspath(path),
                               os.path.abspath(root)]) == os.path.abspath(root)


@pytest.mark.parametrize("domain", [
    "../../outside_plugin",       # .. 段
    "..\\outside_plugin",          # 反斜杠 + ..
    "C:/outside_plugin",          # 盘符
    "/etc",                        # 绝对路径
    "real_domain/sub",            # 含分隔符（子目录）
    "",                            # 空串
])
def test_domain_must_be_a_single_segment(staged, domain):
    """`domain` 只接受单个目录名——六类越界写法全部显式拒绝。

    空串是特例：它等价于"未指定"，走既有 else 分支的指引文案（不是"不合法"），
    但同样必须 `profile_dir is None` 且给出理由——不许静默采用。
    """
    profile_dir, _direction_file, warnings = jd_gap.resolve_profile(
        str(staged["ws"]), domain=domain)

    assert profile_dir is None, "放行了：%r → %s" % (domain, profile_dir)
    assert warnings, "拒绝了但没给理由（静默）"
    if domain.strip():
        assert any("不合法" in w for w in warnings), warnings
    else:
        assert any("无法确定领域插件" in w for w in warnings), warnings
    assert _resolved_within(profile_dir, str(staged["profiles"])) in (None, True)


@pytest.mark.parametrize("direction", [
    "../../../../outside_plugin/directions/x",
    "..\\..\\outside_plugin\\directions\\x",
    "C:/outside_plugin/directions/x",
    "sub/ok",
])
def test_direction_must_be_a_single_segment(staged, direction):
    """`direction` 只接受单个文件名（不带 .md）——越界显式拒绝。"""
    _profile_dir, direction_file, warnings = jd_gap.resolve_profile(
        str(staged["ws"]), domain="real_domain", direction=direction)

    assert direction_file is None, "放行了：%r → %s" % (direction, direction_file)
    assert warnings, "拒绝了但没给理由（静默）"
    assert any("不合法" in w for w in warnings), warnings


def test_legitimate_domain_and_direction_still_work(staged):
    """正常路径不能被打断：合法插件 + 合法方向照常解析。"""
    profile_dir, direction_file, warnings = jd_gap.resolve_profile(
        str(staged["ws"]), domain="real_domain", direction="ok")

    assert profile_dir == str(staged["profiles"] / "real_domain")
    assert direction_file == str(staged["profiles"] / "real_domain"
                                 / "directions" / "ok.md")
    assert warnings == []


def test_workspace_profile_takes_priority_over_domain(staged):
    """工作区 `config/profile.md` 优先——这条既有行为不能被边界检查改坏。

    即便 `domain` 是越界值，也不该被采用（警告里不许出现"不合法"——那说明
    边界检查插到了 workspace 分支前面）。
    """
    ws_config = staged["ws"] / "config"
    ws_config.mkdir()
    (ws_config / "profile.md").write_text("工作区档案", encoding="utf-8")

    profile_dir, _direction_file, warnings = jd_gap.resolve_profile(
        str(staged["ws"]), domain="../../outside_plugin")

    assert profile_dir == str(ws_config), profile_dir
    assert not any("不合法" in w for w in warnings), warnings
