# -*- coding: utf-8 -*-
"""迁移的**清单**与**目标侧预检**（B1）：plan 相依赖的判定原件。

为什么单独一个文件：`tests/test_dataroot_migrate.py` 锁状态机本身（相位、续跑、回滚、
switch 唯一生效点），本文件锁它依赖的原件——

- 清单怎么算：相对路径形状、大小 + sha256 策略、**跳过哪些运行时产物**（锁文件与
  原子写临时名不是数据，且它们会在迁移期间变动，进清单只会制造假「源已漂移」）；
- preflight 拒什么：目标空间（spec §七风险 3 的跨卷）、长路径、大小写冲突、
  junction / symlink、越界与非法名字（spec §七风险 4：与
  `web/backend/snapshot_entries.py` 的「先归一化再判定」同族纪律）；
- **一条刻意的边界**：中文目录名**必须支持**（工作区里到处都是 `03_面试准备` 这类
  目录，拒绝它们等于迁移不可用）；只有「本机文件系统编码不了」的路径才拒绝。

术语见 `docs/specs/2026-10-04-single-canonical-data-root.md` 决策 5 与 §七。
"""

import hashlib
import os

import pytest

from jobws_core import dataroot_manifest as manifest_mod

WS = "personal"


def _write(root, rel, text="内容\n"):
    path = os.path.join(str(root), rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _make_workspace(root, name=WS):
    """一个「像真实工作区」的源目录：中文目录名 + 追踪表 + 配置。"""
    ws = os.path.join(str(root), name)
    _write(ws, "config/profile.md", "# 档案\n")
    _write(ws, "config/directions/backend.md", "backend\n")
    _write(ws, "05_投递追踪/tracker.csv", "id,公司\n1,示例公司A\n2,示例公司B\n")
    _write(ws, "03_面试准备/训练卡/项目一/02_数据从哪里来.md", "样本数口径\n")
    return ws


def _symlink(source, link):
    try:
        os.symlink(source, link)
    except (OSError, NotImplementedError) as exc:  # Windows 需开发者模式 / 提权
        pytest.skip("本机不允许创建符号链接：%s" % exc)


def _entry(rel, size=1):
    return {"rel": rel, "size": size, "sha256": "0" * 64}


def _manifest(entries, links=(), skipped=()):
    return {"entries": list(entries), "links": list(links),
            "skipped": list(skipped),
            "total_bytes": sum(item["size"] for item in entries)}


# --- 相对路径：先归一化再判定 ---------------------------------------------------

def test_normalize_keeps_one_shape():
    """`a\\b` / `a/./b` / `a//b` 归一成同一个形状（与 snapshot_entries 同口径）。"""
    assert manifest_mod.normalize_rel("a\\b") == "a/b"
    assert manifest_mod.normalize_rel("a/./b") == "a/b"
    assert manifest_mod.normalize_rel("a//b") == "a/b"
    assert manifest_mod.normalize_rel("a/b") == "a/b"


@pytest.mark.parametrize("rel", [
    "", ".", "..", "../x", "a/../b", "a/..", "/abs/x", "C:/x", "a/b:c",
    "x.md.", "x.md ", "a//../b",
])
def test_rel_problem_rejects_escapes_and_illegal_shapes(rel):
    """越界、盘符、ADS、尾随空格/点一律拒绝——**归一化之前先判 `..`**。

    与 `web/backend/snapshot_entries.py:80-111` 同族：先归一化再判定，但 `..` 必须在
    归一化**之前**判——`a/../b` 归一化后是合法的 `b`，静默放行就等于放走了一次越界。
    """
    assert manifest_mod.rel_problem(rel), "%r 应被拒绝" % rel


@pytest.mark.parametrize("rel", [
    "config/profile.md",
    "05_投递追踪/tracker.csv",
    "03_面试准备/训练卡/项目一/02_数据从哪里来，输入和标签是什么？.md",
    "99_归档/快照(2026-10-04).zip",
])
def test_rel_problem_accepts_chinese_and_nested_names(rel):
    """中文目录名是**正常数据**（工作区到处都是），不是要拒绝的对象。"""
    assert manifest_mod.rel_problem(rel) is None


def test_rel_problem_rejects_unencodable_path():
    """本机文件系统编码不了的路径（代理项）才拒绝——「中文」与「编码不了」是两件事。"""
    assert manifest_mod.rel_problem("坏\udcff.md")
    assert manifest_mod.rel_problem("坏名字.md") is None


# --- 清单：大小 / 哈希 / 跳过项 -------------------------------------------------

def test_build_manifest_lists_sorted_entries_with_hash(tmp_path):
    ws = _make_workspace(tmp_path)
    manifest = manifest_mod.build_manifest(ws)

    rels = [item["rel"] for item in manifest["entries"]]
    assert rels == sorted(rels), "清单顺序必须稳定（按 rel 排序）"
    assert "config/profile.md" in rels
    assert "03_面试准备/训练卡/项目一/02_数据从哪里来.md" in rels

    by_rel = {item["rel"]: item for item in manifest["entries"]}
    profile = by_rel["config/profile.md"]
    assert profile["size"] == len("# 档案\n".encode("utf-8"))
    assert profile["sha256"] == hashlib.sha256("# 档案\n".encode("utf-8")).hexdigest()
    assert manifest["total_bytes"] == sum(item["size"] for item in manifest["entries"])
    assert manifest["links"] == []


def test_build_manifest_skips_runtime_artifacts(tmp_path):
    """锁文件 / 原子写临时名 / 字节码不入清单，但**如实列进 skipped**。

    它们会在迁移期间被别的进程创建或删除，进清单只会把「源已漂移」报成假故障。
    """
    ws = _make_workspace(tmp_path)
    _write(ws, "05_投递追踪/tracker.lock", "")
    _write(ws, "config/imap.lock", "")
    _write(ws, "05_投递追踪/.jobws_tmp_tracker.csv", "half")
    _write(ws, "config/imap.json.tmp", "{}")
    _write(ws, "03_面试准备/训练卡/__pycache__/x.pyc", "bytecode")

    manifest = manifest_mod.build_manifest(ws)
    rels = {item["rel"] for item in manifest["entries"]}
    assert "05_投递追踪/tracker.lock" not in rels
    assert "05_投递追踪/.jobws_tmp_tracker.csv" not in rels
    assert "03_面试准备/训练卡/__pycache__/x.pyc" not in rels
    skipped = set(manifest["skipped"])
    assert {"05_投递追踪/tracker.lock", "config/imap.lock"} <= skipped
    assert "03_面试准备/训练卡/__pycache__" in skipped  # 整目录跳过（不再逐条列 .pyc）
    assert not any(rel.endswith(".pyc") for rel in rels)


def test_build_manifest_records_links_without_following(tmp_path):
    """符号链接记进 `links` 且**不跟随**——跟随会把外面的大树拖进来，甚至成环。"""
    ws = _make_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside, "大文件.md", "不该被搬走\n")
    _symlink(str(outside), os.path.join(ws, "03_面试准备", "链接目录"))

    manifest = manifest_mod.build_manifest(ws)
    assert manifest["links"], "符号链接必须被记下来（由预检拒绝）"
    assert not any("大文件.md" in item["rel"] for item in manifest["entries"])


def test_build_manifest_records_links_without_following_via_injection(tmp_path, monkeypatch):
    """本机建不出符号链接时的**等价锁**：注入一个「链接目录」，遍历逻辑照样要对。

    真链接那条用例在 Windows（无开发者模式）会被 skip，CI 的 Linux 侧才真跑；
    这里把 `is_link` 指到某个真实目录上，确保「链接不入清单、也不递归」不是盲区。
    """
    ws = _make_workspace(tmp_path)
    fake = os.path.join(ws, "03_面试准备", "链接目录")
    _write(fake, "外面的大文件.md", "不该被搬走\n")
    real_is_link = manifest_mod.is_link
    monkeypatch.setattr(
        manifest_mod, "is_link",
        lambda path: os.path.normcase(os.path.normpath(path))
        == os.path.normcase(os.path.normpath(fake)) or real_is_link(path))

    manifest = manifest_mod.build_manifest(ws)
    assert manifest["links"] == ["03_面试准备/链接目录"]
    assert not any("外面的大文件" in item["rel"] for item in manifest["entries"])


# --- 预检：用法形状 ------------------------------------------------------------

def test_preflight_usage_shape_rejections(tmp_path):
    """空 / 相对 / 同一根 / 互相嵌套——这四条是**用法错误**（CLI 退出码 2）。"""
    source = tmp_path / "src"
    _make_workspace(source)

    cases = [
        (str(source), ""),                                    # 空目标
        (str(source), "relative/target"),                     # 相对目标
        (str(source), str(source)),                           # 目标 == 源
        (str(source), os.path.join(str(source), "inner")),    # 目标在源内部
        (str(source), str(tmp_path)),                         # 源在目标内部
    ]
    for src, target in cases:
        reasons = manifest_mod.preflight(src, target, WS, _manifest([_entry("a.md")]))
        assert reasons, (src, target)
        assert {item["kind"] for item in reasons} == {"usage"}, (src, target, reasons)


# --- 预检：目标侧阻塞 ----------------------------------------------------------

def _blocked(tmp_path, source_root=None, target_root=None, entries=None, **kwargs):
    source = str(source_root or tmp_path / "src")
    if source_root is None:
        _make_workspace(source)
    target = str(target_root or tmp_path / "out")
    manifest = _manifest(entries if entries is not None else [_entry("a.md")])
    return manifest_mod.preflight(source, target, WS, manifest, **kwargs)


def test_preflight_accepts_a_normal_chinese_workspace(tmp_path):
    """正例：中文目录 + 目标还不存在 → 一条理由都不该有。"""
    assert _blocked(tmp_path) == []


def test_preflight_rejects_missing_source_workspace(tmp_path):
    reasons = manifest_mod.preflight(str(tmp_path / "nope"), str(tmp_path / "out"),
                                    WS, _manifest([]))
    assert reasons and all(item["kind"] == "blocked" for item in reasons)
    assert any("源工作区不存在" in item["message"] for item in reasons)


def test_preflight_rejects_existing_target_workspace(tmp_path):
    """目标已有同名工作区 → 拒绝（本命令不合并两份工作区）。"""
    source, target = tmp_path / "src", tmp_path / "out"
    _make_workspace(source)
    _make_workspace(target)
    reasons = _blocked(tmp_path, source_root=source, target_root=target)
    assert any("已有同名工作区" in item["message"] for item in reasons)


def test_preflight_rejects_workspace_leftover_in_staging(tmp_path):
    """暂存目录存在但不属于本次事务（没有 journal）→ 拒绝，绝不覆盖别人的目录。"""
    source, target = tmp_path / "src", tmp_path / "out"
    _make_workspace(source)
    _make_workspace(os.path.join(str(target), manifest_mod.STAGING_NAME))
    reasons = _blocked(tmp_path, source_root=source, target_root=target)
    assert any("暂存目录" in item["message"] for item in reasons)


def test_preflight_rejects_foreign_marker_in_target(tmp_path):
    """目标根已带另一份数据的身份（root_id 不同）→ 拒绝。"""
    import io
    import json

    source, target = tmp_path / "src", tmp_path / "out"
    _make_workspace(source)
    target.mkdir()
    with io.open(os.path.join(str(target), ".jobws-root.json"), "w",
                 encoding="utf-8") as handle:
        handle.write(json.dumps({"format": 1, "root_id": "other-data"}))

    reasons = _blocked(tmp_path, source_root=source, target_root=target)
    assert any("root_id" in item["message"] for item in reasons)


def test_preflight_rejects_insufficient_space(tmp_path, monkeypatch):
    """目标侧空间不足 → 拒绝（暂存也在目标卷上，所以同卷同样要算）。"""
    monkeypatch.setattr(manifest_mod, "free_bytes", lambda path: 1024)
    reasons = _blocked(tmp_path, entries=[_entry("big.bin", size=10 * 1024 * 1024)])
    assert any("空间不足" in item["message"] for item in reasons)


def test_preflight_rejects_too_long_target_path(tmp_path, monkeypatch):
    """超长路径 → 拒绝：判定按**暂存路径**算（它是迁移期最长的那条）。"""
    monkeypatch.setattr(manifest_mod, "MAX_PATH", 60)
    long_rel = "03_面试准备/" + "深/" * 12 + "卡.md"
    reasons = _blocked(tmp_path, entries=[_entry(long_rel)])
    assert any("路径过长" in item["message"] for item in reasons)


def test_preflight_rejects_case_collision(tmp_path):
    """仅大小写不同的两条会在不敏感卷上互相覆盖 → 拒绝。"""
    reasons = _blocked(tmp_path, entries=[_entry("a/报告.md"), _entry("A/报告.md")])
    assert any("大小写" in item["message"] for item in reasons)


def test_preflight_rejects_links_and_illegal_names(tmp_path):
    linked = _manifest([_entry("a.md")], links=["03_面试准备/链接目录"])
    assert any("符号链接" in item["message"]
               for item in manifest_mod.preflight(str(tmp_path / "src"),
                                                  str(tmp_path / "out"), WS, linked))

    illegal = _manifest([_entry("a/b.md.")])
    reasons = manifest_mod.preflight(str(tmp_path / "src"), str(tmp_path / "out"),
                                     WS, illegal)
    assert any("非法" in item["message"] or "条目" in item["message"]
               for item in reasons)


def test_preflight_uses_the_injected_workspace_name(tmp_path):
    """工作区名参与判定（不是写死 `personal`）——第三方工作区同样能迁移。"""
    source, target = tmp_path / "src", tmp_path / "out"
    _make_workspace(source, "my_job_hunt")
    reasons = manifest_mod.preflight(str(source), str(target), "my_job_hunt",
                                     _manifest([_entry("a.md")]))
    assert reasons == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
