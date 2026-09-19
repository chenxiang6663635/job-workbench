# -*- coding: utf-8 -*-
"""素材库的 HTTP 用例：列表（kind 分流 + 隐藏目录规则）与内容（文本/二进制）。

2026-09-18 补齐安全边界（此前素材库只有一层 safe_join）：realpath 二次确认
与笔记同款；反斜杠 case 的断言按平台分流（与 test_prep_api 同款说明——
Windows 上 `\\` 是路径分隔符、posix 上是普通文件名字符）。
"""

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
FACTS_DIR = "00_事实库"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _write(tmp_path, rel, content):
    path = tmp_path / WS / FACTS_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


# --- 列表 ---------------------------------------------------------------------


def test_list_marks_text_and_binary_everywhere(client, tmp_path):
    _write(tmp_path, "示例科技_后端/解析卡.md", "# 卡")
    _write(tmp_path, "示例科技_后端/项目图.png", b"\x89PNG")
    _write(tmp_path, ".obsidian/x.md", "# 隐藏")
    _write(tmp_path, "__pycache__/y.md", "# 产物")

    res = client.get("/api/library/facts", params={"ws": WS})
    assert res.status_code == 200
    by_rel = {item["rel"]: item for item in res.json()["items"]}
    # 隐藏目录规则随共享层对齐（.obsidian 不再出现）
    assert set(by_rel) == {"示例科技_后端/解析卡.md", "示例科技_后端/项目图.png"}
    assert by_rel["示例科技_后端/解析卡.md"]["kind"] == "text"
    assert by_rel["示例科技_后端/项目图.png"]["kind"] == "binary"


def test_list_empty_workspace(client):
    res = client.get("/api/library/facts", params={"ws": WS})
    assert res.status_code == 200
    assert res.json() == {"section": "facts", "items": [], "total": 0}


# --- 内容 ---------------------------------------------------------------------


def test_content_text_and_binary(client, tmp_path):
    _write(tmp_path, "卡.md", "# 正文")
    _write(tmp_path, "图.png", b"PNGBYTES")

    res = client.get("/api/library/facts/content", params={"ws": WS, "rel": "卡.md"})
    assert res.status_code == 200
    assert res.json() == {"rel": "卡.md", "type": "text", "content": "# 正文"}

    res = client.get("/api/library/facts/content", params={"ws": WS, "rel": "图.png"})
    assert res.status_code == 200
    assert res.json() == {"rel": "图.png", "type": "binary"}


def test_content_rejects_traversal(client, tmp_path):
    for bad in ("../config/profile.md", "/etc/passwd"):
        res = client.get("/api/library/facts/content", params={"ws": WS, "rel": bad})
        assert res.status_code == 400, bad
        assert res.json()["error_code"] == "path.illegalSegment", bad

    # 反斜杠：Windows 上按穿越拒（400），posix 上是普通文件名 → 文件不存在（404）
    res = client.get("/api/library/facts/content",
                     params={"ws": WS, "rel": "..\\config\\profile.md"})
    assert res.status_code == (400 if os.name == "nt" else 404)

    # URL 编码的 .. —— 服务端解码后必须同样被拒（原始 URL 直传，绕过 params 二次编码）
    res = client.get("/api/library/facts/content?ws=%s&rel=%%2e%%2e%%2fconfig.md" % WS)
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.illegalSegment"


def test_content_missing_file(client, tmp_path):
    res = client.get("/api/library/facts/content", params={"ws": WS, "rel": "无.md"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "lib.fileNotFound"


def test_unknown_section(client):
    res = client.get("/api/library/nope", params={"ws": WS})
    assert res.status_code == 404
    assert res.json()["error_code"] == "lib.unknownSection"


# --- 字节端点 -----------------------------------------------------------------


def test_file_endpoint_returns_bytes_with_media_type(client, tmp_path):
    _write(tmp_path, "图.png", b"PNGBYTES")
    res = client.get("/api/library/facts/file", params={"ws": WS, "rel": "图.png"})
    assert res.status_code == 200
    assert res.content == b"PNGBYTES"
    assert res.headers["content-type"].startswith("image/png")


def test_file_endpoint_rejects_traversal(client, tmp_path):
    res = client.get("/api/library/facts/file",
                     params={"ws": WS, "rel": "../config/profile.md"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.illegalSegment"


@pytest.mark.skipif(os.name != "posix", reason="符号链接场景仅在 POSIX 上验证")
def test_content_rejects_symlink_escape(client, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# secret", encoding="utf-8")
    base = tmp_path / WS / FACTS_DIR
    base.mkdir(parents=True, exist_ok=True)
    os.symlink(str(outside), str(base / "link"))

    res = client.get("/api/library/facts/content",
                     params={"ws": WS, "rel": "link/secret.md"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.escape"
