# -*- coding: utf-8 -*-
"""两段式写入协议（`tools/approval.py`）的回归。

三条硬性逐条钉住：**预览不落盘**、**令牌一次性**、**令牌过期 / 绑定工作区 /
防篡改**。这些不是"读一遍代码就能放心"的性质——写错一条的后果是用户数据被写
两次，或一份确认被用到了另一个工作区上，而且都不会报错。

这里只用**假操作**（monkeypatch 进 `_OPERATIONS`）测协议本身；真实操作的
落盘行为在 `tests/test_approval_flow.py` 里用字节级断言钉。
"""

import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import approval  # noqa: E402


@pytest.fixture
def tokens(tmp_path, monkeypatch):
    """把令牌目录挪进 tmp_path：不碰真实临时目录，也便于直接检查文件。"""
    store = tmp_path / "tokens"
    store.mkdir()
    # 打到**包内**模块上：协议外壳搬进 jobws_core 后，preview/apply 读的是那里的
    # 模块全局，patch 转发层（本模块）不改变调用点——本仓库反复踩过的那条坑，
    # 同 `tests/test_cli_surface.py` 打 `tracker._core.WORKSPACE` 的写法。
    monkeypatch.setattr(approval._shell, "_store_dir", lambda: str(store))
    return store


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "05_投递追踪").mkdir(parents=True)
    return ws


@pytest.fixture
def fake_op(monkeypatch):
    """注册一个只记账、不落盘的假操作，用来观察 apply 到底调没调。"""
    calls = []
    monkeypatch.setitem(
        approval._OPERATIONS, "test.noop",
        lambda payload, workspace: calls.append((payload, workspace)) or {"summary": "ok"})
    return calls


def _preview(workspace, **overrides):
    args = {
        "operation": "test.noop",
        "workspace": str(workspace),
        "payload": {"fields": {"公司": "示例公司", "岗位": "示例岗位"}},
        "summary": "新增投递：示例公司 示例岗位（待投）",
        "diff": ["| 字段 | 值 |", "|---|---|"],
        "targets": [str(workspace / "05_投递追踪" / "tracker.csv")],
    }
    args.update(overrides)
    return approval.preview(**args)


def test_preview_returns_token_and_touches_nothing(tokens, workspace):
    """预览返回令牌与展示要素；工作区**一个文件都不该多**。"""
    before = sorted(os.listdir(str(workspace)))

    result = _preview(workspace)

    assert approval._TOKEN_RE.match(result["token"])
    assert result["operation"] == "test.noop"
    assert result["summary"] and result["diff"] and result["targets"]
    assert result["expires_at"] > time.time()
    assert sorted(os.listdir(str(workspace))) == before, "预览阶段不许在工作区里建任何东西"


def test_apply_calls_the_operation_once(tokens, workspace, fake_op):
    result = _preview(workspace)

    out = approval.apply(result["token"])

    assert out["summary"] == "ok"
    assert len(fake_op) == 1
    assert fake_op[0][0] == {"fields": {"公司": "示例公司", "岗位": "示例岗位"}}


def test_token_is_single_use(tokens, workspace, fake_op):
    """重放第二次必须被拒——这是"一次性"的全部意义。"""
    result = _preview(workspace)
    approval.apply(result["token"])

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])

    assert "找不到这个令牌" in str(ei.value)
    assert len(fake_op) == 1, "第二次不该再调操作"


def test_expired_token_is_rejected(tokens, workspace, fake_op):
    result = _preview(workspace, ttl=-1)

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])

    assert "过期" in str(ei.value)
    assert not fake_op

    # 语义（2026-10-09 独立审查 MAJOR 后收紧）：**纯校验**（过期/绑定/指纹/操作
    # 登记）全部前置到"取走令牌"之前——校验失败不烧牌，第二次拿到的仍是"过期"。
    # 不变量没有松动：**执行 handler 之前令牌必已被原子取走**（重放与并发依旧
    # 只有一个赢家），只是"不执行 handler 的纯失败路径"不再焚牌——旧实现先
    # os.remove 再校验，会留下含明文载荷的 .running 孤儿（rename 迁移的漏项）。
    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])
    assert "过期" in str(ei.value)


def test_failed_validation_leaves_no_running_orphan(tokens, workspace, fake_op):
    """claim 后的早退分支曾是孤儿源头：校验前置后不许再出现 .running（独立审查 MAJOR）。

    三条失败路径各来一次：过期 / 未知操作 / 指纹被改——每次失败后令牌目录里
    都不得残留 `.running`（含明文业务载荷）。
    """
    # ① 过期
    expired = _preview(workspace, ttl=-1)
    with pytest.raises(approval.ApprovalError):
        approval.apply(expired["token"])

    # ② 未知操作（改令牌记录里的 operation）
    data = _preview(workspace)
    path = approval._token_path(data["token"])
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    record["operation"] = "no.such.op"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    with pytest.raises(approval.ApprovalError):
        approval.apply(data["token"])

    # ③ 指纹被改（载荷与记录里的指纹对不上）
    data2 = _preview(workspace)
    path2 = approval._token_path(data2["token"])
    with open(path2, encoding="utf-8") as fh:
        record2 = json.load(fh)
    record2["payload"] = {"fields": {"公司": "被改过"}}
    with open(path2, "w", encoding="utf-8") as fh:
        json.dump(record2, fh)
    with pytest.raises(approval.ApprovalError):
        approval.apply(data2["token"])

    leftovers = [p.name for p in tokens.iterdir() if p.name.endswith(".running")]
    assert leftovers == [], "失败路径留下孤儿：%s" % leftovers


def test_lock_timeout_keeps_token_for_retry(tokens, workspace, monkeypatch):
    """锁等待超时不烧令牌——「稍后重试」必须字面成立（2026-10-09 审计 1.1-4）。

    修复前：apply 先 os.remove 令牌再执行，TimeoutError 时令牌已焚——用户按提示
    「稍后重试」只会拿到「找不到这个令牌」，提示失真、必须重新预览。
    修复后：取走=原子重命名，锁超时把它放回去；重试同一令牌直接成功。
    """
    calls = []

    def flaky(payload, ws):
        calls.append(ws)
        if len(calls) == 1:
            raise TimeoutError("另一处正持锁")
        return {"summary": "ok"}

    monkeypatch.setitem(approval._OPERATIONS, "test.flaky", flaky)
    result = approval.preview(
        "test.flaky", str(workspace), {"a": 1},
        summary="s", diff=["d"], targets=["t"])

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])
    assert ei.value.code == "lock_timeout"

    again = approval.apply(result["token"])      # 同一令牌重试：可用
    assert again["summary"] == "ok"
    assert len(calls) == 2


def test_token_is_bound_to_its_workspace(tokens, workspace, fake_op, tmp_path):
    """令牌是发给"这个工作区"的确认书，不能拿去给别的工作区用。"""
    result = _preview(workspace)
    other = tmp_path / "other-ws"
    other.mkdir()

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"], workspace=str(other))

    assert "绑定" in str(ei.value)
    assert not fake_op


def test_apply_without_workspace_falls_back_to_bound_one(tokens, workspace, fake_op):
    result = _preview(workspace)

    approval.apply(result["token"])

    assert fake_op[0][1] == str(workspace)


def test_tampered_payload_is_rejected(tokens, workspace, fake_op):
    """改过载荷的令牌一律拒绝——指纹就是为这个存的。"""
    result = _preview(workspace)
    path = tokens / (result["token"] + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["fields"]["公司"] = "被篡改的公司"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])

    assert "改动" in str(ei.value)
    assert not fake_op


def test_unknown_token_shapes_are_rejected(tokens, workspace):
    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply("not-a-token")
    assert "格式不对" in str(ei.value)

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply("0" * 32)
    assert "找不到这个令牌" in str(ei.value)


def test_unknown_operation_is_rejected(tokens, workspace):
    result = _preview(workspace, operation="nope.whatever")

    with pytest.raises(approval.ApprovalError) as ei:
        approval.apply(result["token"])

    assert "未知操作" in str(ei.value)
