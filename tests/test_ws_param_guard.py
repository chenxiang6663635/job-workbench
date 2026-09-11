# -*- coding: utf-8 -*-
"""#22 的回归：工作区参数写错时，请求不得静默回退默认工作区。

事故形态（issue #22）：客户端把 `ws` 写成 `workspace`，FastAPI **默认忽略未知查询
参数**，于是 `ws=None` → 回退默认工作区（`personal/`，真实数据）→ 200。
更糟的是：错误请求与正确请求返回的**行数恰好相同**，只看条数会「验证通过」。

所以这里断言的不是「有没有报错」，而是三件事：
  1. 近名错拼的参数被**明确拒绝**（400），且消息点明正确参数名；
  2. 每个响应都**回显实际服务的工作区**，调用方据此可自检；
  3. 既有的 400/404 校验**不放松**（绝对路径、不存在的工作区）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "web", "backend"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HEADER = "X-Jobws-Workspace"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把应用根指到临时目录，并建两个工作区。

    不依赖仓库里真实的 `personal/`：CI 上它不存在（已被 gitignore），
    依赖它会让测试在本地绿、CI 红。
    """
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    # APPDATA 也要隔离：快照目录走系统用户目录，不隔离会读到开发机上的真实快照
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / "personal").mkdir()
    (tmp_path / "ws-ok").mkdir()

    import main  # noqa: E402  （在 ROOT 被改写之后导入，避免读到真实仓库根）
    return TestClient(main.app)


def test_echoes_resolved_workspace(client):
    """每个响应都要回显「实际服务的是哪个工作区」——把静默错误变成可察觉错误。"""
    resp = client.get("/api/system/paths", params={"ws": "ws-ok"})
    assert resp.status_code == 200
    assert resp.headers.get(HEADER) == "ws-ok"


def test_echoes_default_workspace_when_absent(client):
    resp = client.get("/api/system/paths")
    assert resp.status_code == 200
    assert resp.headers.get(HEADER) == "personal"


def test_near_miss_param_is_rejected_not_ignored(client):
    """核心回归：`?workspace=` 不能再被静默忽略。

    FastAPI 默认忽略未知查询参数，这正是 #22 的成因——参数被丢掉后
    回退默认工作区，返回 200 + 真实数据。
    """
    resp = client.get("/api/system/paths", params={"workspace": "ws-ok"})
    assert resp.status_code == 400, "近名错拼的参数必须被拒绝，而不是静默回退默认工作区"
    assert "ws" in resp.text, "报错要点明正确参数名，否则调用方不知道该改什么"


def test_rejection_does_not_leak_default_workspace(client):
    """被拒的请求不得携带任何默认工作区的数据。"""
    resp = client.get("/api/system/paths", params={"workspace": "ws-ok"})
    assert "snapshotDir" not in resp.text, "被拒响应里不应出现默认工作区的信息"


def test_rejection_carries_cors_header(client):
    """被拒的 400 必须带 CORS 头，否则浏览器会把它拦成「网络错误」。

    `@app.middleware("http")` 是**后注册的在最外层**：若在中间件里直接 return
    JSONResponse，就绕过了 CORSMiddleware，浏览器读不到这个 400 的正文——
    前端只会看到 TypeError，而不是「参数名写错了」。
    """
    resp = client.get("/api/system/paths", params={"workspace": "ws-ok"},
                      headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 400
    assert resp.headers.get("access-control-allow-origin"), \
        "缺 CORS 头：前端读不到这条可读的 400"


def test_case_variant_and_plural_are_rejected(client):
    """近名比对必须大小写不敏感，且要覆盖复数形式。

    查询参数名大小写敏感（HTTP 语义）：`?Workspace=` 不在小写清单里就会被
    FastAPI 当未知参数丢掉——**复现与 #22 一字不差的静默回退**。
    大小写变体（PascalCase 的脚本作者、Swagger 生成的代码）与
    `workspaces`（受 /api/workspaces 端点名诱导）是同等常见的错拼来源。
    """
    for bad in ("Workspace", "WS", "WORKSPACE", "workspaces"):
        resp = client.get("/api/system/paths", params={bad: "ws-ok"})
        assert resp.status_code == 400, f"`{bad}` 必须被拒绝而不是静默回退默认工作区"


def test_empty_ws_value_is_rejected(client):
    """`?ws=`（显式空值）也不得静默回退默认工作区。

    前端只在选中工作区时才拼 ws，所以空值只可能来自拼模板串的第三方脚本——
    它拿到的是「没点名的工作区」+ 200，与「静默回退即危险」的立场冲突。
    """
    resp = client.get("/api/system/paths", params={"ws": ""})
    assert resp.status_code == 400


def test_echo_is_the_normalized_workspace_name(client):
    """回显的应是归一化后的工作区名，而不是原始输入串。

    `?ws=./personal` 实际服务的就是 personal；回显原始串 `./personal`
    会让按期望值比对的客户端误报不一致（fail-closed，无安全洞，只是噪音）。
    顺带记录：`?ws=personal/../` 会 normpath 到仓库根本身 → 400（fail-closed）。
    """
    resp = client.get("/api/system/paths", params={"ws": "./personal"})
    assert resp.status_code == 200
    assert resp.headers.get(HEADER) == "personal"


def test_unknown_workspace_still_404(client):
    """既有校验不放松：工作区不存在仍是 404（不是回退默认）。"""
    resp = client.get("/api/system/paths", params={"ws": "definitely-not-here"})
    assert resp.status_code == 404


def test_absolute_path_still_400(client):
    """既有校验不放松：绝对路径仍被拒。"""
    resp = client.get("/api/system/paths", params={"ws": "/etc"})
    assert resp.status_code == 400
