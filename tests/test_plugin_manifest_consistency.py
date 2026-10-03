# -*- coding: utf-8 -*-
"""插件清单一致性校验的**集成层**测试（2026-09-25 建立，2026-10-02 随 #205 改造）。

历史语义：「三份手写副本互校」——plugin.json.skills / marketplace.json 的
plugins[0].skills / skills/ 磁盘目录，外加描述里的技能数量（`jwb-domain-setup`
加入时 marketplace 漏改 8 vs 9，触发了那套校验，PR #200）。

现状（issue #205）：两份 JSON 已改为**生成物**（真源在 tools/assets_registry.py），
本文件相应改为「生成物与真源」的集成验证——registry 自身的单元逻辑（生成幂等、
计数派生、命令顺序摩擦、版本流动）在 `test_assets_registry.py`。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import assets_registry  # noqa: E402
from check_plugin_assets import manifest_consistency_problems  # noqa: E402

ALL_COMMANDS = ("today", "apply-pack", "retro", "bank", "jd")


def _synced_repo(tmp_path, skills=("jwb-a", "jwb-b"), commands=ALL_COMMANDS,
                 version="1.0.0"):
    """造一份「真源 + 已生成」的仓库——与 check_all 的期望一致。"""
    for name in skills:
        (tmp_path / "skills" / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "commands").mkdir(exist_ok=True)
    for name in commands:
        (tmp_path / "commands" / ("%s.md" % name)).write_text("x\n", encoding="utf-8")
    (tmp_path / "agents").mkdir(exist_ok=True)
    (tmp_path / "agents" / "cross-end-audit.md").write_text("x\n", encoding="utf-8")
    pkg = tmp_path / "web" / "electron"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "package.json").write_text(json.dumps({"version": version}),
                                      encoding="utf-8")
    (tmp_path / ".codebuddy-plugin").mkdir(exist_ok=True)
    assets_registry.write_all(str(tmp_path))
    return str(tmp_path)


def test_synced_manifests_pass(tmp_path):
    """生成物与真源一致 → 空（CI 绿的条件）。"""
    assert manifest_consistency_problems(_synced_repo(tmp_path)) == []


def test_hand_edited_manifest_is_flagged(tmp_path):
    """手改生成物（技能名被改掉）→ 报漂移，并指明重新生成的命令。"""
    repo = _synced_repo(tmp_path)
    path = os.path.join(repo, ".codebuddy-plugin", "plugin.json")
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("jwb-a", "jwb-ghost"))

    problems = manifest_consistency_problems(repo)
    assert any("plugin.json" in p and "漂移" in p for p in problems), problems


def test_broken_manifest_is_reported(tmp_path):
    """生成物坏掉（非法 JSON）→ 报出来，不静默通过。"""
    repo = _synced_repo(tmp_path)
    with open(os.path.join(repo, ".codebuddy-plugin", "marketplace.json"),
              "w", encoding="utf-8") as handle:
        handle.write("{ 坏")

    problems = manifest_consistency_problems(repo)
    assert any("marketplace.json" in p for p in problems), problems


def test_missing_version_source_is_reported(tmp_path):
    """版本真值源缺失 → 报一条根因（校验器自身的失败同样要响亮）。"""
    repo = _synced_repo(tmp_path)
    os.remove(os.path.join(repo, "web", "electron", "package.json"))

    problems = manifest_consistency_problems(repo)
    assert problems and "读真源失败" in problems[0], problems
