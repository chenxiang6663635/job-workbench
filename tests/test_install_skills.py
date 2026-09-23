# -*- coding: utf-8 -*-
"""`tools/install_skills.py` 的 `--link` 建链语义（批 10）。

为什么单独钉它：建链只在 `--link` 下走到，而那条路最容易「看起来成功了」——
① 已存在的**真实副本**不能被静默覆盖（那可能是用户自己改过的版本）；
② 已有的链要能重建（幂等：重跑不累积、不因一次失败把好链弄丢）；
③ 目标目录不存在时要能建出来。
Windows 未开开发者模式时建链会失败，所以用例在无符号链接能力的环境里跳过——
CI 跑在 Linux，这几条在那里是真跑的。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import install_skills  # noqa: E402
from install_skills import link_tree  # noqa: E402


def _symlink_supported(tmp_path):
    probe = str(tmp_path / "_probe")
    try:
        os.symlink(str(tmp_path), probe)
    except (OSError, NotImplementedError):
        return False
    os.unlink(probe)
    return True


def _make_source(tmp_path):
    src = tmp_path / "src"
    (src / "jwb-x").mkdir(parents=True)
    (src / "jwb-x" / "SKILL.md").write_text("真源", encoding="utf-8")
    return src


def _install_one_stub(ok):
    """替身：`ok=False` 模拟某个落点失败（权限不足、不支持符号链接…）。"""
    calls = {"n": 0}

    def _stub(*_args, **_kwargs):
        calls["n"] += 1
        return ok
    return _stub, calls


def test_main_returns_nonzero_when_a_target_fails(monkeypatch, capsys):
    """部分落点失败必须非零退出。

    此前 `_install_one` 的失败只被 `return False` 吞掉、出口无条件 `return 0`：
    CI 里 `jobws skills install` 拿到 0 就当全部分发成功，而实际上有一个宿主目录
    没装成（留着旧版本或干脆没有）。
    """
    stub, calls = _install_one_stub(False)
    monkeypatch.setattr(install_skills, "_validate", lambda root: True)
    monkeypatch.setattr(install_skills, "_install_one", stub)
    monkeypatch.setattr(sys, "argv", ["jobws"])

    assert install_skills.main() == 1
    assert calls["n"] > 0, "一个落点都没尝试，这条断言就没钉住任何东西"
    out = capsys.readouterr().out
    assert "失败" in out or "未完成" in out


def test_main_returns_zero_when_all_targets_succeed(monkeypatch):
    """否定验证：全部成功仍必须是 0——出口不能矫枉过正到「一律非零」。"""
    stub, calls = _install_one_stub(True)
    monkeypatch.setattr(install_skills, "_validate", lambda root: True)
    monkeypatch.setattr(install_skills, "_install_one", stub)
    monkeypatch.setattr(sys, "argv", ["jobws"])

    assert install_skills.main() == 0
    assert calls["n"] > 0


def test_link_tree_skips_real_copies(tmp_path):
    if not _symlink_supported(tmp_path):
        pytest.skip("当前环境不允许建符号链接（Windows 未开开发者模式）")
    src = _make_source(tmp_path)
    dst = tmp_path / "dst" / "skills"
    (dst / "jwb-x").mkdir(parents=True)
    (dst / "jwb-x" / "SKILL.md").write_text("用户自己改过的副本", encoding="utf-8")

    linked, skipped, failed = link_tree(str(src), str(dst))

    assert skipped == ["jwb-x"]
    assert linked == [] and failed == []
    assert (dst / "jwb-x" / "SKILL.md").read_text(encoding="utf-8") == "用户自己改过的副本"


def test_link_tree_creates_links_into_missing_target(tmp_path):
    if not _symlink_supported(tmp_path):
        pytest.skip("当前环境不允许建符号链接（Windows 未开开发者模式）")
    src = _make_source(tmp_path)
    dst = tmp_path / "dst" / "skills"

    linked, skipped, failed = link_tree(str(src), str(dst))

    assert linked == ["jwb-x"] and skipped == [] and failed == []
    assert os.path.islink(str(dst / "jwb-x"))
    assert (dst / "jwb-x" / "SKILL.md").read_text(encoding="utf-8") == "真源"


def test_link_tree_rebuilds_existing_links_idempotently(tmp_path):
    if not _symlink_supported(tmp_path):
        pytest.skip("当前环境不允许建符号链接（Windows 未开开发者模式）")
    src = _make_source(tmp_path)
    dst = tmp_path / "dst" / "skills"
    link_tree(str(src), str(dst))

    # 第二次跑：既不算「跳过」，也不留临时链残留
    linked, skipped, failed = link_tree(str(src), str(dst))

    assert linked == ["jwb-x"] and skipped == [] and failed == []
    assert [n for n in os.listdir(str(dst)) if "jobws-tmp" in n] == []
