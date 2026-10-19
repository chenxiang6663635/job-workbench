# -*- coding: utf-8 -*-
"""数据根**迁移状态机**（B1）：相位、续跑、幂等、失败保留源、回滚。

为什么单独一个文件：`tests/test_dataroot_manifest.py` / `test_dataroot_semantics.py`
锁 plan / verify 两相依赖的判定原件，本文件锁**事务本身**——spec 决策 5 的
`plan → copy → verify → switch → done/failed`：

- **switch 是唯一生效点且最后写**：选择文件的 `data_root` 只在最后一次写里变成目标，
  之前每一个相位都仍指向源（源在 done 之前只读不删）；
- **copy-first / switch-second / delete-never**：旧目录一个字节都不动，`done` 之后
  它仍然完整（本机是真实数据，测出来的是承诺）；
- **断点续跑**：拷到一半崩（`_copy_file` 注入 OSError）、切到一半被硬杀
  （`_write_selection` 注入 KeyboardInterrupt）两条路径都能续；
- **幂等**：`root_id` / 选择已是目标即跳过；
- **失败语义**：任何阶段失败都不影响源目录可用，`state=failed` + 原因；
- **回滚**：把持久化选择指回旧根（两份目录都留着，不做自动删除 / 回搬）——**仅限
  在途 / 未生效**；迁移已生效（含「切换写成功、完成记录未落盘」的崩溃窗口）后拒绝
  指针式回滚，判别见 `dataroot_rollback`（P1-B 方案①）。

夹具全部落在 `tmp_path`，`APPDATA` 也隔离——**不碰真实 `personal/`**。
"""

import io
import json
import os

import pytest

from jobws_core import dataroot, dataroot_migrate as migrate, dataroot_manifest, pathres

WS = "personal"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """系统用户目录（选择文件 / 事务记录）与凭据形态都隔离到临时值。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.delenv(pathres.ENV_DATA_DIR, raising=False)
    # 凭据一律走明文形态：既让语义项确定，也**绝不碰**本机真实凭据管理器。
    monkeypatch.setenv("JOBWS_CREDENTIAL_STORE", "plaintext")


def _write(root, rel, text="内容\n"):
    path = os.path.join(str(root), rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _make_workspace(root, name=WS):
    ws = os.path.join(str(root), name)
    _write(ws, "config/profile.md", "# 档案\n")
    _write(ws, "config/directions/backend.md", "backend\n")
    _write(ws, "config/imap.json", json.dumps({"auth_ref": "job-workbench/x/imap"}))
    _write(ws, "05_投递追踪/tracker.csv", "id,公司\n1,示例公司A\n2,示例公司B\n")
    _write(ws, "03_面试准备/训练卡/项目一/02_数据从哪里来.md", "样本数口径\n")
    _write(ws, "02_简历工坊/简历.md", "简历正文\n")
    return ws


def _selection_file():
    return os.path.join(pathres.user_data_dir(), "state", "data-root.json")


def _read_selection():
    with io.open(_selection_file(), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _fingerprint(root):
    """目录的 `rel → sha256` 映射（比对源有没有被动过的硬证据）。"""
    manifest = dataroot_manifest.build_manifest(root)
    return {item["rel"]: item["sha256"] for item in manifest["entries"]}


@pytest.fixture()
def roots(tmp_path):
    source = tmp_path / "src"
    _make_workspace(source)
    return source, tmp_path / "out"


def _spy_on_writer(monkeypatch, recorder):
    """把「唯一写口」包一层记录器：相位顺序与生效点都能直接断言。"""
    real = migrate._write_selection

    def spy(root, phase, root_id=None):
        recorder.append((os.path.normcase(os.path.normpath(root)), phase))
        return real(root, phase, root_id)

    monkeypatch.setattr(migrate, "_write_selection", spy)


# --- plan：纯读、可拒 -----------------------------------------------------------

def test_plan_reads_everything_and_writes_nothing(roots):
    source, target = roots
    plan = migrate.plan(str(target), str(source))

    assert plan["ok"] is True and plan["reasons"] == []
    assert plan["source_root"] == str(source)
    assert plan["target_root"] == str(target)
    assert plan["source_workspace"] == os.path.join(str(source), WS)
    assert plan["staging"] == os.path.join(str(target), dataroot_manifest.STAGING_NAME, WS)
    assert [item["rel"] for item in plan["manifest"]["entries"]] == sorted(
        item["rel"] for item in plan["manifest"]["entries"])
    assert len(plan["manifest"]["entries"]) == 6

    # 纯读：选择文件与事务记录都不该出现，目标目录也不该被建
    assert not os.path.exists(_selection_file())
    assert not os.path.exists(migrate.journal_file())
    assert not os.path.exists(str(target))


def test_plan_rejects_usage_shape_without_writing(roots):
    source, _target = roots
    plan = migrate.plan(str(source), str(source))    # 目标 == 源
    assert plan["ok"] is False
    assert {item["kind"] for item in plan["reasons"]} == {"usage"}
    assert not os.path.exists(_selection_file())
    assert not os.path.exists(migrate.journal_file())


def test_plan_skips_when_selection_already_points_at_the_target(roots):
    source, target = roots
    os.makedirs(str(target))
    dataroot.write_persisted_selection(str(target))

    plan = migrate.plan(str(target), str(source))
    assert plan["ok"] is True and plan["already_current"] is True
    assert plan["manifest"] is None, "幂等路径不必再遍历 / 哈希源目录"
    with pytest.raises(ValueError):
        migrate.apply(plan)


def test_reverse_migration_is_misread_as_already_current(roots):
    """**特征化测试**（#304）——钉的是现状，不是期望行为。

    A→B 完成后，`_already_current()` 的第二分支（「目标已带**同一个** `root_id`」）
    必然命中：`root_id` 随数据一起搬走（spec 决策 2，另见
    `test_apply_keeps_root_id_across_the_move`），旧根 A 仍带着同一个身份。于是
    `jobws data-root migrate A` 会打印「已经是当前数据，无需迁移」并**一个字节都不动**，
    用户以为搬回去了，实际活动根仍是 B。这正是 #304 要修的东西；在此钉住现状，
    是为了防止它在没有协议的情况下悄悄变成别的行为（或修好之后没人知道它曾经是这样）。
    """
    source, target = roots
    # 真实场景的前提：A 曾是活动数据根，本来就带着根标记（`data-root set` 或上一次
    # 迁移写的）；迁移不会碰旧根，所以搬家后 A 的标记与 B 的标记带着**同一个** root_id。
    # 少这一步，A 根本没有标记、`_already_current` 的第二分支无从命中（我第一版就漏了）。
    dataroot.write_persisted_selection(str(source))

    migrate.apply(migrate.plan(str(target), str(source)))      # 完成一次 A→B 搬家

    assert migrate._already_current(str(source)) is True, \
        "反向迁移当前被误判为幂等（#304）：这条断言钉的是**现状**，#304 落地后应改为 False"


# --- apply：完整事务 ------------------------------------------------------------

def test_apply_completes_and_switches_only_at_the_end(roots, monkeypatch):
    source, target = roots
    before = _fingerprint(os.path.join(str(source), WS))
    calls = []
    _spy_on_writer(monkeypatch, calls)

    result = migrate.apply(migrate.plan(str(target), str(source)))

    assert result["status"] == "done", result
    # 相位顺序 + switch 是唯一生效点（只有最后一次写指向目标）
    assert [phase for _root, phase in calls] == [
        "planned", "copying", "verifying", "switching", "idle"]
    assert calls[-1] == (os.path.normcase(str(target)), "idle")
    assert [root for root, _phase in calls if root == os.path.normcase(str(target))] == [
        os.path.normcase(str(target))]

    # 数据真的到了目标，且**一个字节都不差**
    assert _fingerprint(os.path.join(str(target), WS)) == before
    assert os.path.isfile(os.path.join(str(target), WS, "config", "imap.json")), \
        "凭证配置文件必须随工作区一起搬（迁移不是分享，漏搬会退化成「还没配置」）"

    # 源目录只读不删
    assert _fingerprint(os.path.join(str(source), WS)) == before

    # 生效写的结果：选择指向目标、相位回到 idle、身份搬过去
    selection = _read_selection()
    assert selection["data_root"] == str(target)
    assert selection["migration_state"] == "idle"
    assert selection["selected_by"] == "migration"
    journal = migrate.read_journal()
    assert journal["root_id"] == selection["root_id"]
    assert dataroot.read_root_marker(str(target))["root_id"] == journal["root_id"]
    assert journal["completed_at"]
    assert not os.path.exists(os.path.join(str(target), dataroot_manifest.STAGING_NAME)), \
        "切换后暂存目录应被清掉（只在它确实空着时）"


def test_apply_keeps_root_id_across_the_move(roots):
    """`root_id` 是「同一份数据搬了家」的唯一判据——它必须跟着数据走。"""
    source, target = roots
    dataroot.write_persisted_selection(str(source))          # 源根先有身份
    root_id = _read_selection()["root_id"]

    migrate.apply(migrate.plan(str(target), str(source)))
    assert _read_selection()["root_id"] == root_id
    assert dataroot.read_root_marker(str(target))["root_id"] == root_id


def test_apply_refuses_a_plan_that_did_not_pass_preflight(roots):
    source, _target = roots
    plan = migrate.plan(str(source), str(source))
    with pytest.raises(ValueError):
        migrate.apply(plan)
    assert not os.path.exists(migrate.journal_file())


# --- 失败语义：源不受影响、相位如实 ----------------------------------------------

def test_copy_failure_keeps_source_and_marks_failed(roots, monkeypatch, caplog):
    source, target = roots
    before = _fingerprint(str(source))
    real_copy = migrate._copy_file
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] == 2:
            raise OSError("磁盘已满（模拟）")
        return real_copy(src, dst)

    monkeypatch.setattr(migrate, "_copy_file", flaky)
    result = migrate.apply(migrate.plan(str(target), str(source)))

    assert result["status"] == "failed"
    # 原文进日志、不进返回值（CodeQL #222/#223）：summary 会**原样回到 HTTP 响应**。
    # 这条从"reason 里必须有原文"改成了"reason 不许有原文"——旧断言正是泄漏本身。
    assert "磁盘已满" not in result["reason"], "异常原文进了返回值：%s" % result["reason"]
    assert result["reason"].startswith("IO 失败"), result["reason"]
    assert any("磁盘已满" in rec.getMessage() for rec in caplog.records), \
        "原文应进日志（否则排障只剩一句空话）"
    assert _read_selection()["migration_state"] == "failed"
    assert _read_selection()["data_root"] == str(source), "失败时选择仍指向源"
    assert _fingerprint(str(source)) == before, "任何阶段失败都不影响源目录"
    assert migrate.read_journal()["reason"]


def test_verify_rejects_a_corrupted_copy(roots, monkeypatch):
    source, target = roots

    def corrupt(src, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with io.open(dst, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("同样的长度但内容不同\n")

    monkeypatch.setattr(migrate, "_copy_file", corrupt)
    result = migrate.apply(migrate.plan(str(target), str(source)))

    assert result["status"] == "failed"
    assert "哈希" in result["reason"] or "大小" in result["reason"]
    assert not os.path.isdir(os.path.join(str(target), WS)), "校验没过就不许上位"


def test_verify_detects_source_drift(roots, monkeypatch):
    """拷贝期间源被改：拷出来的不是最新 → 报出来，绝不静默切换。"""
    source, target = roots
    real_copy = migrate._copy_file
    state = {"touched": False}

    def copy_then_touch(src, dst):
        result = real_copy(src, dst)
        if not state["touched"]:            # 只改第一个（理由里只该有一条这类问题）
            state["touched"] = True
            with io.open(src, "a", encoding="utf-8") as handle:
                handle.write("迁移期间的新写入\n")
        return result

    monkeypatch.setattr(migrate, "_copy_file", copy_then_touch)
    result = migrate.apply(migrate.plan(str(target), str(source)))

    assert result["status"] == "failed"
    assert "发生了变化" in result["reason"]
    assert _read_selection()["migration_state"] == "failed"


# --- 续跑 -----------------------------------------------------------------------

def test_resume_continues_with_diff_copy(roots, monkeypatch):
    source, target = roots
    before = _fingerprint(os.path.join(str(source), WS))
    real_copy = migrate._copy_file
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] == 3:
            raise OSError("进程被中断（模拟）")
        return real_copy(src, dst)

    monkeypatch.setattr(migrate, "_copy_file", flaky)
    assert migrate.apply(migrate.plan(str(target), str(source)))["status"] == "failed"

    monkeypatch.setattr(migrate, "_copy_file", real_copy)
    result = migrate.resume(apply=True)

    assert result["status"] == "done", result
    assert result["copy"]["reused"] == 2, "已落位的两个文件不该重拷（按清单 / 哈希差量续跑）"
    assert result["copy"]["copied"] == 4
    assert _fingerprint(os.path.join(str(target), WS)) == before
    assert _fingerprint(os.path.join(str(source), WS)) == before
    assert _read_selection()["data_root"] == str(target)


def test_resume_after_hard_kill_at_the_switch_only_redoes_the_switch(roots, monkeypatch):
    """切到一半被硬杀（rename 已发生、生效写还没写）→ 续跑只补最后一步。"""
    source, target = roots
    real_write = migrate._write_selection

    def kill_at_switch(root, phase, root_id=None):
        if os.path.normcase(root) == os.path.normcase(str(target)):
            raise KeyboardInterrupt("模拟硬杀（不落任何状态）")
        return real_write(root, phase, root_id)

    monkeypatch.setattr(migrate, "_write_selection", kill_at_switch)
    with pytest.raises(KeyboardInterrupt):
        migrate.apply(migrate.plan(str(target), str(source)))

    # 现场：数据已上位，相位停在 switching，选择仍指向源
    assert os.path.isdir(os.path.join(str(target), WS))
    assert not os.path.isdir(os.path.join(str(target), dataroot_manifest.STAGING_NAME))
    assert dataroot.describe(dataroot.FORM_MCP_ONLY)["migration_state"] == "switching"

    monkeypatch.setattr(migrate, "_write_selection", real_write)
    dry = migrate.resume()
    assert dry["status"] == "dry-run" and dry["steps"] == ["switch"]

    result = migrate.resume(apply=True)
    assert result["status"] == "done"
    assert result["copy"] is None, "这一轮不该再碰拷贝"
    assert _read_selection()["data_root"] == str(target)


def test_resume_without_a_transaction_is_a_noop(roots):
    assert migrate.resume() == {"status": "nothing"}
    assert migrate.resume(apply=True) == {"status": "nothing"}


def test_resume_after_completion_is_a_noop(roots):
    source, target = roots
    migrate.apply(migrate.plan(str(target), str(source)))
    assert migrate.resume(apply=True) == {"status": "nothing"}


# --- 回滚：在途可用；已生效则拒绝（P1-B 方案①） ----------------------------------------

def test_rollback_after_completion_is_refused(roots):
    """迁移完成（目标根已生效）→ 拒绝：不写选择、不改事务记录，并说清数据都在。"""
    source, target = roots
    migrate.apply(migrate.plan(str(target), str(source)))
    selection_before = _read_selection()
    journal_before = migrate.read_journal()

    dry = migrate.rollback()                   # 演练也要如实预告，不给假希望
    assert dry["status"] == "refused", dry
    assert dry["source_root"] == str(source) and dry["target_root"] == str(target)
    assert dry["target_kept"] is True and dry["staging_kept"] is False
    assert "completed" in dry["signals"]

    result = migrate.rollback(apply=True)
    assert result["status"] == "refused", result
    assert "没有被删除" in result["reason"] and "旧根" in result["reason"]
    assert "不支持反向迁移" in result["reason"], \
        "搬回旧位置当前不可行：提示必须如实说明（#304），而不是指一条走不通的路"
    assert _read_selection() == selection_before, "拒绝时一个字节都不该写"
    assert migrate.read_journal() == journal_before
    assert dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).path == str(target)


def test_rollback_is_refused_in_the_switch_crash_window(roots, monkeypatch):
    """**切换生效写已发生、完成记录未落盘**（崩在两者之间）也不许指针式回滚。"""
    source, target = roots
    real_write = migrate._write_journal

    def die_before_completion(journal):
        if journal.get("completed_at"):
            raise OSError("模拟硬杀：完成记录没来得及落盘")
        return real_write(journal)

    monkeypatch.setattr(migrate, "_write_journal", die_before_completion)
    with pytest.raises(OSError):
        migrate.apply(migrate.plan(str(target), str(source)))

    # 现场：选择已指向目标、相位回到 idle、事务记录里没有完成位
    assert _read_selection()["data_root"] == str(target)
    assert _read_selection()["migration_state"] == "idle"
    assert migrate.read_journal()["completed_at"] is None
    assert os.path.isdir(os.path.join(str(target), WS))

    result = migrate.rollback(apply=True)
    assert result["status"] == "refused", result
    assert "switch_landed_unfinished" in result["signals"]
    assert _read_selection()["data_root"] == str(target), "拒绝时不许动指针"


def test_rollback_refusal_is_idempotent(roots):
    """重复回滚：第二次仍然拒绝，且两次都不碰盘上的任何状态。"""
    source, target = roots
    migrate.apply(migrate.plan(str(target), str(source)))

    first = migrate.rollback(apply=True)
    snapshot = (_read_selection(), migrate.read_journal())
    second = migrate.rollback(apply=True)
    assert first["status"] == second["status"] == "refused"
    assert (_read_selection(), migrate.read_journal()) == snapshot
    assert migrate.resume(apply=True)["status"] == "nothing", "被拒 ≠ 事务又在途了"


def test_rollback_refuses_after_new_records_land_in_the_target(roots):
    """成功迁移后在目标根新增了记录再回滚：拒绝——否则那些记录看起来凭空消失。"""
    source, target = roots
    migrate.apply(migrate.plan(str(target), str(source)))
    record = _write(target, "%s/05_投递追踪/tracker.csv" % WS, "id,公司\n9,迁移后的新记录\n")

    result = migrate.rollback(apply=True)
    assert result["status"] == "refused", result
    with io.open(record, "r", encoding="utf-8") as handle:
        assert "迁移后的新记录" in handle.read()
    assert dataroot.resolve_data_root(dataroot.FORM_MCP_ONLY).path == str(target)


def test_rollback_before_the_switch_only_abandons_the_transaction(roots, monkeypatch):
    """在途 / 失败的事务照旧可以回滚：选择本就指着旧根，回滚是幂等收尾。"""
    source, target = roots

    def boom(src, dst):
        raise OSError("中断")

    monkeypatch.setattr(migrate, "_copy_file", boom)
    assert migrate.apply(migrate.plan(str(target), str(source)))["status"] == "failed"

    dry = migrate.rollback()
    assert dry["status"] == "dry-run"
    assert dry["to"] == str(source)
    assert dry["target_root"] == str(target)
    assert _read_selection()["migration_state"] == "failed", "演练不改任何东西"

    result = migrate.rollback(apply=True)
    assert result["status"] == "noop"
    assert _read_selection()["data_root"] == str(source)
    assert _read_selection()["migration_state"] == "idle"
    assert migrate.read_journal()["rolled_back_at"]


def test_rollback_after_a_hard_kill_at_the_switch_is_still_allowed(roots, monkeypatch):
    """硬杀在 switch 里（数据已上位、指针还没翻）仍是**在途**——不许误拒。

    这是判据里 `identity_on_target`（本事务的 `root_id` 已钉在目标根上）唯一能
    单独成立的现场：它只作佐证、不作拒绝依据，否则「中断后回滚」这条通道就没了。
    """
    source, target = roots
    real_write = migrate._write_selection

    def kill_at_switch(root, phase, root_id=None):
        if os.path.normcase(root) == os.path.normcase(str(target)):
            raise KeyboardInterrupt("模拟硬杀（不落任何状态）")
        return real_write(root, phase, root_id)

    monkeypatch.setattr(migrate, "_write_selection", kill_at_switch)
    with pytest.raises(KeyboardInterrupt):
        migrate.apply(migrate.plan(str(target), str(source)))

    before_source = _fingerprint(os.path.join(str(source), WS))
    before_target = _fingerprint(os.path.join(str(target), WS))
    result = migrate.rollback(apply=True)      # 现场：相位 switching、选择仍指向源
    assert result["status"] == "noop", result
    assert _read_selection()["data_root"] == str(source)
    # 不删、不回搬：两份目录都原样留着（允许的回滚也只动选择文件与事务记录）
    assert _fingerprint(os.path.join(str(source), WS)) == before_source
    assert _fingerprint(os.path.join(str(target), WS)) == before_target
    assert result["target_kept"] is True and result["staging_kept"] is False


# --- 与诊断面 / 隐私的接口 -------------------------------------------------------

def test_describe_reports_the_phase_from_the_state_file(roots, monkeypatch):
    """`describe().migration_state` 读真值（A3 时期是占位 "idle"）。"""
    source, target = roots

    def boom(src, dst):
        raise OSError("中断")

    monkeypatch.setattr(migrate, "_copy_file", boom)
    migrate.apply(migrate.plan(str(target), str(source)))
    assert dataroot.describe(dataroot.FORM_MCP_ONLY)["migration_state"] == "failed"


def test_journal_never_contains_plaintext_secrets(roots):
    """事务记录会落盘到 state/：只许出现**引用**，绝不许出现密文。"""
    source, target = roots
    _write(str(source), "%s/config/imap.json" % WS,
           json.dumps({"auth_ref": "job-workbench/x/imap", "password": "明文授权码"}))
    migrate.apply(migrate.plan(str(target), str(source)))

    with io.open(migrate.journal_file(), "r", encoding="utf-8") as handle:
        text = handle.read()
    # journal 只装清单（rel/size/sha256）与元数据：隐私不变量是「明文绝不入册」；
    # 引用串属工作区内容，由语义校验在暂存侧核对（dataroot_semantics）。
    assert "明文授权码" not in text
    assert "auth_ref" not in text


# --- 计划指纹（预览 → 确认协议的凭据）--------------------------------------------

def test_plan_fingerprint_changes_when_source_changes(roots):
    """源数据在预览与确认之间变过 → 指纹必须变——旧确认不许沿用。"""
    source, target = roots
    token = migrate.plan_fingerprint(migrate.plan(str(target), str(source)))

    _write(source, "personal/02_简历工坊/预览之后的新文件.md", "迁移前被改\n")
    plan2 = migrate.plan(str(target), str(source))
    assert migrate.plan_fingerprint(plan2) != token


def test_plan_fingerprint_is_stable_for_the_same_plan(roots):
    source, target = roots
    once = migrate.plan_fingerprint(migrate.plan(str(target), str(source)))
    again = migrate.plan_fingerprint(migrate.plan(str(target), str(source)))
    assert once == again, "同一份计划两次计算必须同指纹（确定性）"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
