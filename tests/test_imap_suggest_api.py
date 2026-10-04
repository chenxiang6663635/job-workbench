# -*- coding: utf-8 -*-
"""邮件 → 候选事实的 HTTP 层（批 9）：只读、不落盘、错误码复用。

钉三条（与 IMAP 面的红线同源）：

1. **只读**：调用前后工作区文件字节不变——它只是把「已经拉到手的正文」解释成
   建议，写不写由用户逐条确认后的既有链路决定；
2. **ICS 优先**：同一封邮件带 ICS 时，时间与会议链接以 ICS 为准（source=ics）；
3. **同义不新造 code**：空输入复用 `status.textRequired`（前端语言包已覆盖）；
4. **凭据形态**（issue #203）：Provider 的 key 有「引用 / 明文」两态——保存只写引用、
   读时惰性迁移、引用取不到时 GET 如实自报而 BYOK 调用面 409（见文末那组用例）。
"""

import csv
import io
import json
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from apierror import ApiError  # noqa: E402
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


def test_suggest_facts_accepts_rfc5322_mail_date(tmp_path, client):
    """回归（2026-09-25 真机）：前端传的是 IMAP 的 Date 头**原文**（RFC 5322），
    不是 ISO——只测 ISO 会让链路看着是通的，而基准其实静默退化成今天。"""
    _seed(tmp_path, [ROW])
    facts = _suggest(client, 原文="请在 3 天内完成在线测评",
                     日期="Sun, 20 Sep 2026 09:05:00 +0800").json()["facts"]
    deadline = next(f for f in facts if f["kind"] == "截止")
    assert deadline["value"] == "2026-09-23", "基准应为邮件日期 09-20 + 3 天"


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
    """把 provider 配置成「已就绪」，并拦掉真实出网。

    配置按**明文回退形态**手写（key 直接落在文件里，autouse fixture 已把存储钉成
    plaintext）：本文件其余用例只关心「配置齐了」这件事；引用形态本身由文末
    #203 那组用例专测。
    """
    from routers import imap_facts

    cfg = tmp_path / WS / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "provider.json").write_text(
        json.dumps({"base_url": "https://api.example.com/v1", "api_key": "sk-test"}),
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


# --- Provider 凭据的 at-rest（issue #203 子任务 B）---------------------------------
#
# 存储策略层（`jobws_core.credentials`）自己的行为由 tests/test_credentials.py 钉住；
# 这里钉的是 **Provider 这一侧的接线**：保存只写引用、读时惰性迁移、以及「引用在手却
# 取不到」时各调用面的分工（GET 如实自报，BYOK 调用面 409）。一律注入假 store——
# 绝不碰真机凭据管理器（真机往返只在 tests/test_credentials_windows.py）。

SECRET = "sk-provider-cred-4a7d"
MISSING_REF = "job-workbench/9ca1f0/deleted/provider"


class _FakeStore:
    """假「凭据管理器」：内存字典 + 读写成败可编程。"""

    kind = "credman"

    def __init__(self, stored=None, set_ok=True):
        self.entries = dict(stored or {})   # {ref: secret}；缺某个 ref = 取不到
        self.set_ok = set_ok
        self.set_calls = 0

    def available(self):
        return True

    def get(self, ref):
        return self.entries.get(ref)

    def set(self, ref, secret):
        self.set_calls += 1
        if not self.set_ok:
            return False
        self.entries[ref] = secret
        return True

    def delete(self, ref):
        self.entries.pop(ref, None)
        return True


def _use_store(monkeypatch, store):
    """把 Provider 的存储换成假 store（`select_store` 每次现取，所以打桩即可）。"""
    from jobws_core import credentials

    monkeypatch.setattr(credentials, "select_store", lambda *args, **kwargs: store)
    return store


@pytest.fixture()
def credman(monkeypatch):
    """假 credman 存储；用例可直接读它的 `entries` 断言密文落在哪。"""
    return _use_store(monkeypatch, _FakeStore())


def _provider_file(tmp_path):
    return tmp_path / WS / "config" / "provider.json"


def _write_provider_config(tmp_path, data):
    path = _provider_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _read_provider_file(tmp_path):
    return json.loads(_provider_file(tmp_path).read_text(encoding="utf-8"))


def _save_provider(client, **body):
    payload = {"base_url": "https://api.example.com/v1", "api_key": ""}
    payload.update(body)
    return client.post("/api/provider", params={"ws": WS}, json=payload)


def _get_provider(client):
    return client.get("/api/provider", params={"ws": WS}).json()


def test_provider_save_writes_a_reference_not_the_key(tmp_path, client, credman):
    """(a) 保存后配置文件里只剩引用串，密文在凭据管理器里，响应自报形态 credman。"""
    res = _save_provider(client, api_key=SECRET)

    assert res.status_code == 200, res.text
    assert res.json()["storage"] == "credman"
    assert res.json()["hasKey"] is True
    assert SECRET not in res.text, "响应不得回显完整 key"

    raw = _read_provider_file(tmp_path)
    assert "api_key" not in raw, "引用形态：配置文件里不该再有明文 key"
    assert credman.entries == {raw["api_key_ref"]: SECRET}, "密文得真的存进去"

    got = _get_provider(client)
    assert got["storage"] == "credman" and got["hasKey"] is True
    assert SECRET not in json.dumps(got)


def test_provider_get_migrates_legacy_plaintext(tmp_path, client, credman):
    """(b) 读时惰性迁移：手写明文 config → GET 触发 → 文件改写成引用形态。"""
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key": SECRET})

    body = _get_provider(client)

    assert body["storage"] == "credman" and body["hasKey"] is True
    raw = _read_provider_file(tmp_path)
    assert "api_key" not in raw and raw["api_key_ref"], "迁移必须落盘，否则引用只活在内存"
    assert credman.entries[raw["api_key_ref"]] == SECRET


def test_provider_read_migrates_on_the_consumer_path(tmp_path, client, credman, monkeypatch):
    """(b') 消费面（本文件的 AI 建议）读配置时同样迁移——两处走同一个 read_config。"""
    _seed(tmp_path, [ROW])
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key": SECRET})
    from routers import imap_facts

    monkeypatch.setattr(imap_facts, "_call_model", lambda cfg_, prompt, model: AI_CONTENT)

    res = _suggest_ai(client, 原文="面试改到 2026-09-25 14:00")

    assert res.status_code == 200, res.text
    raw = _read_provider_file(tmp_path)
    assert "api_key" not in raw and raw["api_key_ref"]


def test_provider_save_keeps_plaintext_when_store_write_fails(tmp_path, client, monkeypatch):
    """(c) 写凭据管理器失败 → 明文留在配置文件：一次失败的迁移不能吞掉仅存的凭据。"""
    store = _use_store(monkeypatch, _FakeStore(set_ok=False))

    res = _save_provider(client, api_key=SECRET)

    assert res.json()["storage"] == "plaintext"
    raw = _read_provider_file(tmp_path)
    assert raw["api_key"] == SECRET and "api_key_ref" not in raw
    assert store.set_calls and _get_provider(client)["hasKey"] is True, "明文形态照样能用"


def test_provider_reference_without_the_secret(tmp_path, client, credman):
    """(d) 引用在手但取不到：GET 如实显示「有引用、没 key」，调用面才 409。

    分工是刻意的——GET 要能打开设置页让人重新保存，所以它不能抛；而 `/test` 与
    BYOK 调用面必须报错，否则界面看着正常、调用永远拿不到 key。
    """
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key_ref": MISSING_REF})
    assert credman.entries == {}, "夹具前提：这条引用在存储里取不到"

    body = _get_provider(client)
    assert body["hasKey"] is False and body["api_key"] == ""
    assert body["storage"] == "credman", "形态照报：引用形态不等于明文"

    res = client.post("/api/provider/test", params={"ws": WS})
    assert res.status_code == 409, res.text
    assert res.json()["error_code"] == "provider.credentialUnavailable"
    assert "重新保存" in res.json()["detail"]

    from routers import provider as provider_router

    with pytest.raises(ApiError) as excinfo:
        provider_router.read_config(str(tmp_path / WS))
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "provider.credentialUnavailable"


def test_provider_unavailable_blocks_the_ai_consumer(tmp_path, client, credman):
    """(d') 消费面（简历导入 / AI 建议这类 BYOK 调用）同样 409——绝不静默降级。"""
    _seed(tmp_path, [ROW])
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key_ref": MISSING_REF})

    res = _suggest_ai(client, 原文="面试改到 2026-09-25 14:00")

    assert res.status_code == 409, res.text
    assert res.json()["error_code"] == "provider.credentialUnavailable"
    assert "重新保存" in res.json()["detail"]


def test_provider_rotation_reuses_the_same_reference(tmp_path, client, credman):
    """(e) 换 key 复用同一引用：凭据管理器里不留指向旧密文的孤儿条目。"""
    _save_provider(client, api_key="sk-first-1111")
    ref = _read_provider_file(tmp_path)["api_key_ref"]

    res = _save_provider(client, api_key="sk-second-2222")

    assert res.json()["storage"] == "credman"
    assert res.json()["api_key"].endswith("2222"), "脱敏保留末 4 位，用于确认换的是哪把"
    assert _read_provider_file(tmp_path)["api_key_ref"] == ref
    assert credman.entries == {ref: "sk-second-2222"}


def test_provider_blank_key_resave_never_writes_the_secret_back(tmp_path, client, credman):
    """(f) 空 key = 保留凭据：**绝不能**把解析出的密文回写进配置文件。

    回归网（2026-10-04 人工复核发现）：Provider 的 `_resolve` 会把解析出的 key 注入
    `cfg["api_key"]`（`read_config` 的既有形状——resume / imap_facts 按它取 key），
    而 POST 紧接着把 cfg 落盘；注入没关的话，第二次保存（只改 base_url、key 留空）
    就把明文 key 写了回去，把 #203 的成果整个抵消。
    """
    _save_provider(client, api_key=SECRET)
    ref = _read_provider_file(tmp_path)["api_key_ref"]

    res = _save_provider(client, api_key="", base_url="https://api.changed.com/v1")

    assert res.status_code == 200, res.text
    assert res.json()["storage"] == "credman"
    raw = _read_provider_file(tmp_path)
    # 不变量是「密文不在文件里」，不是「api_key 键不存在」：_empty_config 会带一个
    # 空串占位（引用形态下它是无害的遗留字段，读侧按"没有"处理）。
    assert raw.get("api_key", "") == "", "空 key 保存不得把密文写回配置文件"
    assert SECRET not in json.dumps(raw), "密文不得出现在配置文件的任何字段里"
    assert raw["api_key_ref"] == ref, "重存复用同一引用（不留孤儿）"
    assert raw["base_url"] == "https://api.changed.com/v1"
    assert credman.entries[ref] == SECRET, "保留语义没变：原 key 还在凭据管理器里"


def test_provider_migration_keeps_a_concurrent_save(tmp_path, client, credman, monkeypatch):
    """(g) 迁移落盘走「锁内重读合并」：并发写入的字段不会被手里的旧 cfg 覆盖。

    构造并发窗口：GET 读入旧 cfg（明文形态）之后、迁移落盘之前，模拟另一端把
    base_url 改成新值（包一层 `credentials.resolve_secret`，在它返回后改文件）。
    没有合并的话，迁移会把手里的旧 base_url 写回去——用户刚在设置页保存的地址
    就这么没了（provider 老实现专门防过这一手，抽公共件时不能丢）。
    """
    from jobws_core import credentials

    only_once = {"done": False}
    real = credentials.resolve_secret

    def resolve_then_concurrent_write(*args, **kwargs):
        outcome = real(*args, **kwargs)
        if not only_once["done"]:
            only_once["done"] = True
            path = _provider_file(tmp_path)
            current = json.loads(path.read_text(encoding="utf-8"))
            current["base_url"] = "https://concurrent.example/v1"
            path.write_text(json.dumps(current), encoding="utf-8")
        return outcome

    monkeypatch.setattr(credentials, "resolve_secret", resolve_then_concurrent_write)
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key": SECRET})

    body = _get_provider(client)

    assert body["base_url"] == "https://concurrent.example/v1", "读到的应是合并后的新值"
    raw = _read_provider_file(tmp_path)
    assert raw["base_url"] == "https://concurrent.example/v1", "迁移写回不得覆盖并发保存"
    assert raw["api_key_ref"] and "api_key" not in raw
    assert credman.entries[raw["api_key_ref"]] == SECRET


def test_provider_concurrent_migration_leaves_no_orphan(tmp_path, client, credman, monkeypatch):
    """并发迁移去重：另一端先落盘了引用 → 采用先到者，并删掉自己刚写的那条。

    两个读请求同时撞上同一条旧明文时，各自都会往凭据管理器写一份；没有去重的话，
    每并发一次就多一条永久失联的条目（四端复核 m-1①）。
    """
    from jobws_core import credentials

    theirs_ref = "job-workbench/aaaa1111bbbb2222/provider"
    real = credentials.resolve_secret
    only_once = {"done": False}

    def wrap(*args, **kwargs):
        outcome = real(*args, **kwargs)
        if not only_once["done"]:
            only_once["done"] = True
            store = kwargs["store"]
            path = _provider_file(tmp_path)
            path.write_text(json.dumps({"base_url": "https://api.example.com/v1",
                                        "api_key_ref": theirs_ref}), encoding="utf-8")
            store.entries[theirs_ref] = SECRET
        return outcome

    monkeypatch.setattr(credentials, "resolve_secret", wrap)
    _write_provider_config(tmp_path, {"base_url": "https://api.example.com/v1",
                                      "api_key": SECRET})

    body = _get_provider(client)

    raw = _read_provider_file(tmp_path)
    assert raw["api_key_ref"] == theirs_ref, "采用先到者的引用"
    assert body["hasKey"] is True and body["storage"] == "credman"
    assert [r for r in credman.entries if r != theirs_ref] == [], \
        "自己刚写的那条要被删掉（不留孤儿）"
