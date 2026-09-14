# -*- coding: utf-8 -*-
"""三个出网调用点的接线（issue #59 的验收：不得再有裸 `urlopen`）。

为什么单列一个文件：`test_tls_policy.py` / `test_tls_http.py` 只能证明"策略本身
是对的"，证明不了"有没有人真的在用它"。#59 的两处 MAJOR 恰恰都是**沉默失效**——
关校验的那处写得好好的（注释还给出了理由），没传上下文的两处看起来也完全正常，
三处都能通过 tsc / lint / 冒烟。所以这里对三个调用点各钉一条：捕获 `urlopen`
实际收到的 `context`，必须是策略给出的那个哨兵对象；再用一条扫描钉住"关证书
校验的捷径不许再出现"。
"""

import json
import os
import ssl
import sys
import urllib.request

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import tls_policy  # noqa: E402
from routers import jobs as jobs_router  # noqa: E402
from routers import provider as provider_router  # noqa: E402
from routers import resume as resume_router  # noqa: E402


class _Resp:
    """urlopen 的最小替身：三个调用点各自用到的属性都在。"""

    def __init__(self, payload=b"", content_type="text/html", status=200):
        self._payload = payload
        self.status = status
        self.headers = {"Content-Type": content_type}

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def sentinel_ctx(monkeypatch):
    """把策略换成哨兵：这三个用例只问"策略的产物有没有被传下去"。"""
    sentinel = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(tls_policy, "outbound_ssl_context",
                        lambda purpose, env_var: sentinel)
    return sentinel


def _capture_urlopen(monkeypatch, resp):
    captured = {}

    def _fake(req, timeout=None, context=None):
        captured["context"] = context
        captured["timeout"] = timeout
        return resp

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    return captured


def test_provider_test_connection_passes_policy_context(monkeypatch, sentinel_ctx):
    """Provider 连通性测试：策略的上下文必须到 urlopen（key 就挂在这个请求上）。"""
    monkeypatch.setattr(
        provider_router, "_read_config",
        lambda path: {"base_url": "https://api.example.com/v1", "api_key": "sk-test"})
    captured = _capture_urlopen(
        monkeypatch, _Resp(json.dumps({"data": [{"id": "m1"}]}).encode("utf-8"),
                           "application/json"))

    provider_router.test_provider(ws="ws-ok")

    assert captured["context"] is sentinel_ctx


def test_resume_llm_call_passes_policy_context(monkeypatch, sentinel_ctx):
    """简历改写：同一个策略，且 `Authorization: Bearer` 也在这个请求上。"""
    captured = _capture_urlopen(
        monkeypatch,
        _Resp(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8"),
              "application/json"))

    resume_router._call_llm({"base_url": "https://api.example.com/v1", "api_key": "sk-test"},
                            "prompt", "model-x")

    assert captured["context"] is sentinel_ctx


def test_jobs_fetch_jd_passes_policy_context(monkeypatch, sentinel_ctx, tmp_path):
    """JD 抓取：拿不到上下文时证书库损坏会抛 ASN1 原文，这条接线是用户可读报错的前提。"""
    ws = tmp_path / "ws-ok"
    ws.mkdir()
    html = ("<html><body><h1>热管理工程师</h1><p>"
            + "岗位职责与任职要求，负责热管理系统设计。" * 20
            + "</p></body></html>")
    captured = _capture_urlopen(monkeypatch, _Resp(html.encode("utf-8")))

    jobs_router.fetch_jd(
        jobs_router.FetchJdRequest(url="https://example.com/jd/1",
                                   公司="示例科技", 岗位="热管理工程师"),
        ws=str(ws))

    assert captured["context"] is sentinel_ctx


# ---- 扫描：#59 的验收原文（`grep -rn "_create_unverified_context" web/ tools/` 归零）----

def test_no_unverified_context_shortcut_left():
    """关证书校验的捷径不许再出现在 web/ 与 tools/ 的源码里。

    用扫描而不是 grep：这条纪律要跟着 CI 跑，靠人记得 grep 的约定等于没有。
    与那三个 issue 里的验收条目同源，改了判定就要同步改这里。
    """
    # 拼开写：保证本文件自己不会被这条规则扫到（否则就成了"豁免自己"的笑话）
    needle = "_create_unverified" + "_context"
    skip_dirs = ("node_modules", "release", "__pycache__", ".git", "dist")
    offenders = []
    for base in ("web", "tools"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT_DIR, base)):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for name in sorted(filenames):
                if not name.endswith((".py", ".js", ".ts", ".tsx")):
                    continue
                full = os.path.join(dirpath, name)
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if needle in line:
                            offenders.append("%s:%d"
                                             % (os.path.relpath(full, ROOT_DIR).replace("\\", "/"),
                                                lineno))
    assert offenders == [], (
        "出网一律走 tools/tls_policy.py；确需跳过校验只能由用户显式设环境变量。命中：%s"
        % offenders)
