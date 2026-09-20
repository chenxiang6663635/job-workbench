# -*- coding: utf-8 -*-
"""网页端导入的两段式（与 CLI / MCP 共用同一套令牌协议，批 3c）。

网页端 CSV 导入此前是「进程内 preview → 用户确认后重新上传 commit」，现在改为
「preview 登记令牌 → `/api/approvals/apply` 凭令牌落盘」。本文件钉住：

1. 预览不落盘（tracker.csv 连文件都不该出现）且**只在可提交时**给出令牌；
2. apply 才写入，时间线可溯源（口径复用 tracker.commit_import / append_history）；
3. 令牌一次性：重放被拒（422，approval.tokenInvalid）；
4. 预览之后数据变了：整批拒绝（409，approval.conflict），一个字节都不写；
5. 旧 `mode=commit` 直写路径保持可用（网页端已切走，兼容面不破坏）。

令牌目录挪进 tmp_path（与 tests/test_approval.py 同款做法）：不在真实系统临时
目录里留令牌文件。
"""

import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import approval  # noqa: E402
import deps  # noqa: E402
import tracker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
TRACKING = "05_投递追踪"
CSV_ONE = (
    "公司,岗位,方向,批次,当前阶段\n"
    "公司A,岗位甲,hvac,正式批,已投\n"
)


@pytest.fixture()
def tokens(tmp_path, monkeypatch):
    store = tmp_path / "tokens"
    store.mkdir()
    monkeypatch.setattr(approval._shell, "_store_dir", lambda: str(store))
    return store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入，避免读到真实仓库根）
    return TestClient(main.app)


def _ws(tmp_path):
    return str(tmp_path / WS)


def _tracker_bytes(tmp_path):
    path = tmp_path / WS / TRACKING / "tracker.csv"
    return path.read_bytes() if path.exists() else b""


def _preview(client, csv_text=CSV_ONE):
    res = client.post("/api/applications/import", params={"ws": WS},
                      json={"csv": csv_text, "mode": "preview"})
    assert res.status_code == 200, res.text
    return res.json()


def _apply(client, token):
    return client.post("/api/approvals/apply", json={"token": token})


def test_preview_gives_token_without_writing(tmp_path, client, tokens):
    before = _tracker_bytes(tmp_path)
    body = _preview(client)
    assert body["counts"]["ok"] == 1
    assert body["token"], "无错误行且有可新增行时必须给出令牌"
    assert _tracker_bytes(tmp_path) == before, "预览不落盘：tracker.csv 不该被创建/改动"


def test_apply_writes_and_is_traceable(tmp_path, client, tokens):
    token = _preview(client)["token"]
    res = _apply(client, token)
    assert res.status_code == 200, res.text
    assert res.json()["written"] == 1

    rows = tracker.read_rows(_ws(tmp_path))
    assert [r["公司"] for r in rows] == ["公司A"]
    history = tracker.read_history(_ws(tmp_path))
    assert [h["字段"] for h in history] == ["创建"], "导入必须逐条入账时间线"


def test_token_is_single_use(tmp_path, client, tokens):
    token = _preview(client)["token"]
    assert _apply(client, token).status_code == 200

    again = _apply(client, token)
    assert again.status_code == 422
    assert again.json()["error_code"] == "approval.tokenInvalid"
    assert len(tracker.read_rows(_ws(tmp_path))) == 1, "重放不得产生第二条写入"


def test_conflict_after_preview_rejects_whole_batch(tmp_path, client, tokens):
    token = _preview(client)["token"]

    # 预览之后主表出现同键记录（用户在另一处加过）——apply 必须整批拒绝
    rows = [{field: "" for field in tracker.FIELDS}]
    rows[0].update({"id": "A001", "公司": "公司A", "岗位": "岗位甲",
                    "当前阶段": "已投"})
    tracker.write_rows(rows, _ws(tmp_path))

    res = _apply(client, token)
    assert res.status_code == 409
    assert res.json()["error_code"] == "approval.conflict"
    assert len(tracker.read_rows(_ws(tmp_path))) == 1, "冲突时一个字节都不该写"


def test_preview_with_error_rows_gives_no_token(client, tokens):
    body = _preview(client, "公司,岗位\n,只有岗位\n")
    assert body["counts"]["error"] >= 1
    assert body["token"] is None, "有错误行时不给令牌（前端按钮同样保持禁用）"


def test_preview_without_new_rows_gives_no_token(tmp_path, client, tokens):
    token = _preview(client)["token"]
    assert _apply(client, token).status_code == 200

    body = _preview(client)
    assert body["counts"]["ok"] == 0
    assert body["counts"]["duplicate"] == 1
    assert body["token"] is None, "没有可新增行时不给令牌"


def test_unknown_token_is_rejected(client, tokens):
    res = _apply(client, "0" * 32)
    assert res.status_code == 422
    assert res.json()["error_code"] == "approval.tokenInvalid"


def test_legacy_commit_mode_still_writes(tmp_path, client, tokens):
    """旧路径（网页端已不调用）保持可用——兼容面不破坏。"""
    res = client.post("/api/applications/import", params={"ws": WS},
                      json={"csv": CSV_ONE, "mode": "commit"})
    assert res.status_code == 200, res.text
    assert res.json()["written"] == 1
    assert len(tracker.read_rows(_ws(tmp_path))) == 1
