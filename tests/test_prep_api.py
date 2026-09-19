# -*- coding: utf-8 -*-
"""笔记两个只读端点：列表（.md 平铺 + 服务端排序）与内容（截断诚实 + 三层防护）。

钉住四件容易悄悄坏掉的事：
1. **目录写死**：section 白名单之外 404；路径穿越（`..` / 绝对路径）与符号链接
   逃逸一律拒——`progress/questions.py:111-114` 的 MAJOR-1 教训就是"目录被做成参数"；
2. **截断诚实**：超 256KB 时 `truncated=true` 且 `bytes` 报**真实总字节**，
   截断切坏的多字节字符要能回退解码（不能吐乱码也不能 500）；
3. **只列 .md**：跳过 `.` 文件、`__` 目录与非 md；0 字节文件照常列出（不能消失）；
4. **读端点不落盘**：写通道由 approvals 唯一提供，本模块只读（无隐藏写路径）。
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
PREP_DIR = "03_面试准备"
KB_DIR = "04_知识库"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _write(tmp_path, rel, content, base=PREP_DIR):
    """在（默认）03_面试准备 下写文件；content 为 bytes 时按二进制写。"""
    path = tmp_path / WS / base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


# --- 列表 ---------------------------------------------------------------------


def test_list_returns_markdown_with_nested_rel_and_sorted(client, tmp_path):
    _write(tmp_path, "README.md", "# 目录说明")
    _write(tmp_path, "空文件.md", "")
    _write(tmp_path, "行为面/_模板_行为故事.md", "# 行为故事")
    _write(tmp_path, "行为面/缓存雪崩.md", "# 缓存雪崩")
    _write(tmp_path, "note.txt", "不是 md")
    _write(tmp_path, ".hidden.md", "# 隐藏")
    _write(tmp_path, "__pycache__/x.md", "# 运行时产物")
    _write(tmp_path, ".trash/旧笔记.md", "# 已删进回收站")

    res = client.get("/api/prep/interview", params={"ws": WS})
    assert res.status_code == 200
    data = res.json()
    rels = [item["rel"] for item in data["items"]]
    # 服务端 rel 字典序是唯一排序口径；非 md / . 文件 / __ 目录都不出现
    assert rels == ["README.md", "空文件.md",
                    "行为面/_模板_行为故事.md", "行为面/缓存雪崩.md"]
    assert data["total"] == 4
    # 0 字节文件照常列出（前端显示"空"标记——文件不能静默消失）
    empty = [item for item in data["items"] if item["rel"] == "空文件.md"][0]
    assert empty["size"] == 0


def test_list_knowledge_section(client, tmp_path):
    _write(tmp_path, "Redis 缓存速查卡.md", "# Redis", base=KB_DIR)
    res = client.get("/api/prep/knowledge", params={"ws": WS})
    assert res.status_code == 200
    assert res.json()["items"][0]["rel"] == "Redis 缓存速查卡.md"


def test_list_empty_workspace(client):
    res = client.get("/api/prep/interview", params={"ws": WS})
    assert res.status_code == 200
    assert res.json() == {"section": "interview", "items": [], "total": 0}


# --- 内容 ---------------------------------------------------------------------


def test_content_reads_and_strips_bom(client, tmp_path):
    _write(tmp_path, "自我介绍.md", "# 自我介绍".encode("utf-8-sig"))
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "自我介绍.md"})
    assert res.status_code == 200
    data = res.json()
    assert data["content"].startswith("# 自我介绍")  # BOM 已剥离
    assert data["truncated"] is False
    assert data["bytes"] > 0


def test_content_truncates_with_real_byte_count(client, tmp_path):
    # 360KB+ 且 256KB 处会切坏多字节字符（每字 3 字节，262144 不能被 3 整除）
    path = _write(tmp_path, "大文件.md", "# 大文件\n" + "字" * 120000)
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "大文件.md"})
    assert res.status_code == 200
    data = res.json()
    assert data["truncated"] is True
    assert data["bytes"] == os.path.getsize(str(path))  # 真实总字节，不是返回长度
    assert len(data["content"].encode("utf-8")) <= 256 * 1024
    assert data["content"].startswith("# 大文件")  # 回退解码成功，没吐乱码


def test_content_rejects_traversal(client, tmp_path):
    for bad in ("../config/profile.md", "/etc/passwd"):
        res = client.get("/api/prep/interview/content", params={"ws": WS, "rel": bad})
        assert res.status_code == 400, bad
        assert res.json()["error_code"] == "path.illegalSegment", bad

    # 反斜杠是 Windows 的路径分隔符：Windows 上按穿越拒绝；posix 上它是普通
    # 文件名字符、不构成穿越 → 落到"文件不存在"。两平台的语义各自钉住
    # （CI 在 Linux 跑，首版把这条当跨平台穿越断言，红在 CI——2026-09-18）。
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "..\\config\\profile.md"})
    if os.name == "nt":
        assert res.status_code == 400
        assert res.json()["error_code"] == "path.illegalSegment"
    else:
        assert res.status_code == 404
        assert res.json()["error_code"] == "prep.fileNotFound"

    # URL 编码的 .. —— 服务端解码后必须同样被拒（原始 URL 直传，绕过 params 二次编码）
    res = client.get("/api/prep/interview/content?ws=%s&rel=%%2e%%2e%%2fconfig.md" % WS)
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.illegalSegment"


@pytest.mark.skipif(os.name != "posix", reason="符号链接场景仅在 POSIX 上验证")
def test_content_rejects_symlink_escape(client, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# secret", encoding="utf-8")
    link_dir = tmp_path / WS / PREP_DIR
    link_dir.mkdir(parents=True, exist_ok=True)
    os.symlink(str(outside), str(link_dir / "link"))

    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "link/secret.md"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.escape"


@pytest.mark.skipif(os.name != "posix", reason="符号链接场景仅在 POSIX 上验证")
def test_list_rejects_symlinked_section_dir(client, tmp_path):
    """section 目录本身被替换成外部链接 → 整体拒绝（锚点=工作区根，MINOR-2）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "外.md").write_text("# 外", encoding="utf-8")
    os.symlink(str(outside), str(tmp_path / WS / PREP_DIR))

    res = client.get("/api/prep/interview", params={"ws": WS})
    assert res.status_code == 400
    assert res.json()["error_code"] == "path.escape"


def test_content_rejects_non_markdown(client, tmp_path):
    _write(tmp_path, "笔记.txt", "纯文本")
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "笔记.txt"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "prep.notMarkdown"


def test_content_missing_file(client, tmp_path):
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "无此文件.md"})
    assert res.status_code == 404
    body = res.json()
    assert body["error_code"] == "prep.fileNotFound"
    assert body["error_params"]["rel"] == "无此文件.md"


def test_unknown_section(client):
    res = client.get("/api/prep/unknown", params={"ws": WS})
    assert res.status_code == 404
    body = res.json()
    assert body["error_code"] == "prep.unknownSection"
    assert body["error_params"]["section"] == "unknown"


def test_content_rejects_non_utf8(client, tmp_path):
    """非 UTF-8 字节 → 明确失败，不用 errors="replace" 静默糊住真乱码。"""
    _write(tmp_path, "坏编码.md", "中文内容".encode("gbk"))
    res = client.get("/api/prep/interview/content",
                     params={"ws": WS, "rel": "坏编码.md"})
    assert res.status_code == 500
    body = res.json()
    assert body["error_code"] == "prep.readFailed"
    assert body["error_params"]["rel"] == "坏编码.md"
