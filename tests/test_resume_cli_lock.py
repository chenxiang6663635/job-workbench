# -*- coding: utf-8 -*-
"""CLI 简历构建与桌面端共用 resume.lock（GitHub issue #237）。

问题本体：桌面端构建（web/backend/routers/resume.py 的数据驱动与手写模板两条路径）
持 resume.lock；CLI 构建（tools/_cli_resume.py 的 render 与手写 HTML 两条路径）此前
不持锁，而两者的默认输出目录相同（02_简历工坊/pdf）——并发构建会写同一个 PDF 文件名，
一方可能读到另一方半写的文件，ATS 校验随机失败（issue #237）。

怎么测：不 mock 锁（那会把唯一会出错的路径盖住），而是**真的占住 resume.lock**，再经
统一入口（jobws）跑 CLI 构建：

1. 被占住时：快速失败（不长等）、可读提示、退出码 1 且不落盘；
2. 空闲时：照常构建成功，且构建确实发生在锁内——打桩的构建函数里再抢一次同一把
   锁，必须抢不到（抢到了说明锁没包住构建段）。

两条路径（render / 手写 HTML）各覆盖一遍。浏览器、PDF 生成与校验一律打桩——本文件
只验锁语义，不验 PDF 内容（那是 test_resume_templates.py 的活）。
"""

import io
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from jobws_core import filelock as filelock_mod  # noqa: E402
from jobws_core import workspace_io  # noqa: E402
import _cli_resume  # noqa: E402
import resume_build  # noqa: E402

# 「快速失败」的判定上界（秒）：锁被占住时 CLI 不许接近 file_lock 的默认 10s 超时。
FAST_FAIL_BOUND = 5.0


def _lock_path(ws):
    """resume.lock 的统一路径（唯一真源 = workspace_io 的锁名表，不手拼）。"""
    return workspace_io.lock_path(str(ws), "resume")


@pytest.fixture()
def ws(tmp_path):
    """最小工作区：简历工坊的 pdf / source 目录都在。"""
    path = tmp_path / "ws"
    (path / "02_简历工坊" / "pdf").mkdir(parents=True)
    (path / "02_简历工坊" / "source").mkdir(parents=True)
    return path


@pytest.fixture()
def fake_browser(monkeypatch):
    """浏览器探测打桩：两个入口都经 `_cli_resume.find_browser`，没有真 Chrome 也能跑。"""
    monkeypatch.setattr(_cli_resume, "find_browser", lambda: "fake-chrome")


def _invoke(monkeypatch, capsys, argv):
    import jobws  # noqa: E402

    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        code = jobws.main()
    except SystemExit as exc:  # argparse 的退出走 SystemExit
        code = exc.code
    code = 0 if code is None else code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _forbid_build(monkeypatch, module):
    """把构建函数换成「一被调用就失败」——证明被锁挡住时确实没走到构建段。"""
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("锁被占住时不该执行构建")

    monkeypatch.setattr(module, "build_pdf", forbidden)
    return calls


def _seed_render_source(ws):
    source = ws / "02_简历工坊" / "source"
    data = {"basics": {"name": "示例同学"}, "meta": {"intent": "后端开发"}}
    (source / "resume_backend.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _fake_build_under_lock(lock_path, built):
    """构建打桩：先断言此刻同一把锁抢不到（说明构建在锁内），再假装写出 PDF。"""

    def fake_build(_browser, _html, pdf_path):
        with pytest.raises(TimeoutError):
            with filelock_mod.file_lock(lock_path, timeout=0.2):
                pass
        built.append(pdf_path)
        with io.open(pdf_path, "w", encoding="utf-8") as handle:
            handle.write("x")
        return True

    return fake_build


# ---- ① 锁被占住：快速失败、可读提示、非 0、不落盘 -----------------------------


def test_render_build_fails_fast_when_lock_held(ws, fake_browser, monkeypatch, capsys):
    _seed_render_source(ws)
    calls = _forbid_build(monkeypatch, resume_build)

    started = time.monotonic()
    with filelock_mod.file_lock(_lock_path(ws), timeout=5.0):
        code, out = _invoke(monkeypatch, capsys,
                            ["resume", "render", "--workspace", str(ws),
                             "--version", "backend"])
    elapsed = time.monotonic() - started

    assert code == 1, out
    assert "另一端正在构建" in out and "稍后重试" in out, out
    assert calls == [], "锁被占住却仍执行了构建"
    assert not (ws / "02_简历工坊" / "pdf" / "简历_backend.pdf").exists(), "锁被占住却落了盘"
    assert elapsed < FAST_FAIL_BOUND, "CLI 侧应快速失败，实测 %.1fs" % elapsed


def test_manual_build_fails_fast_when_lock_held(ws, fake_browser, monkeypatch, capsys):
    (ws / "02_简历工坊" / "pdf" / "resume_hvac.html").write_text(
        "<html></html>", encoding="utf-8")
    calls = _forbid_build(monkeypatch, _cli_resume)

    started = time.monotonic()
    with filelock_mod.file_lock(_lock_path(ws), timeout=5.0):
        code, out = _invoke(monkeypatch, capsys, ["resume", "--workspace", str(ws)])
    elapsed = time.monotonic() - started

    assert code == 1, out
    assert "另一端正在构建" in out and "稍后重试" in out, out
    assert calls == [], "锁被占住却仍执行了构建"
    assert not (ws / "02_简历工坊" / "pdf" / "简历_hvac.pdf").exists(), "锁被占住却落了盘"
    assert elapsed < FAST_FAIL_BOUND, "CLI 侧应快速失败，实测 %.1fs" % elapsed


# ---- ② 锁空闲：照常构建，且构建发生在锁内 ------------------------------------


def test_render_build_succeeds_and_runs_under_lock(ws, fake_browser, monkeypatch, capsys):
    _seed_render_source(ws)
    built = []
    monkeypatch.setattr(resume_build, "build_pdf",
                        _fake_build_under_lock(_lock_path(ws), built))
    monkeypatch.setattr(resume_build, "check_a4_mediabox",
                        lambda _path: (True, "A4（测试）"))
    monkeypatch.setattr(resume_build, "verify_pdf",
                        lambda *_args, **_kwargs: (True, [("页数", "1 页", True)]))

    code, out = _invoke(monkeypatch, capsys,
                        ["resume", "render", "--workspace", str(ws),
                         "--version", "backend"])

    assert code == 0, out
    assert built and os.path.isfile(built[0]), "锁空闲时应当正常构建并落盘"


def test_manual_build_succeeds_and_runs_under_lock(ws, fake_browser, monkeypatch, capsys):
    (ws / "02_简历工坊" / "pdf" / "resume_hvac.html").write_text(
        "<html></html>", encoding="utf-8")
    built = []
    monkeypatch.setattr(_cli_resume, "build_pdf",
                        _fake_build_under_lock(_lock_path(ws), built))
    monkeypatch.setattr(_cli_resume, "verify_pdf",
                        lambda *_args, **_kwargs: (True, [("页数", "1 页", True)]))

    code, out = _invoke(monkeypatch, capsys, ["resume", "--workspace", str(ws)])

    assert code == 0, out
    assert built and os.path.isfile(built[0]), "锁空闲时应当正常构建并落盘"
