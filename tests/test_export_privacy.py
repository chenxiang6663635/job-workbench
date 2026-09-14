# -*- coding: utf-8 -*-
"""导出与备份的隐私边界：访问凭证不得进 zip。

背景（2026-09-12 审计发现）：导出包会被用户分享（求助 / 迁移），快照目录可能
落在云盘同步范围内；而 `config/imap.json`（明文邮箱授权码）与
`config/provider.json`（明文 API key）一旦被打包，就等于把邮箱读取权限
与计费凭证一起交出去。

`_iter_files` 是导出与备份**共用**的唯一文件清单，所以它在两层被钉住：
纯函数层的清单断言 + 端到端解包后的字节级搜索（防止"文件不在名单但内容
混进了别处"这类间接泄漏）。
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

WS = "ws-ok"

# 凭证字面量：用于在导出 zip 字节里搜（出现即失败）
IMAP_SECRET = "imap-auth-code-9f3a"
PROVIDER_SECRET = "sk-provider-secret-7c1b"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _make_workspace(tmp_path):
    ws = tmp_path / WS
    (ws / "config").mkdir(parents=True, exist_ok=True)
    (ws / "config" / "imap.json").write_text(
        '{"user": "me@example.com", "password": "%s"}' % IMAP_SECRET, encoding="utf-8")
    (ws / "config" / "provider.json").write_text(
        '{"base_url": "https://api.example.com/v1", "api_key": "%s"}' % PROVIDER_SECRET,
        encoding="utf-8")
    (ws / "config" / "profile.md").write_text("领域插件配置（非凭证）", encoding="utf-8")
    (ws / "config" / "imap.lock").write_text("", encoding="utf-8")
    (ws / "01_岗位池").mkdir(exist_ok=True)
    (ws / "01_岗位池" / "note.md").write_text("普通数据", encoding="utf-8")
    # 诱饵（issue #50 T1）：让"按 .txt 后缀取第一个"的写法拿错文件——
    # 下面那条测试靠它才真的能拦住回归，否则改成精确匹配只是"看着更严谨"。
    (ws / "01_岗位池" / "notes.txt").write_text("这是普通文本数据，不是导出说明",
                                                encoding="utf-8")


def _rel_names(ws):
    from routers.system import _iter_files

    return [
        os.path.relpath(path, str(ws)).replace(os.sep, "/")
        for path in _iter_files(str(ws))
    ]


def test_iter_files_excludes_credentials_and_runtime(tmp_path):
    _make_workspace(tmp_path)
    names = _rel_names(tmp_path / WS)

    assert "config/imap.json" not in names, "邮箱授权码不得进导出/备份清单"
    assert "config/provider.json" not in names, "API key 不得进导出/备份清单"
    assert "config/imap.lock" not in names, "锁文件是运行时产物"
    assert "config/profile.md" in names, "非凭证的普通配置照常导出"
    assert "01_岗位池/note.md" in names


def test_export_zip_carries_no_credentials(tmp_path, client):
    """端到端：解包后的文件清单与字节内容都不含凭证。"""
    _make_workspace(tmp_path)

    res = client.get("/api/system/export", params={"ws": WS})
    assert res.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert not [n for n in names if n.endswith("config/imap.json")]
    assert not [n for n in names if n.endswith("config/provider.json")]
    assert [n for n in names if n.endswith("config/profile.md")], "普通配置必须在导出里"

    blob = b"".join(zf.read(n) for n in names)
    assert IMAP_SECRET.encode() not in blob, "授权码字面量不得出现在导出包任何文件里"
    assert PROVIDER_SECRET.encode() not in blob, "API key 字面量不得出现在导出包任何文件里"


def test_export_readme_states_the_credential_boundary(tmp_path, client):
    """导出包自带的说明必须写清"不含凭证"——边界写出来才可被信任。"""
    _make_workspace(tmp_path)
    res = client.get("/api/system/export", params={"ws": WS})
    zf = zipfile.ZipFile(io.BytesIO(res.content))

    # 精确匹配文件名（issue #50 T1）：此前是 `endswith(".txt")` + `[0]`，
    # 工作区里只要存在别的 .txt，取到的就不是说明文件——而这条测试正是
    # "边界可被信任"的依据，取错文件等于在测另一份东西。
    assert any(n.endswith("notes.txt") for n in zf.namelist()), \
        "诱饵文件应随包一起导出，否则本测试的回归保障是空的"
    names = [n for n in zf.namelist() if n == "README_导出说明.txt"]
    assert len(names) == 1, "导出包根目录应恰有一份 README_导出说明.txt：%s" % zf.namelist()
    text = zf.read(names[0]).decode("utf-8")
    assert "凭证" in text, "说明里必须写明哪些敏感内容不在包里"
