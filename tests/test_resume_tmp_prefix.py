# -*- coding: utf-8 -*-
"""渲染临时 HTML 必须守 TMP_PREFIX（`.jobws_tmp_`）——2026-10-08 审计 1.1-5。

问题：`resume_build.discover_source_json` 的暂存名是 `__std_<stem>.html`、
后端预览写的是 `__preview_<version>.html`——都不带 `TMP_PREFIX`，崩溃残留会
混进导出/快照 zip 并被列成可浏览模板（workspace_io / export_notes / manifest
的跳过规则全部按前缀识别）。

两半断言：行为面（discover 产出的暂存名带前缀）+ 源码面（两个写入点不许再出现
旧字面量、都必须引用 TMP_PREFIX——与 tests/test_lock_literals.py 同款的防漂移网）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("tools", "web/backend"):
    _p = os.path.join(ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from jobws_core.workspace_io import TMP_PREFIX  # noqa: E402
import resume_build  # noqa: E402


def test_discover_source_json_returns_prefixed_tmp_name(tmp_path):
    """CLI 路径：暂存 HTML 名以 TMP_PREFIX 开头（且仍是 .html，浏览器要按后缀解析）。"""
    source = tmp_path / "source"
    source.mkdir()
    (source / "resume_hvac.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")

    jobs = resume_build.discover_source_json(str(source))

    assert len(jobs) == 1
    tmp_name = jobs[0][0]
    assert tmp_name.startswith(TMP_PREFIX), tmp_name
    assert tmp_name.endswith(".html"), tmp_name


def test_no_legacy_tmp_literals_in_write_sites():
    """源码面：两个写入点不许再出现 `__std_` / `__preview_` 旧字面量，且引用 TMP_PREFIX。"""
    cli = open(os.path.join(ROOT, "tools", "resume_build.py"), encoding="utf-8").read()
    web = open(os.path.join(ROOT, "web", "backend", "routers", "resume.py"),
               encoding="utf-8").read()

    assert '"__std_' not in cli and "'__std_" not in cli, "CLI 暂存名仍是旧字面量"
    assert '"__preview_' not in web and "'__preview_" not in web, "后端预览名仍是旧字面量"
    assert "TMP_PREFIX" in cli and "TMP_PREFIX" in web, "写入点必须引用 TMP_PREFIX（单一来源）"
