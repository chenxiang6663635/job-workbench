# -*- coding: utf-8 -*-
"""诊断包导出（首发前收口批 笔 3）。

为什么需要它：这个应用的所有故障现场都在用户机器上——"打不开 / 没反应 / 数据看着不对"
三类反馈里，开发者此前能拿到的只有一句用户口述。诊断包把定位所需的事实（版本、平台、
解释器、数据目录与模式、schema 自检摘要、主进程日志尾部）收成一个 zip。

隐私边界比导出包更严，本文件逐条钉住：

1. **不含凭证**：`config/imap.json` / `config/provider.json` 的字节不得出现在包里
   （与导出包同一份排除清单，但这里连"工作区文件"整体都不进包）；
2. **不含工作区内容**：数据文件里的字面量不得出现在包里（字节级搜索，防"文件不在
   名单但内容混进别处"）；
3. **路径脱敏**：家目录前缀（`C:\\Users\\<某人>`）必须以 `~` 出现在日志里；
4. **体积有上限**：日志尾部截断并注明，不能把 1GB 的 main.log 原样打包。
"""

import io
import os
import sys
import zipfile

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-diag"

# 假的"家目录"：用 USERPROFILE 换掉，脱敏断言才有确定的落脚点
HOME = "C:\\Users\\somebody"
IMAP_SECRET = "imap-auth-code-diag-7f2c"
WORKSPACE_MARKER = "工作区里的真实内容不该进诊断包"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.setenv("JOBWS_WORKSPACE", WS)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("USERPROFILE", HOME)
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _make_workspace(tmp_path):
    ws = tmp_path / WS
    (ws / "config").mkdir(parents=True, exist_ok=True)
    (ws / "config" / "imap.json").write_text(
        '{"user": "me@example.com", "password": "%s"}' % IMAP_SECRET, encoding="utf-8")
    (ws / "01_岗位池").mkdir(exist_ok=True)
    (ws / "01_岗位池" / "note.md").write_text(WORKSPACE_MARKER, encoding="utf-8")


def _write_log(tmp_path, text):
    user_data = tmp_path / "appdata" / "job-workbench"
    user_data.mkdir(parents=True, exist_ok=True)
    (user_data / "main.log").write_text(text, encoding="utf-8")


def _unzip(res):
    return zipfile.ZipFile(io.BytesIO(res.content))


def _blob(zf):
    return b"".join(zf.read(name) for name in zf.namelist())


def test_diagnostics_zip_has_manifest_and_log_tail(tmp_path, client):
    _make_workspace(tmp_path)
    _write_log(tmp_path, "[job-workbench] 2026-09-23T22:07:00.000Z Backend ready\n")

    res = client.get("/api/system/diagnostics")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"

    zf = _unzip(res)
    names = zf.namelist()
    assert "diagnostics.json" in names, names
    assert "main-log.txt" in names, names
    assert any(name.startswith("README") for name in names), names

    manifest = __import__("json").loads(zf.read("diagnostics.json").decode("utf-8"))
    assert manifest["app"]["platform"] == sys.platform
    assert "version" in manifest["app"]
    assert manifest["paths"]["workspace"].endswith(WS)
    assert set(["dataRoot", "mode", "snapshotCount"]) <= set(manifest["paths"])
    assert "ok" in manifest["check"], manifest["check"]
    # 包里有什么、跳过了什么，都要写清楚——诊断包自己得能自解释
    assert manifest["contents"], manifest
    assert "Backend ready" in zf.read("main-log.txt").decode("utf-8")


def test_diagnostics_carries_no_credentials_or_workspace_content(tmp_path, client):
    _make_workspace(tmp_path)
    _write_log(tmp_path, "[job-workbench] boot\n")

    zf = _unzip(client.get("/api/system/diagnostics"))
    blob = _blob(zf)

    assert IMAP_SECRET.encode() not in blob, "授权码不得出现在诊断包里"
    assert WORKSPACE_MARKER.encode() not in blob, "工作区内容不得出现在诊断包里"
    # 注意：**文件名**允许出现——README 里写着"不含 config/imap.json"是刻意的边界声明
    # （含糊承诺不如写清边界）。所以这里断言的是"包里没有这样一个条目"，不是"字节里没有这个词"。
    assert not [name for name in zf.namelist() if name.endswith("imap.json")], zf.namelist()


@pytest.mark.parametrize("spelling", [HOME, HOME.upper(), HOME.replace("\\", "/")])
def test_home_path_is_redacted_in_the_log_tail(tmp_path, client, spelling):
    """大小写与分隔符变体都要脱敏：Windows 路径大小写不敏感，日志里的写法不受我们控制
    （PATH、第三方库、Chromium 都可能给出 `c:\\users\\bob` 或 `C:/Users/Bob`）。"""
    _make_workspace(tmp_path)
    _write_log(tmp_path, "[job-workbench] log at %s\\AppData\\Roaming\\job-workbench\\main.log\n" % spelling)

    text = _unzip(client.get("/api/system/diagnostics")).read("main-log.txt").decode("utf-8")
    assert spelling not in text, "家目录前缀必须脱敏（%s）：%s" % (spelling, text)
    assert "~" in text, text


def test_huge_log_is_truncated_with_a_note(tmp_path, client):
    _make_workspace(tmp_path)
    _write_log(tmp_path, ("x" * 1000 + "\n") * 400)  # 约 400KB

    zf = _unzip(client.get("/api/system/diagnostics"))
    text = zf.read("main-log.txt").decode("utf-8")
    assert len(text) < 200 * 1024, "日志尾部必须有上限（实际 %d 字节）" % len(text)
    assert "truncated" in text.lower(), "截断必须注明，否则像是在看完整日志"


def test_missing_log_file_still_returns_a_package(tmp_path, client):
    """没有 main.log（纯 API 场景 / 刚装上）也要能出包，并如实说明缺了什么。"""
    _make_workspace(tmp_path)

    res = client.get("/api/system/diagnostics")
    assert res.status_code == 200, res.text
    zf = _unzip(res)
    assert "diagnostics.json" in zf.namelist()
    manifest = __import__("json").loads(zf.read("diagnostics.json").decode("utf-8"))
    assert manifest["log"] is None or manifest["log"].get("present") is False, manifest.get("log")
