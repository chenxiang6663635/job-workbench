# -*- coding: utf-8 -*-
"""`pdf_print.build_pdf` 的**目录镜像范围**契约（2026-10-18 外部审计要求补的负向测试）。

背景：为了让「手写 HTML 用相对路径引同目录照片」不失效，#325 把 HTML 所在目录
`copytree` 进临时目录。但「除 PDF 外全拷」意味着**同目录里的任何文件都会被复制出
工作区**——外部审计指出三种必须验证的情形：

1. 目录含大量无关文件 → 磁盘占用与读放大；
2. 子目录含指向外部的符号链接 → `copytree` 默认**跟随**链接并复制目标内容；
3. HTML 所在目录含敏感但无关的文件 → 被暂时复制到临时目录。

本文件把这三条钉死，并锁住「渲染可能引用的类型仍被镜像」这一条不回归
（照片失效正是 #325 自己踩过的坑：200×300 → 14×16 占位图标）。
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


def _capture_mirror(monkeypatch):
    """跑一次 build_pdf，把临时目录里的文件清单抓出来（不起真浏览器）。"""
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
    return seen


def _stage(tmp_path, monkeypatch, **files):
    """在 tmp_path 下造一个 HTML + 若干伴随文件，返回 (html_path, seen)。"""
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    html = tmp_path / files.pop("_html", "resume.html") if "_html" in files else None
    return html


def test_render_assets_are_still_mirrored(tmp_path, monkeypatch, fake_browser):
    """不回归：照片 / CSS / 字体这些**渲染真要引**的类型必须被镜像过去。

    这条是 #325 自己踩过的坑的回归网——只搬 HTML 会让相对引用的照片静默丢失
    （实测图片 XObject 从 200×300 退化成 14×16 占位图标）。
    """
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / "style.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "font.woff2").write_bytes(b"w0FF")
    html = tmp_path / "resume.html"
    html.write_text("<html><img src='photo.jpg'></html>", encoding="utf-8")

    seen = _capture_mirror(monkeypatch)
    pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    for must in ("resume.html", "photo.jpg", "style.css", "font.woff2"):
        assert must in seen["names"], "渲染需要的 %s 没被镜像：%s" % (must, seen["names"])


def test_unrelated_files_are_not_mirrored(tmp_path, monkeypatch, fake_browser):
    """同目录里的**无关文件**不该被复制出工作区（外部审计情形 3）。

    这些是用户放在同一个 pdf 目录里的笔记 / 导出 / 其它版本简历——与渲染无关，
    复制进临时目录等于把内容搬出一个它本不该出的位置（且崩溃时会留在 TEMP）。
    """
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / "面试笔记.md").write_text("敏感：面试官提到薪资范围", encoding="utf-8")
    (tmp_path / "投递记录.csv").write_text("公司,岗位\n某公司,后端\n", encoding="utf-8")
    (tmp_path / "resume_old.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("私人备注", encoding="utf-8")
    html = tmp_path / "resume.html"
    html.write_text("<html><img src='photo.jpg'></html>", encoding="utf-8")

    seen = _capture_mirror(monkeypatch)
    pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    for must_not in ("面试笔记.md", "投递记录.csv", "resume_old.json", "notes.txt"):
        assert must_not not in seen["names"], \
            "无关文件被镜像出工作区：%s（实际 %s）" % (must_not, seen["names"])


def test_copytree_is_told_not_to_follow_symlinks(tmp_path, monkeypatch, fake_browser):
    """接线断言：`copytree` 必须收到 `symlinks=True`（任何平台都能验）。

    行为测试（下面那条）在 Windows 无开发者模式时建不了符号链接会被跳过，
    所以把「保护本身」单独钉住：`shutil.copytree` 默认 `symlinks=False`，
    意味着它会**跟随**链接并把目标内容复制进来。
    """
    seen = {}

    def fake_copytree(src, dst, **kwargs):
        seen["kwargs"] = kwargs
        os.makedirs(dst, exist_ok=True)
        return dst

    monkeypatch.setattr(pdf_print.shutil, "copytree", fake_copytree)
    monkeypatch.setattr(pdf_print.subprocess, "run", lambda *a, **kw: None)

    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")
    pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    assert seen["kwargs"].get("symlinks") is True, \
        "没传 symlinks=True：copytree 会跟随符号链接并复制目标内容（%r）" % seen["kwargs"]
    assert callable(seen["kwargs"].get("ignore")), "没传 ignore 回调"


def test_symlink_to_outside_is_not_followed(tmp_path, monkeypatch, fake_browser):
    """符号链接默认会被 `copytree` **跟随**并复制目标内容（外部审计情形 2）。

    断言：链接**目标的内容**不出现在临时目录里。允许链接本身被复制为链接
    （`symlinks=True`），但不允许把 `outside/secret.txt` 的内容读出来。
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "secret.txt"
    sentinel.write_text("SENTINEL-OUTSIDE-CONTENT", encoding="utf-8")

    html_dir = tmp_path / "pdf"
    html_dir.mkdir()
    html = html_dir / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")
    link = html_dir / "sneaky.txt"
    try:
        os.symlink(str(sentinel), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("本平台不支持创建符号链接（需管理员/开发者模式）")

    seen = _capture_mirror(monkeypatch)
    ok = pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    # 优先级 1：含链接的目录**直接拒绝渲染**（`unsafe_links` 在 copytree 之前拦）
    assert ok is False, "源目录含符号链接却仍然渲染了"
    # 优先级 2：即便将来放宽成「复制但不读内容」，外部 sentinel 的内容也不能进临时目录。
    # 守卫拒绝时 subprocess 根本没跑，`seen` 里不会有 work —— 所以用 in 判，不要下标。
    if "work" in seen:
        staged_link = os.path.join(seen["work"], "sneaky.txt")
        if os.path.exists(staged_link):
            assert not os.path.isfile(staged_link) or \
                open(staged_link, encoding="utf-8", errors="replace").read() \
                != "SENTINEL-OUTSIDE-CONTENT", "跟随了符号链接，外部内容被复制进来"
        assert "secret.txt" not in seen["names"], "链接目标文件被复制进了临时目录"


def test_large_directory_is_bounded(tmp_path, monkeypatch, fake_browser):
    """受控大目录：镜像数量只与「渲染可能引用的类型」有关，与目录总量无关。

    外部审计情形 1（读放大）：造 120 个资源 + 120 个无关文件，断言临时目录里
    只有资源 + HTML——否则每渲染一次就要把整个目录搬一遍。
    """
    for i in range(120):
        (tmp_path / ("photo_%03d.jpg" % i)).write_bytes(b"\xff\xd8\xff\xd9")
        (tmp_path / ("note_%03d.md" % i)).write_text("无关 %d" % i, encoding="utf-8")
    html = tmp_path / "resume.html"
    html.write_text("<html>hi</html>", encoding="utf-8")

    seen = _capture_mirror(monkeypatch)
    pdf_print.build_pdf(fake_browser, str(html), str(tmp_path / "out.pdf"))

    mirrored = [n for n in seen["names"] if n.startswith(("photo_", "note_"))]
    assert len(mirrored) == 120, "只该镜像 120 个资源，实际 %d：%s" % (len(mirrored), mirrored)
    assert not any(n.startswith("note_") for n in seen["names"]), \
        "无关文件占了临时目录：%s" % seen["names"][:8]
