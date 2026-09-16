# -*- coding: utf-8 -*-
"""简历端点参数化（批 4.5）：版式/风格清单、渲染参数传递与 422 语义。

钉住的核心口径（每条都对应一个真实会出事的场景）：

1. **同一真源**——`/layouts` 的版式与预设必须来自 resume_build 常量，
   前端与 CLI 不允许各维护一份清单；
2. **参数真的生效**——换 accent 渲染出的 HTML 必须换色、换版式必须换模板，
   而不是"收了参数、没传下去"；
3. **不静默回落**——非法 template / accent 一律 422（用户以为换了、实际没换
   比报错更难发现）；
4. **预览与导出同源**——doc 与 build 接受同一组参数（build 的参数校验
   先于环境检查，因此本文件不依赖 Chrome）。

本文件是 /api/resume 系端点的首个测试文件（此前为零覆盖）。
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

WS = "ws-ok"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import deps  # noqa: E402
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / "ws-ok").mkdir()

    import main  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402
    return TestClient(main.app)


def _seed_resume(tmp_path, version="backend"):
    """最小可渲染数据：render_block 按字段有无驱动区块，两个块足够断言。"""
    source = os.path.join(str(tmp_path), WS, "02_简历工坊", "source")
    os.makedirs(source)
    data = {
        "basics": {"name": "示例同学", "phone": "138-0000-0000",
                   "email": "demo@example.com", "location": "北京"},
        "meta": {"intent": "后端开发", "profile": "示例概况"},
    }
    with open(os.path.join(source, "resume_%s.json" % version), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False))
    return version


# ---- /layouts ---------------------------------------------------------------

def test_layouts_lists_templates_and_accents(client):
    res = client.get("/api/resume/layouts", params={"ws": WS})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "std_resume" in body["templates"]
    assert "std_compact" in body["templates"]
    assert "std_accent" in body["templates"]
    assert body["default"] == "std_resume"
    assert body["accents"]["酒红"] == "#7a2e3a"
    assert body["preferredAccent"] == "", "无偏好文件时应为空串"


def test_layouts_reads_preferred_accent(tmp_path, client):
    cfg = os.path.join(str(tmp_path), WS, "config")
    os.makedirs(cfg)
    with open(os.path.join(cfg, "preferences.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"resume_style": "深墨绿"}))
    res = client.get("/api/resume/layouts", params={"ws": WS})
    assert res.json()["preferredAccent"] == "深墨绿"


# ---- 预览：参数真的生效 -------------------------------------------------------

def test_preview_applies_accent(tmp_path, client):
    _seed_resume(tmp_path)
    base = client.get("/api/resume/backend/html", params={"ws": WS})
    assert base.status_code == 200, base.text
    assert "#2c5f8d" in base.json()["html"], "缺省应为模板默认色"

    res = client.get("/api/resume/backend/html",
                     params={"ws": WS, "accent": "酒红"})
    assert res.status_code == 200
    html = res.json()["html"]
    assert "#7a2e3a" in html
    assert "#2c5f8d" not in html, "强调色必须整体替换（风格只有一个入口）"


def test_preview_applies_template(tmp_path, client):
    _seed_resume(tmp_path)
    res = client.get("/api/resume/backend/html",
                     params={"ws": WS, "template": "std_compact"})
    assert res.status_code == 200
    assert "<title>求职简历（紧凑版式）</title>" in res.json()["html"]


def test_preview_rejects_bad_params(tmp_path, client):
    _seed_resume(tmp_path)
    res = client.get("/api/resume/backend/html",
                     params={"ws": WS, "template": "../etc"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "resume.templateInvalid"

    res = client.get("/api/resume/backend/html",
                     params={"ws": WS, "accent": "不存在色"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "resume.accentInvalid"


# ---- 导出：与预览同源 ---------------------------------------------------------

def test_doc_accepts_same_params(tmp_path, client):
    _seed_resume(tmp_path)
    res = client.get("/api/resume/backend/doc",
                     params={"ws": WS, "accent": "#123456"})
    assert res.status_code == 200
    assert "#123456" in res.text


def test_build_validates_params_before_environment(tmp_path, client):
    """422 先于 500 chromeMissing：输入问题不该被环境问题掩盖。"""
    _seed_resume(tmp_path)
    res = client.post("/api/resume/backend/build",
                      params={"ws": WS, "accent": "不存在色"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "resume.accentInvalid"
