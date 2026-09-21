# -*- coding: utf-8 -*-
"""题库的 HTTP 端点：列表（后端过滤）、新增 / 导入 / 更新 / 删除预览（都不落盘）。

钉住两件容易悄悄坏掉的事：
1. **筛选在后端**：`?domain=` / `?status=` / `?q=` 必须真的少返回，而不是前端
   拉全量再过滤（那样接口看着一样，数据却每次都传整张表）；
2. **预览不落盘**：四个预览端点都只给令牌，`questions.csv` **不该**在这时被改——
   写通道只有 `/api/approvals/apply` 一条。
"""

import datetime
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


def _read_questions(tmp_path):
    """按字节读回：断言"只读端点一个字节都没写"要用它。"""
    path = os.path.join(str(tmp_path), WS, "05_投递追踪", "questions.csv")
    with io.open(path, "rb") as handle:
        return handle.read()


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


def test_drill_is_readonly_and_shares_the_cli_rule(client, tmp_path):
    """抽题端点：队列 = 错题 ∪ due（与 CLI 同一口径），且一个字节都不写。"""
    # 会了 = 14 天后到期：日期**相对今天**构造——写死的日期会让这条用例在某个
    # 日子起必然变红（不改一行产品代码，CI 却红了，最难查的那种）
    recent = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点,标签,最近复习\n"
                     "Q001,TCP,技术面,网络,未看,导入,要点,,\n"                 # due（未看恒在）
                     f"Q002,UDP,技术面,网络,会了,导入,要点,,{recent}\n"        # 不到期
                     "Q003,HTTP,技术面,网络,会了,导入,要点,错题,2026-01-01\n")   # 错题且到期
    before = _read_questions(tmp_path)
    res = client.get("/api/progress/questions/drill",
                     params={"ws": WS, "mode": "due", "n": "5"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert {row["题目"] for row in data["items"]} == {"TCP", "HTTP"}
    assert _read_questions(tmp_path) == before


def test_drill_rejects_unknown_mode_with_a_stable_code(client, tmp_path):
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,导入,要点\n")
    res = client.get("/api/progress/questions/drill",
                     params={"ws": WS, "mode": "smart"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "question.drillFailed"
def test_preview_delete_gives_token_and_writes_nothing(client, tmp_path):
    """删题也是两段式：端点只给令牌与"将删哪一行"，CSV 一个字节都不动。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,导入,要点\n")
    before = _read_questions(tmp_path)
    res = client.get("/api/progress/questions/preview-delete",
                     params={"ws": WS, "id": "Q001"})
    assert res.status_code == 200
    data = res.json()
    assert data["token"]
    assert data["summary"] == "删除 1 道题"
    assert any("Q001" in line for line in data["diff"])
    assert _read_questions(tmp_path) == before


def test_preview_delete_rejects_unknown_id_with_a_stable_code(client, tmp_path):
    """找不到就报错（不是"删除 0 道题"的空转），且错误码稳定——前端靠它出文案。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,导入,要点\n")
    res = client.get("/api/progress/questions/preview-delete",
                     params={"ws": WS, "id": "Q999"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "question.deleteFailed"


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


def test_list_marks_due_questions_with_reason(client, tmp_path):
    """B-3：列表行带 due 标记与原因（复用 due_from_rows，与 CLI `bank due` 同口径）。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点,最近复习\n"
                     "Q001,未看的题,技术面,网络,未看,自拟,要点,\n"
                     "Q002,刚复习的题,技术面,网络,会了,自拟,要点,2099-01-01\n")
    res = client.get("/api/progress/questions", params={"ws": WS})
    assert res.status_code == 200
    items = dict((row["题目id"], row) for row in res.json()["items"])
    assert items["Q001"]["due"] is True
    assert "未看" in items["Q001"]["reason"]
    assert "due" not in items["Q002"]


def test_drill_returns_reasons_and_counts(client, tmp_path):
    """B-3/B-4：抽题结果带每行的原因与三态计数（结束卡消费 counts 看"练到哪了"）。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点,最近复习\n"
                     "Q001,未看的题,技术面,网络,未看,自拟,要点,\n"
                     "Q002,会的题,技术面,网络,会了,自拟,要点,2099-01-01\n")
    res = client.get("/api/progress/questions/drill",
                     params={"ws": WS, "mode": "due", "n": 5})
    assert res.status_code == 200
    data = res.json()
    assert data["counts"] == {"未看": 1, "会了": 1}
    assert [row["题目id"] for row in data["items"]] == ["Q001"]
    assert "未看" in data["items"][0]["reason"]


def test_preview_add_returns_token_without_writing(client, tmp_path):
    """1c 自拟新增预览：只给令牌，questions.csv 一个字节都不写。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,自拟,要点\n")
    before = _read_questions(tmp_path)
    res = client.get("/api/progress/questions/preview-add",
                     params={"ws": WS, "title": "DNS 解析过程", "domain": "技术面",
                             "subject": "网络", "answer": "递归 + 迭代",
                             "difficulty": "中"})
    assert res.status_code == 200
    data = res.json()
    assert data["token"]
    assert "新增题目：DNS 解析过程" in data["summary"]
    # 差异表列的是"将写入的字段"——题目那行必须在
    assert any("DNS 解析过程" in line for line in data["diff"])
    assert _read_questions(tmp_path) == before


def test_preview_add_defaults_source_and_status(client, tmp_path):
    """不给来源/状态时由领域层补「自拟」「未看」——GUI 表单不给这两项选择，
    默认值必须在预览段就体现（预览是"将要落什么"的承诺）。"""
    res = client.get("/api/progress/questions/preview-add",
                     params={"ws": WS, "title": "冒泡排序的复杂度"})
    assert res.status_code == 200
    diff = "\n".join(res.json()["diff"])
    assert "| 来源 | 自拟 |" in diff
    assert "| 状态 | 未看 |" in diff


def test_preview_add_rejects_missing_title(client, tmp_path):
    """题目为空 → 400 + 明确原因，而不是签出一张空题目的令牌。"""
    res = client.get("/api/progress/questions/preview-add", params={"ws": WS})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "question.addFailed"
    assert "题目不能为空" in body["error_params"]["reason"]


def test_preview_add_rejects_duplicate(client, tmp_path):
    """已存在同名同领域的题 → 预览段就拒绝（判重键 = 题目+领域+科目，与导入同口径）。"""
    _write_questions(client, tmp_path,
                     "题目id,题目,领域,科目,状态,来源,答案要点\n"
                     "Q001,TCP,技术面,网络,未看,自拟,要点\n")
    res = client.get("/api/progress/questions/preview-add",
                     params={"ws": WS, "title": "TCP", "domain": "技术面",
                             "subject": "网络"})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "question.addFailed"
    assert "已存在" in body["error_params"]["reason"]
