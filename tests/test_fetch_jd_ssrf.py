# -*- coding: utf-8 -*-
"""`POST /api/jobs/fetch-jd` 的 SSRF 拒绝（CodeQL `py/full-ssrf` #2）。

三条契约：

1. **内网/本机地址在发请求之前就被拒**（422 + `job.urlBlocked`），且
   `tls_http.open_url` **一次都没被调用**——"拒绝了"必须等于"没出网"；
2. 公网地址放行时**带 `public_only=True`** 出门（守卫在 tls_http 里对每一跳
   （含重定向）复检，而不是只在入口查一次）；
3. 重定向到内网被拦（`tls_http` 的 redirect handler 直接单测——真起一个会
   302 的服务器既慢又要有网）。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
import tls_http  # noqa: E402
from jobws_core import outbound  # noqa: E402

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


class _Resp:
    def __init__(self, payload=b"<html>" + b"JD" * 500 + b"</html>"):
        self._payload = payload
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765/api/applications",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.1.2.3/internal",
    "http://[::1]/x",
])
def test_private_target_rejected_without_touching_the_network(client, monkeypatch, url):
    """拒绝 = 不出网：`open_url` 被换成炸弹，一旦调用测试就红。"""
    def boom(*a, **kw):
        raise AssertionError("内网地址居然出了网：%r" % (a, kw))

    monkeypatch.setattr(tls_http, "open_url", boom)

    res = client.post("/api/jobs/fetch-jd",
                      params={"ws": WS},
                      json={"url": url, "公司": "某公司", "岗位": "后端"})

    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "job.urlBlocked"
    assert res.json()["detail"], "detail 是既有契约，不能只剩 code"


def test_malformed_port_reports_url_invalid(client, monkeypatch):
    """畸形端口（`:abc` / 越界）是"链接写得不对"，不是"指向内网"——文案不能串。

    走 `job.urlInvalid`（既有 code，且**不带参数**——与另一处抛出点的参数集一致，
    `test_error_code_params` 会核对）。
    """
    def boom(*a, **kw):
        raise AssertionError("畸形 URL 不该出网")

    monkeypatch.setattr(tls_http, "open_url", boom)

    res = client.post("/api/jobs/fetch-jd",
                      params={"ws": WS},
                      json={"url": "http://a.com:abc/x", "公司": "某公司", "岗位": "后端"})

    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "job.urlInvalid"


def test_public_target_passes_public_only_flag(client, monkeypatch):
    """公网地址才放行，且必须让 tls_http 逐跳复检（`public_only=True`）。"""
    seen = {}

    def fake_open(req, timeout=None, purpose=None, **kwargs):
        seen["url"] = req.full_url
        seen["public_only"] = kwargs.get("public_only")
        return _Resp()

    monkeypatch.setattr(tls_http, "open_url", fake_open)
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *a, **kw: [
        (2, 1, 6, "", ("93.184.216.34", 443))])

    res = client.post("/api/jobs/fetch-jd",
                      params={"ws": WS},
                      json={"url": "https://jobs.example.com/p/1",
                            "公司": "某公司", "岗位": "后端"})

    assert res.status_code == 200, res.text
    assert seen["public_only"] is True, "守卫必须交给 tls_http 逐跳复检"


def test_redirect_to_private_is_blocked(client, monkeypatch):
    """重定向到内网：redirect handler 必须复检并拒绝（不能只查首个 URL）。"""
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *a, **kw: [
        (2, 1, 6, "", ("127.0.0.1", 80))])

    handler = tls_http.public_only_redirect_handler()
    req = tls_http.urllib.request.Request("https://jobs.example.com/p/1")

    with pytest.raises(outbound.OutboundBlocked):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "http://127.0.0.1:8765/api/applications")
