# -*- coding: utf-8 -*-
"""错误消息卫生：**异常原文不回给用户**（CodeQL `py/stack-trace-exposure` #186-190）。

背景：把 `str(exc)` / `% exc` 拼进响应体，会把绝对路径、英文 errno 文本、第三方库
的内部措辞一起送回前端——既可能泄漏本地目录结构，对用户也不比一句可动手的话有用。
原文的去处是日志，不是响应。

这里钉两条链路：① `prep` 搜索的 `skipped.reason`；② `resume_build.verify_pdf` 的
解析失败明细（它经 `/api/resume/templates/{v}/build` 的 `checks` 回给前端）。
"""

import errno
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT_DIR, "tools"), os.path.join(ROOT_DIR, "web", "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import resume_build  # noqa: E402
from apierror import os_error_reason  # noqa: E402
from routers import prep  # noqa: E402


def test_os_error_reason_maps_common_errnos():
    """errno（int）→ 用户能动手的一句话；认不出的给兜底，且**都不含原文**。

    收 int 而不是异常对象是**关键**：拿到异常对象会让返回值带上污点（CodeQL
    认不出自定义映射是 sanitizer）。这条同时钉住形状——传异常会 KeyError。
    """
    assert "磁盘" in os_error_reason(errno.ENOSPC)
    assert "权限" in os_error_reason(errno.EACCES)
    assert "占用" in os_error_reason(errno.EBUSY)
    assert os_error_reason(-99999) == "详见应用日志", "认不出的 errno 走兜底"
    # 传**异常对象**是无效用法（会落到兜底、且把污点接回响应）——故调用点必须传 exc.errno
    assert os_error_reason(OSError(errno.ENOSPC, "x", "/secret")) == "详见应用日志"


def test_credential_warning_has_no_raw_exception(monkeypatch, tmp_path):
    """凭据引用校验失败的告警也不能带异常原文——它经 `plan()` → summary 回响应。

    这是 stack-trace #222/#223 的**第三处**源头（前两处修完告警仍 open，定位到
    `dataroot_semantics.credential_warnings` 把 `%s % exc` 拼进了 warnings）。
    """
    from jobws_core import dataroot_semantics

    class _BoomStore:
        kind = "windows"
        name = "windows"

        def get(self, ref):
            raise RuntimeError("cannot read %s\\%s.cred" % (str(tmp_path), ref))

    monkeypatch.setattr(dataroot_semantics.credentials, "select_store",
                        lambda: _BoomStore())
    monkeypatch.setattr(dataroot_semantics, "credential_refs",
                        lambda ws: [{"file": "config/provider.json",
                                     "ref": "imap:default"}])

    warnings = dataroot_semantics.credential_warnings(str(tmp_path))

    joined = " | ".join(warnings)
    assert joined, "校验失败必须留一条告警（不静默）"
    assert str(tmp_path) not in joined, "异常里的绝对路径回传了：%s" % joined
    assert "cannot read" not in joined, "异常原文回传了：%s" % joined
    assert "重新保存" in joined, joined


def test_prep_search_skipped_reason_has_no_raw_exception(monkeypatch, tmp_path):
    """目录遍历失败时，`skipped.reason` 只能是可动手的说法，不能带路径/errno 原文。"""
    secret = os.path.join(str(tmp_path), "secret-workspace")

    def _boom(*a, **kw):
        raise OSError(errno.EACCES, "Permission denied", secret)

    monkeypatch.setattr(prep, "walk_files", _boom)

    _hits, _total, skipped = prep._search_section(str(tmp_path), "interview", "关键字")

    assert skipped, "遍历失败必须留一条 skipped（不能静默少给）"
    reason = skipped[0]["reason"]
    assert "权限" in reason, reason
    assert secret not in reason, "异常里的绝对路径回传了：%s" % reason
    assert "Permission denied" not in reason, "异常原文回传了：%s" % reason


def test_verify_pdf_failure_message_has_no_raw_exception(monkeypatch, tmp_path):
    """PDF 解析失败的明细会进 `/build` 的响应，不能带异常原文。"""
    secret = os.path.join(str(tmp_path), "secret-resume.pdf")

    class _Boom(Exception):
        pass

    def _fake_reader(path):
        raise _Boom("cannot parse %s (bad xref)" % secret)

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", _fake_reader)
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4 broken")

    passed, details = resume_build.verify_pdf(str(pdf))

    assert passed is False
    joined = " | ".join(details)
    assert secret not in joined, "异常里的绝对路径回传了：%s" % joined
    assert "cannot parse" not in joined, "异常原文回传了：%s" % joined
