# -*- coding: utf-8 -*-
"""PDF 镜像的**资源预算**（外部审计 2026-10-18 §三 最后一行"尚未证明"）。

审计原话：扩展名白名单只回答「哪种类型允许参与复制」，还没回答
「允许复制多少内容？」——所以「极大图片 / 大量合法扩展名文件」需要有明确策略。

本文件钉住三条契约：

1. 超出预算 → **明确失败**，不做部分复制、不静默搬完；
2. 预算只算**会被镜像**的类型（白名单内）——目录里堆着大量 `.md` / `.csv`
   不该因此渲染失败（那些本来就不复制）；
3. 正常规模不受影响（真实模板实测最大目录 = 3 个文件 / 0.01 MB）。

阈值的选择依据写在 `pdf_print.py` 的常量注释里（实测模板规模，不是凭空拍）。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(ROOT, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import pdf_print  # noqa: E402


@pytest.fixture()
def fake_browser(tmp_path, monkeypatch):
    exe = tmp_path / "fake-browser.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(pdf_print, "BROWSER_CANDIDATES", [str(exe)])
    return str(exe)


def _no_spawn(monkeypatch):
    """渲染不该被启动——超预算时连临时目录都不该建到 copytree。"""
    calls = []

    def boom(*a, **kw):
        calls.append(a)
        raise AssertionError("超预算却仍然起了子进程")

    monkeypatch.setattr(pdf_print.subprocess, "run", boom)
    return calls


def test_too_many_renderable_files_is_refused(tmp_path, monkeypatch, fake_browser):
    """数量超预算 → 拒绝，且不启动浏览器。

    用小阈值（2）而不是造 400 个真文件：验的是**判据**，不是磁盘。
    """
    monkeypatch.setattr(pdf_print, "MAX_MIRROR_FILES", 2)
    for i in range(4):
        (tmp_path / ("photo_%d.jpg" % i)).write_bytes(b"\xff\xd8\xff\xd9")
    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")
    calls = _no_spawn(monkeypatch)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is False, "超出文件数预算却仍然渲染了"
    assert calls == [], "拒绝路径不该起子进程"


def test_too_many_bytes_is_refused(tmp_path, monkeypatch, fake_browser):
    """字节数超预算 → 拒绝（大图片场景）。"""
    monkeypatch.setattr(pdf_print, "MAX_MIRROR_BYTES", 1024)
    (tmp_path / "big.png").write_bytes(b"x" * 4096)
    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")
    calls = _no_spawn(monkeypatch)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is False, "超出字节预算却仍然渲染了"
    assert calls == []


def test_budget_ignores_non_renderable_files(tmp_path, monkeypatch, fake_browser):
    """预算只算白名单内的类型——堆一堆 `.md` / `.csv` 不该让渲染失败。

    这条是"白名单 + 预算"的语义边界：不复制的东西，也不该计入预算。
    """
    monkeypatch.setattr(pdf_print, "MAX_MIRROR_FILES", 2)
    monkeypatch.setattr(pdf_print, "MAX_MIRROR_BYTES", 1024)
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    for i in range(50):
        (tmp_path / ("note_%02d.md" % i)).write_text("无关内容", encoding="utf-8")
    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        staged = [c for c in cmd if c.endswith(os.sep + "resume.html")][0]
        with open(os.path.join(os.path.dirname(staged), "resume.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is True, "无关文件把预算吃掉了（白名单语义被破坏）"


def test_budget_message_is_actionable(tmp_path, monkeypatch, fake_browser):
    """失败文案要说清**怎么办**，不能只说"未生成"。"""
    monkeypatch.setattr(pdf_print, "MAX_MIRROR_FILES", 1)
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / "b.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")

    text = pdf_print.failure_text(str(html), str(tmp_path / "out.pdf"))

    assert "资源" in text or "文件" in text, text
    assert "移出" in text or "目录" in text, text
    assert text != "PDF 未生成（浏览器打印失败或超时）", "回落到通用文案了"


def test_normal_scale_still_renders(tmp_path, monkeypatch, fake_browser):
    """不回归：真实模板规模（几个文件 / 几 KB）必须照常渲染。"""
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9" * 100)
    (tmp_path / "style.css").write_text("body{}", encoding="utf-8")
    html = tmp_path / "resume.html"
    html.write_text("<html><img src='photo.jpg'></html>", encoding="utf-8")

    seen = {}

    def fake_run(cmd, **kwargs):
        staged = [c for c in cmd if c.endswith(os.sep + "resume.html")][0]
        seen["names"] = sorted(os.listdir(os.path.dirname(staged)))
        with open(os.path.join(os.path.dirname(staged), "resume.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is True
    assert "photo.jpg" in seen["names"] and "style.css" in seen["names"]
