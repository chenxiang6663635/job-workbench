# -*- coding: utf-8 -*-
"""PDF 生成链的**链接边界**（2026-10-18 外部审计指出，本轮实证补上）。

上一轮加了 `copytree(symlinks=True)` 并配了一条接线断言。外部审计纠正了那个保证的
**范围**：它只证明「复制阶段不展开链接内容」，不证明

- 后续 `shutil.copyfile()` 不会读取外部目标（`copyfile` 默认**跟随**源链接）；
- 保留下来的链接不会被 Chrome 渲染时跟随；
- `shutil.move()` 在跨文件系统回退到 `copy2` 时不会覆盖外部文件。

本文件把这三条连同 Windows junction 一起钉死。**平台说明**：本机（Windows 无
SeCreateSymbolicLinkPrivilege）建不了文件符号链接，相关用例自动 skip 并在 CI
（ubuntu）上真实执行；**junction 不需要管理员，这里就是真证据**。
"""

import hashlib
import os
import shutil
import subprocess
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


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _mklink_junction(link, target):
    """Windows junction（不需要管理员）；非 Windows 返回 False。"""
    if os.name != "nt":
        return False
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, text=True)
    return r.returncode == 0 and os.path.isdir(link)


# --- 一、源目录里的链接 ---------------------------------------------------------

def test_junction_in_source_dir_is_refused(tmp_path, monkeypatch, fake_browser):
    """**Windows 真证据**：源目录里的 junction 必须被拒绝，且外部内容不被读取。

    实证（本机 2026-10-18）：`os.path.islink()` 对 junction 返回 **False**，
    而 `copytree(symlinks=True)` 会把 junction 原样搬过去并**仍指向外部**——
    透过镜像就能读到 sentinel。所以 `symlinks=True` 对 junction 不构成防护，
    必须在镜像前显式拒绝。
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "secret.txt"
    sentinel.write_text("SENTINEL-OUTSIDE", encoding="utf-8")

    src = tmp_path / "pdf"
    src.mkdir()
    html = src / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")

    junc = src / "assets"
    if not _mklink_junction(str(junc), str(outside)):
        pytest.skip("本平台无法创建 junction")

    seen = {}

    def fake_run(cmd, **kwargs):
        staged = [c for c in cmd if c.endswith(os.sep + "resume.html")][0]
        work = os.path.dirname(staged)
        seen["work"] = work
        seen["names"] = sorted(os.listdir(work))
        with open(os.path.join(work, "resume.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is False, "源目录含 junction 却仍然渲染了"
    # 即使渲染了，也不该把外部内容带进临时目录
    if "work" in seen:
        assert "assets" not in seen["names"], "junction 被镜像且仍指向外部"


def test_file_symlink_in_source_dir_is_refused(tmp_path, monkeypatch, fake_browser):
    """源目录里的**文件**符号链接：拒绝，且不读取链接目标内容。

    本机建不了文件符号链接（WinError 1314）→ skip；CI（ubuntu）上真实执行。
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "secret.txt"
    sentinel.write_text("SENTINEL-OUTSIDE", encoding="utf-8")

    src = tmp_path / "pdf"
    src.mkdir()
    html = src / "resume.html"
    html.write_text("<html><img src='photo.png'></html>", encoding="utf-8")
    link = src / "photo.png"
    try:
        os.symlink(str(sentinel), str(link))
    except OSError:
        pytest.skip("本平台不允许创建文件符号链接（CI ubuntu 上会真实执行）")

    seen = {}

    def fake_run(cmd, **kwargs):
        staged = [c for c in cmd if c.endswith(os.sep + "resume.html")][0]
        work = os.path.dirname(staged)
        seen["work"] = work
        seen["names"] = sorted(os.listdir(work))
        seen["photo_content"] = None
        p = os.path.join(work, "photo.png")
        if os.path.isfile(p) and not os.path.islink(p):
            with open(p, "rb") as fh:
                seen["photo_content"] = fh.read()
        with open(os.path.join(work, "resume.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert ok is False, "源目录含符号链接却仍然渲染了"
    assert seen.get("photo_content") != b"SENTINEL-OUTSIDE", \
        "链接目标内容被读进了临时目录"


def test_html_source_itself_being_a_symlink_is_refused(tmp_path, monkeypatch,
                                                       fake_browser):
    """**HTML 本身**是符号链接：`copyfile()` 默认跟随源链接 → 会读取外部内容。

    这一条与「目录里有链接」是两回事：copytree 的白名单/链接策略都管不到它，
    因为它是从 `html_path` 直接 `copyfile` 过去的。
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    real_html = outside / "real.html"
    real_html.write_text("<html>外部 HTML</html>", encoding="utf-8")

    src = tmp_path / "pdf"
    src.mkdir()
    link_html = src / "resume.html"
    try:
        os.symlink(str(real_html), str(link_html))
    except OSError:
        pytest.skip("本平台不允许创建文件符号链接（CI ubuntu 上会真实执行）")

    seen = {}

    def fake_run(cmd, **kwargs):
        staged = [c for c in cmd if c.endswith(os.sep + "resume.html")][0]
        seen["staged_content"] = open(staged, encoding="utf-8", errors="replace").read()
        with open(os.path.join(os.path.dirname(staged), "resume.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    ok = pdf_print.build_pdf(fake_browser, str(link_html), str(tmp_path / "out.pdf"))

    assert ok is False, "HTML 本身是符号链接却仍然渲染了"
    assert "外部 HTML" not in (seen.get("staged_content") or ""), \
        "copyfile 跟随了源链接，把外部 HTML 内容读进了临时目录"


# --- 二、输出目标上的链接 -------------------------------------------------------

def test_pdf_target_being_a_symlink_is_refused(tmp_path, monkeypatch, fake_browser):
    """**输出 PDF 已存在且是指向外部文件的符号链接**：必须拒绝，外部文件字节不变。

    `shutil.move()` 在同文件系统用 `os.rename`（替换链接本身），但**跨文件系统**
    会回退到 `copy2` + 删源——`copy2` 跟随**目标**链接，于是外部文件被覆盖。
    这正是审计要求补的负向测试：用 sentinel 哈希判「外部文件未被修改」。
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.pdf"
    sentinel.write_bytes(b"%PDF-EXTERNAL-DO-NOT-TOUCH")
    before = _sha(sentinel)

    src = tmp_path / "pdf"
    src.mkdir()
    html = src / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")

    target = tmp_path / "out" / "resume_x.pdf"
    target.parent.mkdir()
    try:
        os.symlink(str(sentinel), str(target))
    except OSError:
        pytest.skip("本平台不允许创建文件符号链接（CI ubuntu 上会真实执行）")

    def fake_run(cmd, **kwargs):
        out = [c for c in cmd if c.startswith("--print-to-pdf=")][0]
        with open(out.split("=", 1)[1], "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(pdf_print.subprocess, "run", fake_run)

    pdf_print.build_pdf(fake_browser, str(html), str(target))

    assert _sha(sentinel) == before, \
        "外部 sentinel 被改了——shutil.move 的跨卷回退跟随了目标符号链接"
