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
