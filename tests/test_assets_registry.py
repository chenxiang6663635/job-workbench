# -*- coding: utf-8 -*-
"""资产注册表真源（tools/assets_registry.py，issue #205）的单元测试。

钉四件事：① 两份 JSON 由真源生成（幂等：write 之后 check 必绿）；② 集合与
**计数**都从磁盘派生（加技能目录 → 清单与描述数量一起变）；③ 手改生成物 /
未登记顺序的命令会被抓；④ 版本号取自 `web/electron/package.json`（唯一真源）。
"""

import io
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import assets_registry  # noqa: E402

PLUGIN_DIR = ".codebuddy-plugin"


ALL_COMMANDS = ("today", "apply-pack", "retro", "bank", "jd")


def _repo(tmp_path, skills=("jwb-a", "jwb-b"), commands=ALL_COMMANDS,
          agents=("cross-end-audit.md",), version="1.0.0"):
    """最小仓库骨架：三类资产目录 + 版本真值源 + 空的插件目录。"""
    for name in skills:
        (tmp_path / "skills" / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "commands").mkdir(exist_ok=True)
    for name in commands:
        (tmp_path / "commands" / ("%s.md" % name)).write_text("x\n", encoding="utf-8")
    (tmp_path / "agents").mkdir(exist_ok=True)
    for name in agents:
        (tmp_path / "agents" / name).write_text("x\n", encoding="utf-8")
    pkg_dir = tmp_path / "web" / "electron"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({"version": version}), encoding="utf-8")
    (tmp_path / PLUGIN_DIR).mkdir(exist_ok=True)
    return str(tmp_path)


def _read(repo, name):
    return io.open(os.path.join(repo, PLUGIN_DIR, name),
                   encoding="utf-8").read()


def test_write_then_check_is_clean(tmp_path):
    """生成幂等：write 之后 check 必绿（CI 的漂移闸以它为前提）。"""
    repo = _repo(tmp_path)
    assets_registry.write_all(repo)
    assert assets_registry.check_all(repo) == []


def test_manifest_lists_disk_assets_and_derives_counts(tmp_path):
    """清单从磁盘派生、描述数量从清单派生——加一个技能目录全都跟着变。"""
    repo = _repo(tmp_path, skills=("jwb-a", "jwb-b", "jwb-c"),
                 agents=("cross-end-audit.md", "resume-jd-gap.md"))
    assets_registry.write_all(repo)

    plugin = json.loads(_read(repo, "plugin.json"))
    assert plugin["skills"] == ["./skills/jwb-a", "./skills/jwb-b", "./skills/jwb-c"]
    assert plugin["agents"] == ["./agents/cross-end-audit.md", "./agents/resume-jd-gap.md"]
    assert plugin["commands"] == [
        "./commands/today.md", "./commands/apply-pack.md", "./commands/retro.md",
        "./commands/bank.md", "./commands/jd.md"]
    assert "技能 3 个、命令 5 个、子代理 2 个" in plugin["description"]

    market = json.loads(_read(repo, "marketplace.json"))
    assert market["plugins"][0]["skills"] == plugin["skills"]
    assert "3 个技能" in market["description"]
    assert "3 skills" in market["description_en"]


def test_commands_keep_product_order_not_alphabetical(tmp_path):
    """命令顺序是产品决策（COMMAND_ORDER），不是字母序。"""
    repo = _repo(tmp_path, commands=("jd", "retro", "today", "bank", "apply-pack"))
    assets_registry.write_all(repo)
    plugin = json.loads(_read(repo, "plugin.json"))
    assert plugin["commands"] == [
        "./commands/today.md", "./commands/apply-pack.md", "./commands/retro.md",
        "./commands/bank.md", "./commands/jd.md"]


def test_version_flows_from_electron_package_json(tmp_path):
    """版本号取自唯一真源（web/electron/package.json），不手写。"""
    repo = _repo(tmp_path, version="26.10.0")
    assets_registry.write_all(repo)
    assert json.loads(_read(repo, "plugin.json"))["version"] == "26.10.0"


def test_manually_edited_manifest_is_flagged(tmp_path):
    """手改生成物（漂移）→ check 报，并指向 --write。"""
    repo = _repo(tmp_path)
    assets_registry.write_all(repo)

    path = os.path.join(repo, PLUGIN_DIR, "plugin.json")
    text = io.open(path, encoding="utf-8").read().replace("jwb-a", "jwb-zz")
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)

    problems = assets_registry.check_all(repo)
    assert any("plugin.json" in p and "漂移" in p for p in problems), problems


def test_unregistered_command_is_flagged(tmp_path):
    """磁盘加了命令但没登记展示顺序 → 真源自身报错（刻意的摩擦）。"""
    repo = _repo(tmp_path, commands=("today", "jd", "brand-new"))
    problems = assets_registry.check_all(repo)
    assert any("brand-new" in p and "COMMAND_ORDER" in p for p in problems), problems


def test_order_entry_without_file_is_flagged(tmp_path):
    """COMMAND_ORDER 登记了磁盘上不存在的命令 → 也报（防登记腐化）。"""
    repo = _repo(tmp_path, commands=("today",))
    problems = assets_registry.check_all(repo)
    assert any("bank" in p or "jd" in p for p in problems), problems


def test_missing_version_source_is_reported(tmp_path):
    """读不到版本真源（package.json 缺失）→ 报一条根因，不是崩。"""
    repo = _repo(tmp_path)
    os.remove(os.path.join(repo, "web", "electron", "package.json"))
    problems = assets_registry.check_all(repo)
    assert problems and "读真源失败" in problems[0], problems


def test_real_repo_is_in_sync():
    """真实仓库：两份清单与真源一致（本批交付后必须成立）。"""
    assert assets_registry.check_all(ROOT_DIR) == []
