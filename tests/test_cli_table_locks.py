# -*- coding: utf-8 -*-
"""从表写入口必须持锁（2026-09-23 二轮审计，严重项）。

问题本体：CLI 的从表写入口（mail / contact / offer / talk 的 add·update 与
`track import`）是「锁外 read → 改 dict → 整表重写」。整表重写会把**锁外读到的
快照**覆盖回去——桌面端的后端是常驻进程、用同一把 `tracker.lock`，所以「界面刚
改完，CLI 一写就变回去」这类丢更新没有任何报错，且只发生在从表（主表一直持锁）。

怎么测：不 mock 锁（那会把唯一会出错的路径盖住），而是**真的占住锁**，再跑 CLI 的
写操作，断言它写不进去。默认获取锁要等 10s，测试里把 `_core.file_lock` 换成
超时 0.2s 的同款实现，避免测试真的干等。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from jobws_core import filelock as filelock_mod  # noqa: E402
from jobws_core import tracker  # noqa: E402


def _invoke(monkeypatch, capsys, argv):
    import jobws  # noqa: E402

    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        code = jobws.main()
    except SystemExit as exc:  # argparse 的退出走 SystemExit
        code = exc.code
    except TimeoutError:
        code = 1  # 拿不到锁时冒泡出来的就是它（CLI 尚无友好文案）
    code = 0 if code is None else code
    capsys.readouterr()
    return code


@pytest.fixture()
def ws(tmp_path):
    path = str(tmp_path / "ws")
    os.makedirs(os.path.join(path, "05_投递追踪"))
    return path


@pytest.fixture()
def short_lock(monkeypatch):
    """把领域层的取锁超时压到 0.2s（判定逻辑不变，只是别让测试等十秒）。"""
    monkeypatch.setattr(tracker._core, "file_lock",
                        lambda path, timeout=0.2: filelock_mod.file_lock(path, timeout))


def _cmd(ws, *rest):
    return ["track", "--workspace", ws] + list(rest)


def test_contact_add_waits_for_the_lock(ws, short_lock, monkeypatch, capsys):
    """锁被占住时联系人新增必须写不进去（而不是照旧整表覆盖）。"""
    with filelock_mod.file_lock(tracker._lock_path(ws), timeout=5.0):
        code = _invoke(monkeypatch, capsys,
                       _cmd(ws, "contact", "add", "--name", "张老师"))
    assert code != 0, "锁被占住时不该成功落盘"
    assert tracker.read_contacts(ws) == [], "锁外写入了——丢更新的通道还开着"


def test_offer_add_waits_for_the_lock(ws, short_lock, monkeypatch, capsys):
    with filelock_mod.file_lock(tracker._lock_path(ws), timeout=5.0):
        code = _invoke(monkeypatch, capsys, _cmd(ws, "offer", "add", "--company", "示例公司"))
    assert code != 0
    assert tracker.read_offers(ws) == []


def test_talk_update_waits_for_the_lock(ws, short_lock, monkeypatch, capsys):
    tracker.write_talks([{"宣讲会id": "T001", "公司": "示例公司",
                          "时间": "2026-09-30"}], ws)
    with filelock_mod.file_lock(tracker._lock_path(ws), timeout=5.0):
        code = _invoke(monkeypatch, capsys,
                       _cmd(ws, "talk", "update", "--id", "T001", "--gain", "内推码"))
    assert code != 0
    assert (tracker.read_talks(ws)[0].get("收获") or "") == "", "锁外写入了"


def test_mail_update_waits_for_the_lock(ws, short_lock, monkeypatch, capsys):
    tracker.write_mails([{"邮件id": "M001", "主题": "面试通知",
                          "日期": "2026-09-16 10:00"}], ws)
    with filelock_mod.file_lock(tracker._lock_path(ws), timeout=5.0):
        code = _invoke(monkeypatch, capsys,
                       _cmd(ws, "mail", "update", "--id", "M001", "--subject", "面试邀请"))
    assert code != 0
    assert tracker.read_mails(ws)[0]["主题"] == "面试通知", "锁外写入了"


def test_contact_update_waits_for_the_lock(ws, short_lock, monkeypatch, capsys):
    tracker.write_contacts([{"联系人id": "C001", "姓名": "张老师"}], ws)
    with filelock_mod.file_lock(tracker._lock_path(ws), timeout=5.0):
        code = _invoke(monkeypatch, capsys,
                       _cmd(ws, "contact", "update", "--id", "C001", "--note", "已回信"))
    assert code != 0
    assert (tracker.read_contacts(ws)[0].get("备注") or "") == "", "锁外写入了"


def test_writes_succeed_when_the_lock_is_free(ws, short_lock, monkeypatch, capsys):
    """否定验证：锁空闲时这些命令必须照常成功（不然就是把闸门装成了「一律拒绝」）。"""
    assert _invoke(monkeypatch, capsys,
                   _cmd(ws, "contact", "add", "--name", "李老师")) == 0
    assert tracker.read_contacts(ws)[0]["姓名"] == "李老师"
