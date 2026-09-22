# -*- coding: utf-8 -*-
"""岗位新建（job.create）与 JD 抓取（jd.fetch）的 HTTP 契约（T 批补网）。

这两个端点**仅 GUI 提供**（四端矩阵里的刻意例外：新建与抓取都需要界面里的
粘贴动作），此前只有证书接线（test_tls_wiring）与四端探针的覆盖，拒绝分支
零测试。这里钉住：

1. 新建：422（公司与岗位为空 / JD 为空）、409（同名岗位已存在）+ 往返落盘；
2. 抓取：422（缺公司岗位 / 非 http(s) 链接 / 抓到内容过短）；
3. 抓取失败降级：出网异常 → 502 + 稳定 error_code（可读拒绝，不是栈）。
"""

import io
import os
import sys
import urllib.error

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
import tls_http  # noqa: E402

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
    """tls_http.open_url 的最小替身（with 语句 + headers + read）。"""

    def __init__(self, payload=b"", content_type="text/html; charset=utf-8"):
        self._payload = payload
        self.headers = {"Content-Type": content_type}

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _stub_fetch(monkeypatch, resp=None, boom=None):
    def _fake(req, timeout=None, purpose=None):
        if boom is not None:
            raise boom
        return resp

    monkeypatch.setattr(tls_http, "open_url", _fake)


LONG_HTML = ("<html><body><h1>热管理工程师</h1><p>"
             + "岗位职责与任职要求，负责热管理系统设计与仿真验证。" * 10
             + "</p></body></html>").encode("utf-8")


# --- 新建岗位 -----------------------------------------------------------------


def test_create_job_roundtrip(client, tmp_path):
    ws_dir = str(tmp_path / WS)

    res = client.post("/api/jobs", params={"ws": WS}, json={
        "公司": "云帆", "岗位": "后端开发", "JD文本": "岗位职责：写代码。"})

    assert res.status_code == 200, res.text
    assert res.json()["dir"] == "云帆_后端开发"
    jd = io.open(os.path.join(ws_dir, "01_岗位池", "云帆_后端开发", "JD原文.md"),
                 encoding="utf-8").read()
    assert jd.startswith("# 云帆 后端开发")
    assert "岗位职责：写代码。" in jd


def test_create_job_reject_branches_use_stable_codes(client, tmp_path):
    res = client.post("/api/jobs", params={"ws": WS}, json={
        "公司": "  ", "岗位": "后端", "JD文本": "x"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "job.companyRoleRequired"

    res = client.post("/api/jobs", params={"ws": WS}, json={
        "公司": "云帆", "岗位": "后端", "JD文本": "   "})
    assert res.status_code == 422
    assert res.json()["error_code"] == "job.jdRequired"

    body = {"公司": "云帆", "岗位": "后端", "JD文本": "职责。"}
    assert client.post("/api/jobs", params={"ws": WS}, json=body).status_code == 200
    res = client.post("/api/jobs", params={"ws": WS}, json=body)
    assert res.status_code == 409
    payload = res.json()
    assert payload["error_code"] == "job.exists"
    assert payload["error_params"]["name"] == "云帆_后端"


# --- JD 抓取 ------------------------------------------------------------------


def test_fetch_jd_reject_branches_use_stable_codes(client, tmp_path):
    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "https://example.com/jd/1", "公司": "", "岗位": ""})
    assert res.status_code == 422
    assert res.json()["error_code"] == "job.companyRoleRequired"

    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "example.com/jd/1", "公司": "云帆", "岗位": "后端"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "job.urlInvalid"


def test_fetch_jd_success_writes_jd_and_reports_chars(client, tmp_path, monkeypatch):
    ws_dir = str(tmp_path / WS)
    _stub_fetch(monkeypatch, resp=_Resp(LONG_HTML))

    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "https://example.com/jd/1", "公司": "云帆", "岗位": "热管理工程师"})

    assert res.status_code == 200, res.text
    assert res.json()["characters"] > 0
    jd = io.open(os.path.join(ws_dir, "01_岗位池", "云帆_热管理工程师",
                              "JD原文.md"), encoding="utf-8").read()
    assert "来源：https://example.com/jd/1" in jd
    assert "热管理工程师" in jd


def test_fetch_jd_short_content_is_readable_error(client, tmp_path, monkeypatch):
    _stub_fetch(monkeypatch, resp=_Resp(b"<html><body>hi</body></html>"))

    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "https://example.com/jd/2", "公司": "云帆", "岗位": "后端"})

    assert res.status_code == 422
    body = res.json()
    assert body["error_code"] == "job.fetchTooShort"
    assert "chars" in body["error_params"]


def test_fetch_jd_http_failure_degrades_to_readable_code(client, tmp_path, monkeypatch):
    _stub_fetch(monkeypatch, boom=urllib.error.HTTPError(
        "https://example.com/x", 403, "Forbidden", None, None))

    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "https://example.com/x", "公司": "云帆", "岗位": "后端"})

    assert res.status_code == 502
    assert res.json()["error_code"] == "job.fetchHttpError"


def test_fetch_jd_unreachable_degrades_to_readable_code(client, tmp_path, monkeypatch):
    _stub_fetch(monkeypatch, boom=urllib.error.URLError("connection refused"))

    res = client.post("/api/jobs/fetch-jd", params={"ws": WS}, json={
        "url": "https://example.com/x", "公司": "云帆", "岗位": "后端"})

    assert res.status_code == 502
    assert res.json()["error_code"] == "job.fetchUnreachable"
