# -*- coding: utf-8 -*-
"""未捕获异常的兜底契约 + 解释器基线判定（2026-09-15 实测缺陷的回归）。

缺陷现场：后端被 conda 的 Python 3.8 启动，用户点「拉取邮件」时 `imaplib` 抛
`TypeError: __init__() got an unexpected keyword argument 'timeout'`（该参数 3.9 才有）。
没有任何一层接住它 → 界面只看到一句裸的 "Internal Server Error"：没有错误码、没有
指向，用户能做的只有猜。

两条回归：
1. **未捕获异常必须变成结构化响应**（`error_code=server.error` + 可读 detail + 参数），
   而不是 Starlette 的纯文本 500——契约之外的错误也不许裸奔；
2. **解释器判定是纯函数**：<3.9 拒绝（技术不可用）、3.9–3.11 警告（未验证）、≥3.12 通过。
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import main  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_interpreter_verdict_levels():
    """三档判定：拒绝 / 警告 / 通过（阈值由技术要求与支持基线决定）。"""
    assert main.interpreter_verdict((3, 8, 19))[0] == "refuse"
    assert main.interpreter_verdict((3, 9, 0))[0] == "warn"
    assert main.interpreter_verdict((3, 11, 9))[0] == "warn"
    assert main.interpreter_verdict((3, 12, 8))[0] == "ok"
    assert main.interpreter_verdict((4, 0, 0))[0] == "ok"


def test_refuse_message_says_why_and_how():
    """拒绝时的说明必须包含**原因**（timeout 参数）与**出路**（换 3.12）。"""
    verdict, message = main.interpreter_verdict((3, 8, 19))
    assert verdict == "refuse"
    assert "timeout" in message
    assert "3.12" in message


def test_unhandled_handler_is_registered():
    """接线断言：兜底处理器必须挂在真实 app 上（只有它注册了，线上才生效）。"""
    assert Exception in main.app.exception_handlers


def test_unhandled_exception_is_wrapped_not_plain_text():
    """未捕获异常 → JSON 契约；不是纯文本 "Internal Server Error"。

    为什么用一个小 app 而不是往 `main.app` 上临时加路由：真实 app 末尾把
    `StaticFiles` 挂在 `/`（有 dist 时），**后注册的路由会被那个挂载先接走**
    （实测 404——这就是"路由顺序"的坑）。这里改为：钉住真实 app 的注册（上一条），
    再用同一处理器跑一次请求，两件事都测到。
    """
    app = FastAPI()
    app.add_exception_handler(Exception, main._unhandled_handler)

    @app.get("/api/__boom_for_test__")
    def _boom():  # pragma: no cover - 只为触发兜底路径
        raise RuntimeError("炸了")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/__boom_for_test__")

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["error_code"] == "server.error"
    assert "RuntimeError" in body["error_params"]["error"]
    assert "炸了" in body["detail"], "detail 必须带上异常本身，否则用户只能靠猜"
