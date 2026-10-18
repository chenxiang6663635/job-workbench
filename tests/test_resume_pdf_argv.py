# -*- coding: utf-8 -*-
"""PDF 打印的命令行契约（CodeQL `py/command-line-injection` #194）。

告警原话：*This command line depends on a user-provided value*. 四条断言把
`pdf_print.build_pdf` 的纪律钉死——**argv 里只能出现常量与临时固定名**：

1. 可执行文件不在候选表 → 直接返回 False，**一个子进程都不起**；
2. argv[0] 是候选表里的字面量（不是调用方传进来的字符串）；
3. 传给浏览器的 HTML/PDF 路径都在临时目录里（固定名 `resume.html`/`resume.pdf`），
   用户可控的路径（`--out` / 工作区 / 版本名）**一个字符都不进 argv**；
4. 生成后 PDF 被搬到调用方指定的路径（用户路径只走文件系统 API）。

第 3 条是这个告警的正解：CodeQL 建议「用硬编码字面量，或在输入里选一个」——
清洗字符串是治标，把用户值赶出命令行才是治本。
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
    """一个「存在且被候选表收录」的假浏览器（CI 上没有真 Chrome 也能跑）。"""
    exe = tmp_path / "fake-browser.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(pdf_print, "BROWSER_CANDIDATES", [str(exe)])
    return str(exe)


def _html(tmp_path, name="resume_x.html"):
    p = tmp_path / name
    p.write_text("<html><body>hi</body></html>", encoding="utf-8")
    return str(p)


def test_non_allowlisted_browser_never_spawns_a_process(tmp_path, monkeypatch):
    """不在候选表里的可执行文件：返回 False，且**没有**任何子进程被启动。"""
    calls = []
    monkeypatch.setattr(pdf_print.subprocess, "run",
                        lambda *a, **kw: calls.append(a) or (_ for _ in ()).throw(
                            AssertionError("不该起子进程")))

    ok = pdf_print.build_pdf(str(tmp_path / "evil.exe"), _html(tmp_path),
                             str(tmp_path / "out.pdf"))

    assert ok is False
    assert calls == []


def test_argv_contains_only_constants_and_temp_paths(tmp_path, monkeypatch,
                                                     fake_browser):
    """argv[0] 是候选表字面量；其余路径都在临时目录里，用户目录不出现。"""
    user_dir = tmp_path / "用户选的输出目录"
    user_dir.mkdir()
    html_path = _html(tmp_path)
    pdf_path = str(user_dir / "简历_x.pdf")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        out = [c for c in cmd if c.startswith("--print-to-pdf=")][0]
        with open(out.split("=", 1)[1], "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    assert pdf_print.build_pdf(fake_browser, html_path, pdf_path) is True

    cmd = seen["cmd"]
    assert cmd[0] == fake_browser, "argv[0] 必须是候选表里的字面量"
    # 用户可控的两个**目录**（HTML 所在目录、输出目录）一个字符都不该出现在 argv 里。
    # argv[0] 是候选表常量、跳过（测试用的假浏览器恰好也在 tmp 下）。
    user_dirs = (os.path.dirname(html_path), str(user_dir))
    for arg in cmd[1:]:
        for bad in user_dirs:
            assert bad not in arg, "用户路径进了命令行：%s" % arg
    # 临时固定名
    joined = " ".join(cmd)
    assert "resume.html" in joined and "resume.pdf" in joined


def test_result_is_moved_to_the_requested_path(tmp_path, monkeypatch, fake_browser):
    """临时目录里的 PDF 生成后搬到调用方路径（用户路径只走文件系统 API）。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = str(out_dir / "简历_v1.pdf")

    def fake_run(cmd, **kwargs):
        out = [c for c in cmd if c.startswith("--print-to-pdf=")][0]
        with open(out.split("=", 1)[1], "wb") as fh:
            fh.write(b"%PDF-1.4 payload")

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    assert pdf_print.build_pdf(fake_browser, _html(tmp_path), target) is True
    with open(target, "rb") as fh:
        assert fh.read() == b"%PDF-1.4 payload"


def test_temp_dir_is_cleaned_up(tmp_path, monkeypatch, fake_browser):
    """无论成败，临时目录都不留（残留靠 TMP_PREFIX 可识别，这里断的是"没有残留"）。"""
    created = []
    real_mkdtemp = pdf_print.tempfile.mkdtemp

    def spy(*a, **kw):
        path = real_mkdtemp(*a, **kw)
        created.append(path)
        return path

    monkeypatch.setattr(pdf_print.tempfile, "mkdtemp", spy)
    monkeypatch.setattr(pdf_print.subprocess, "run", lambda *a, **kw: None)

    pdf_print.build_pdf(fake_browser, _html(tmp_path), str(tmp_path / "x.pdf"))

    assert created, "没建临时目录？"
    assert not any(os.path.exists(p) for p in created), "临时目录没清干净"
