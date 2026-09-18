# -*- coding: utf-8 -*-
"""题库的三个 HTTP 端点：列表（后端过滤）、1a 导入预览、1b 更新预览（都不落盘）。

钉住两件容易悄悄坏掉的事：
1. **筛选在后端**：`?domain=` / `?status=` / `?q=` 必须真的少返回，而不是前端
   拉全量再过滤（那样接口看着一样，数据却每次都传整张表）；
2. **预览不落盘**：两个预览端点都只给令牌，`questions.csv` **不该**在这时被改——
   写通道只有 `/api/approvals/apply` 一条。
"""

import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

from fastapi.testclient import TestClient  # noqa: E402

import deps  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()
    (tmp_path / WS / "05_投递追踪").mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _write_questions(client, tmp_path, rows_text):
    path = os.path.join(str(tmp_path), WS, "05_投递追踪", "questions.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(rows_text)


def test_list_returns_empty_when_no_bank(client):
    res = client.get("/api/progress/questions", params={"ws": WS})
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0, "counts": {},
                          "filters": {"domain": "", "subject": "", "status": "",
                                      "keyword": ""}}


def test_filters_are_applied_server_side(client, tmp_path):
    header = ("题目id,题目,领域,科目,状态,来源,答案要点\n"
              "Q001,TCP,技术面,网络,未看,自拟,要点\n"
              "Q002,UDP,技术面,网络,会了,自拟,要点\n"
              "Q003,讲个冲突,行为面,,看过,自拟,要点\n")
    _write_questions(client, tmp_path, header)
    res = client.get("/api/progress/questions",
                     params={"ws": WS, "domain": "技术面"})
    data = res.json()
    assert data["total"] == 2
    assert {row["题目"] for row in data["items"]} == {"TCP", "UDP"}
    assert data["counts"] == {"未看": 1, "会了": 1}

    res = client.get("/api/progress/questions", params={"ws": WS, "status": "会了"})
    assert res.json()["total"] == 1
    res = client.get("/api/progress/questions", params={"ws": WS, "q": "冲突"})
    assert res.json()["total"] == 1


def test_preview_import_does_not_write(client, tmp_path):
    """预览只给令牌：questions.csv 在这时**不能**存在（写通道只有 apply 一条）。"""
    module = os.path.join(str(tmp_path), WS, "03_面试准备", "技术面")
    os.makedirs(module, exist_ok=True)
    with io.open(os.path.join(module, "tcp.md"), "w", encoding="utf-8") as handle:
        handle.write("# 讲讲 TCP 三次握手\n\n要点。\n")

    res = client.get("/api/progress/questions/preview-import", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["token"]
    assert "导入 1 道题" in data["summary"]
    assert not os.path.exists(os.path.join(str(tmp_path), WS, "05_投递追踪",
                                           "questions.csv"))


def test_preview_import_rejects_module_without_questions(client):
    """只有模板 / 空目录 → 400 + 明确错误码，而不是返回一个空令牌。"""
    res = client.get("/api/progress/questions/preview-import", params={"ws": WS})
    assert res.status_code == 400
    assert res.json()["error_code"] == "question.importFailed"


def test_preview_update_returns_token_without_writing(client, tmp_path):
    """1b 预览只给令牌：这次预览不改 questions.csv（写通道只有 apply 一条）。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,自拟,老要点\n")
    res = client.get("/api/progress/questions/preview-update",
                     params={"ws": WS, "id": "Q001", "answer": "新要点", "status": "会了"})
    assert res.status_code == 200
    data = res.json()
    assert data["token"]
    assert "修改题目 Q001" in data["summary"]
    assert any("答案要点" in line for line in data["diff"])
    # 「最近复习」由落盘段自动写入、不在 changes 里——差异表必须显式列出
    assert any("最近复习" in line for line in data["diff"])
    # 预览不落盘：文件里还是旧值
    path = os.path.join(str(tmp_path), WS, "05_投递追踪", "questions.csv")
    with io.open(path, encoding="utf-8-sig") as handle:
        assert "老要点" in handle.read()


def test_preview_update_rejects_unknown_id(client, tmp_path):
    """找不到题目 → 400 + 明确错误码与原因，而不是一张空的差异表。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,自拟,要点\n")
    res = client.get("/api/progress/questions/preview-update",
                     params={"ws": WS, "id": "Q999", "status": "看过"})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "question.updateFailed"
    assert "找不到" in body["error_params"]["reason"]


def test_preview_update_rejects_no_change(client, tmp_path):
    """没有实际变化时不签发令牌——不制造无意义的确认往返。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,看过,自拟,要点\n")
    res = client.get("/api/progress/questions/preview-update",
                     params={"ws": WS, "id": "Q001", "status": "看过"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "question.updateFailed"
