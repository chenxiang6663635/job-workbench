# -*- coding: utf-8 -*-
"""Provider 端点的 HTTP 层测试（全部离线：出网被 mock）。

这个文件此前**整块缺失**——provider 是 BYOK 的调用入口（简历导入与 AI 改写都经它），
却只有「TLS 上下文接线」「脱敏」「不进导出包」三处旁证。本批补齐五组：

1. **`model` 落盘**：设置页选定后三处使用点共用；旧配置缺这一项要能读（零迁移），
   且**空串表示清空**（与 api_key「空则保留」不同——那是凭证，这是选项）；
2. **`/models` 结构化**：`ok / status / modelCount / models / truncated / hint`，
   列表有上限（OpenRouter 那种几千个模型不能整包塞给界面）；
3. **base_url 提示是非阻断的**：只提示**确证过**的两种写法（通义填了原生地址、
   把 `/chat/completions` 当 base_url 填）；
4. **凭证纪律**：响应脱敏、空 key 保留原值、错误消息给人话；
5. 配置读写并发口径由 `locked` 与原子写保证（既有实现，这里做回归）。
"""

import io
import json
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


@pytest.fixture()
def provider_module():
    import routers.provider as provider  # noqa: E402

    return provider


def _config_path(tmp_path):
    return tmp_path / WS / "config" / "provider.json"


def _save(client, **body):
    payload = {"base_url": "https://api.example.com/v1", "api_key": "sk-test-1234"}
    payload.update(body)
    return client.post("/api/provider", params={"ws": WS}, json=payload)


def _read_raw(tmp_path):
    with io.open(str(_config_path(tmp_path)), "r", encoding="utf-8") as handle:
        return json.load(handle)


class FakeResponse:
    """假出网响应：只带 /models 需要的 status 与 read()。"""

    def __init__(self, payload, status=200):
        self.status = status
        self._payload = payload

    def read(self, size=-1):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _mock_models(monkeypatch, provider_module, payload):
    monkeypatch.setattr(provider_module.tls_http, "open_url",
                        lambda req, timeout=None, purpose=None: FakeResponse(payload))
    monkeypatch.setattr(provider_module, "read_response", lambda resp: payload)


def _models_payload(count):
    return json.dumps(
        {"data": [{"id": "model-%d" % index} for index in range(count)]}
    ).encode("utf-8")


# --- 1. 配置读写与脱敏 ---------------------------------------------------------

def test_get_returns_empty_defaults(client):
    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body == {
        "base_url": "", "api_key": "", "hasKey": False,
        "model": "", "baseUrlHint": None,
    }


def test_get_masks_the_key(client):
    _save(client, api_key="sk-secret-9876")
    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body["hasKey"] is True
    assert "sk-secret-9876" not in json.dumps(body)
    assert body["api_key"]


# --- 2. model 落盘（本批新增）--------------------------------------------------

def test_save_persists_model(client, tmp_path):
    res = _save(client, model="deepseek-chat")
    assert res.status_code == 200, res.text
    assert res.json()["model"] == "deepseek-chat"
    assert _read_raw(tmp_path)["model"] == "deepseek-chat"
    assert client.get("/api/provider", params={"ws": WS}).json()["model"] == "deepseek-chat"


def test_empty_model_clears_it(client, tmp_path):
    """model 与 api_key 的语义**不同**：空串是「清空默认模型」，不是「保留原值」。

    api_key 空着表示"没改凭证"；model 空着是用户想把默认模型取消掉。
    """
    _save(client, model="deepseek-chat")
    res = _save(client, model="")
    assert res.json()["model"] == ""
    assert _read_raw(tmp_path)["model"] == ""


def test_empty_key_still_keeps_the_previous_one(client, tmp_path):
    _save(client, api_key="sk-keep-me")
    _save(client, api_key="", model="deepseek-chat")
    assert _read_raw(tmp_path)["api_key"] == "sk-keep-me"


def test_legacy_config_without_model_is_readable(client, tmp_path):
    """零迁移：旧 provider.json 没有 model 字段时按空串处理，不报错、不丢 key。"""
    path = _config_path(tmp_path)
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with io.open(str(path), "w", encoding="utf-8") as handle:
        json.dump({"base_url": "https://api.example.com/v1", "api_key": "sk-old"},
                  handle, ensure_ascii=False)

    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body["model"] == ""
    assert body["hasKey"] is True
    assert body["base_url"] == "https://api.example.com/v1"


def test_broken_config_is_treated_as_unconfigured(client, tmp_path):
    path = _config_path(tmp_path)
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with io.open(str(path), "w", encoding="utf-8") as handle:
        handle.write("{ not json")

    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body["base_url"] == ""
    assert body["hasKey"] is False


def test_base_url_still_requires_a_scheme(client):
    res = _save(client, base_url="api.example.com/v1")
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "provider.baseUrlInvalid"


# --- 3. base_url 提示（非阻断）-------------------------------------------------

def test_hint_for_dashscope_native_path(client):
    """通义千问必须用兼容模式地址——填原生 dashscope 地址会一直连不上。"""
    _save(client, base_url="https://dashscope.aliyuncs.com/api/v1")
    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body["baseUrlHint"] == "provider.hintDashscope"


def test_no_hint_for_dashscope_compatible_path(client):
    _save(client, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert client.get("/api/provider", params={"ws": WS}).json()["baseUrlHint"] is None


def test_hint_when_a_full_endpoint_is_pasted_as_base_url(client):
    _save(client, base_url="https://api.example.com/v1/chat/completions")
    body = client.get("/api/provider", params={"ws": WS}).json()
    assert body["baseUrlHint"] == "provider.hintEndpointNotBase"


def test_ordinary_base_url_gets_no_hint(client):
    """宁缺勿误报：只提示确证过的两种写法，普通地址保持安静。"""
    _save(client, base_url="https://api.deepseek.com/v1")
    assert client.get("/api/provider", params={"ws": WS}).json()["baseUrlHint"] is None


# --- 4. /test 的结构化结果 -----------------------------------------------------

def test_test_requires_base_url_and_key(client):
    res = client.post("/api/provider/test", params={"ws": WS})
    assert res.status_code == 400
    assert res.json()["error_code"] == "provider.needBaseUrl"

    _save(client, base_url="https://api.example.com/v1", api_key="")
    res = client.post("/api/provider/test", params={"ws": WS})
    assert res.status_code == 400
    assert res.json()["error_code"] == "provider.needApiKey"


def test_test_returns_structured_model_list(client, monkeypatch, provider_module):
    _save(client)
    _mock_models(monkeypatch, provider_module, _models_payload(3))

    body = client.post("/api/provider/test", params={"ws": WS}).json()

    assert body["ok"] is True
    assert body["status"] == 200
    assert body["modelCount"] == 3
    assert body["models"] == ["model-0", "model-1", "model-2"]
    assert body["truncated"] is False
    assert body["hint"] == ""


def test_test_truncates_long_model_lists(client, monkeypatch, provider_module):
    """几千个模型不能整包塞给界面：截断要如实标注，总数照报。"""
    _save(client)
    limit = provider_module.MODEL_LIST_LIMIT
    _mock_models(monkeypatch, provider_module, _models_payload(limit + 7))

    body = client.post("/api/provider/test", params={"ws": WS}).json()

    assert len(body["models"]) == limit
    assert body["modelCount"] == limit + 7
    assert body["truncated"] is True
    assert body["hint"]


def test_test_handles_an_empty_model_list(client, monkeypatch, provider_module):
    """拉不到列表不代表不能用（很多网关没实现 /models）——空列表不是错误。"""
    _save(client)
    _mock_models(monkeypatch, provider_module, b"{}")

    body = client.post("/api/provider/test", params={"ws": WS}).json()

    assert body["ok"] is True
    assert body["models"] == []
    assert body["truncated"] is False


def test_test_wraps_http_errors_with_a_hint(client, monkeypatch, provider_module):
    import urllib.error

    _save(client)

    def _boom(req, timeout=None, purpose=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(provider_module.tls_http, "open_url", _boom)

    res = client.post("/api/provider/test", params={"ws": WS})
    assert res.status_code == 502, res.text
    body = res.json()
    assert body["error_code"] == "provider.connectHttpError"
    assert body["error_params"]["status"] == "401"


def test_test_wraps_unreachable_endpoints(client, monkeypatch, provider_module):
    import urllib.error

    _save(client)

    def _boom(req, timeout=None, purpose=None):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(provider_module.tls_http, "open_url", _boom)

    res = client.post("/api/provider/test", params={"ws": WS})
    assert res.status_code == 502, res.text
    assert res.json()["error_code"] == "provider.connectUnreachable"
