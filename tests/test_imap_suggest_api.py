# -*- coding: utf-8 -*-
"""邮件 → 候选事实的 HTTP 层（批 9）：只读、不落盘、错误码复用。

钉三条（与 IMAP 面的红线同源）：

1. **只读**：调用前后工作区文件字节不变——它只是把「已经拉到手的正文」解释成
   建议，写不写由用户逐条确认后的既有链路决定；
2. **ICS 优先**：同一封邮件带 ICS 时，时间与会议链接以 ICS 为准（source=ics）；
3. **同义不新造 code**：空输入复用 `status.textRequired`（前端语言包已覆盖）。
"""

import csv
import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
TRACKING_DIR = "05_投递追踪"

ICS = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "METHOD:REQUEST",
    "BEGIN:VEVENT",
    "UID:abc-123@example.com",
    "DTSTART;TZID=Asia/Shanghai:20260925T140000",
    "SUMMARY:面试邀请（技术面）",
    "URL:https://meeting.tencent.com/dm/abc123",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
])

ROW = {"id": "A001", "公司": "云帆智算", "岗位": "后端工程师", "当前阶段": "已投"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402

    return TestClient(main.app)


def _seed(tmp_path, rows):
    from jobws_core import tracker

    path = tmp_path / WS / TRACKING_DIR
    path.mkdir(parents=True, exist_ok=True)
    with io.open(str(path / "tracker.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.FIELDS)
        writer.writeheader()
        for row in rows:
            full = {field: "" for field in tracker.FIELDS}
            full.update(row)
            writer.writerow(full)
    # mails.csv 也建一份：只读断言要有字节可比
    with io.open(str(path / "mails.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tracker.MAIL_FIELDS)
        writer.writeheader()
        writer.writerow({field: "" for field in tracker.MAIL_FIELDS})


def _snapshot(tmp_path):
    out = {}
    for base, _dirs, files in os.walk(str(tmp_path / WS)):
        for name in files:
            path = os.path.join(base, name)
            with io.open(path, "rb") as f:
                out[path] = f.read()
    return out


def _suggest(client, **body):
    payload = {"原文": "", "ics": "", "id": ""}
    payload.update(body)
    return client.post("/api/imap/suggest-facts", params={"ws": WS}, json=payload)


def test_suggest_facts_prefers_ics(tmp_path, client):
    _seed(tmp_path, [ROW])
    res = _suggest(client, 原文="（正文略）", ics=ICS)
    assert res.status_code == 200, res.text

    facts = res.json()["facts"]
    time_fact = next(f for f in facts if f["kind"] == "时间")
    assert time_fact["value"] == "2026-09-25 14:00"
    assert time_fact["source"] == "ics"
    assert any(f["kind"] == "会议链接" and f["source"] == "ics" for f in facts)


def test_suggest_facts_is_read_only(tmp_path, client):
    _seed(tmp_path, [ROW])
    before = _snapshot(tmp_path)

    res = _suggest(client, 原文="云帆智算：面试改到 2026-09-25 14:00，"
                                 "见 https://meeting.tencent.com/dm/new001")

    assert res.status_code == 200, res.text
    assert _snapshot(tmp_path) == before, "只读端点不得改动工作区任何文件"


def test_suggest_facts_matches_records_and_stage(tmp_path, client):
    _seed(tmp_path, [ROW])
    facts = _suggest(client, 原文="云帆智算 后端工程师：很遗憾，本次不再推进。").json()["facts"]

    record = next(f for f in facts if f["kind"] == "公司岗位")
    assert record["value"] == "A001"
    stage = next(f for f in facts if f["kind"] == "阶段")
    assert stage["value"] == "已挂"
    assert stage["targetId"] == "A001"


def test_suggest_facts_focus_id_beats_matching(tmp_path, client):
    _seed(tmp_path, [ROW, {"id": "A007", "公司": "星河数据", "岗位": "热管理",
                           "当前阶段": "测评"}])
    facts = _suggest(client, 原文="您的简历已进入笔试环节", id="A007").json()["facts"]

    record = next(f for f in facts if f["kind"] == "公司岗位")
    assert record["value"] == "A007"
    assert record["note"] == "手动指定"


def test_suggest_facts_requires_text(client):
    res = _suggest(client)
    assert res.status_code == 422
    assert res.json()["error_code"] == "status.textRequired"


def test_suggest_facts_uses_mail_date_for_durations(tmp_path, client):
    """「3 天内」以**邮件日期**为基准（不是今天）。

    这是链路验证：前端把邮件的 `date` 传成 `日期`，后端必须真的用它——
    漏传 / 后端忽略都会让结论变成"还有 3 天"而不是正确的落点。
    """
    _seed(tmp_path, [ROW])
    facts = _suggest(client, 原文="请在 3 天内完成在线测评",
                     日期="2026-09-20").json()["facts"]
    deadline = next(f for f in facts if f["kind"] == "截止")
    assert deadline["value"] == "2026-09-23"


def test_suggest_facts_duration_without_mail_date_notes_the_basis(tmp_path, client):
    """不带 `日期` 时退回今天，但 note 必须写明基准（否则用户不知道按哪天算的）。"""
    _seed(tmp_path, [ROW])
    facts = _suggest(client, 原文="48 小时内完成笔试").json()["facts"]
    deadline = next(f for f in facts if f["kind"] == "截止")
    assert "未取到邮件日期" in deadline["note"]


# --- 可选 AI 增强（BYOK）：只产建议、绝不写入 ------------------------------------

AI_CONTENT = (
    "```json\n"
    '{"facts": ['
    '{"kind": "时间", "value": "2026-09-25 14:00", "evidence": "9月25日下午2点"},'
    '{"kind": "会议链接", "value": "https://meeting.tencent.com/dm/ai001", "evidence": "腾讯会议"},'
    '{"kind": "公司岗位", "value": "A001", "evidence": "编造的"},'
    '{"kind": "时间", "value": "", "evidence": "空的"}'
    "]}"
    "\n```"
)


@pytest.fixture()
def provider_ready(tmp_path, monkeypatch):
    """把 provider 配置成「已就绪」，并拦掉真实出网。"""
    import json as _json

    from routers import imap_facts

    cfg = tmp_path / WS / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "provider.json").write_text(
        _json.dumps({"base_url": "https://api.example.com/v1", "api_key": "sk-test"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(imap_facts, "_call_model", lambda cfg_, prompt, model: AI_CONTENT)
    return imap_facts


def _suggest_ai(client, **body):
    payload = {"原文": "", "ics": "", "model": "deepseek-chat"}
    payload.update(body)
    return client.post("/api/imap/suggest-facts-ai", params={"ws": WS}, json=payload)


def test_ai_suggest_requires_provider(client):
    res = _suggest_ai(client, 原文="面试改到 2026-09-25 14:00")
    assert res.status_code == 400
    assert res.json()["error_code"] == "resume.providerMissing"


def test_ai_suggest_requires_model(tmp_path, client, provider_ready):
    res = _suggest_ai(client, 原文="面试改到 2026-09-25 14:00", model="")
    assert res.status_code == 422
    assert res.json()["error_code"] == "resume.modelRequired"


def test_ai_suggest_returns_low_confidence_ai_facts_only(tmp_path, client, provider_ready):
    _seed(tmp_path, [ROW])
    before = _snapshot(tmp_path)

    res = _suggest_ai(client, 原文="面试改到 9月25日下午2点，腾讯会议见")

    assert res.status_code == 200, res.text
    body = res.json()
    # 只保留白名单内的三类，且空值与「公司岗位」被丢弃（AI 不碰记录匹配）
    assert [f["kind"] for f in body["facts"]] == ["时间", "会议链接"]
    assert all(f["source"] == "ai" for f in body["facts"])
    assert all(f["confidence"] == "low" for f in body["facts"]), "AI 建议必须经用户核对"
    assert body["model"] == "deepseek-chat"
    assert _snapshot(tmp_path) == before, "AI 增强同样只读：不得改动工作区"


def test_ai_suggest_matches_after_stripping_quotes(tmp_path, client, provider_ready):
    """记录匹配用剥离引用后的正文：被引用的**另一家公司**不该把建议指过去。"""
    _seed(tmp_path, [ROW, {"id": "A007", "公司": "星河数据", "岗位": "热管理",
                           "当前阶段": "测评"}])
    res = _suggest_ai(client, 原文="面试改到 2026-09-25 14:00\n"
                                   "在 2026-09-20 写道：\n> 星河数据 对接")

    assert res.status_code == 200, res.text
    assert all(f["targetId"] == "" for f in res.json()["facts"]), "引用块里的公司不该被匹配"


def test_ai_suggest_drops_non_whitelisted_meeting_link(tmp_path, client, provider_ready,
                                                      monkeypatch):
    content = ('{"facts": [{"kind": "会议链接", "value": "javascript:alert(1)",'
               ' "evidence": "x"}]}')
    monkeypatch.setattr(provider_ready, "_call_model", lambda *a: content)

    res = _suggest_ai(client, 原文="随便一段")

    assert res.status_code == 200
    assert res.json()["facts"] == [], "非白名单链接（含危险 scheme）一律丢弃"


def test_ai_suggest_caps_input_length(tmp_path, client, provider_ready, monkeypatch):
    seen = {}

    def _capture(cfg_, prompt, model):
        seen["prompt"] = prompt
        return '{"facts": []}'

    monkeypatch.setattr(provider_ready, "_call_model", _capture)

    res = _suggest_ai(client, 原文="A" * 4500 + "TAIL_MARK")

    assert res.status_code == 200
    assert "TAIL_MARK" not in seen["prompt"], "超长正文必须先截断再进 prompt"


def test_ai_suggest_wraps_model_failure(tmp_path, client, provider_ready, monkeypatch):
    def _boom(cfg_, prompt, model):
        raise ValueError("bad json")

    monkeypatch.setattr(provider_ready, "_call_model", _boom)
    res = _suggest_ai(client, 原文="随便一段")
    assert res.status_code == 502
    assert res.json()["error_code"] == "resume.modelCallFailed"
