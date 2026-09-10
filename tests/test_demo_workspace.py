# -*- coding: utf-8 -*-
"""init_workspace.py --demo 的锁死测试。

--demo 是「fresh clone 的第一条命令」，它同时压着两条红线：

1. 生成的 demo 数据必须能通过 tracker check。开箱就跑出红色报错的话，
   新用户会以为是自己配错了。
2. 必须全是占位信息。demo 数据是要被截图、被贴进 README、被 fork 的，
   混进任何一条真实联系方式都等于把它发布出去。

另外锁住「覆盖既有数据必须说出口」——--demo 落到一个已填真实数据的工作区上
就是数据丢失，静默覆盖不能接受。
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import init_workspace  # noqa: E402
import tracker  # noqa: E402

# demo 数据里允许出现的联系方式，只有这两个占位值
PLACEHOLDER_PHONE = "13800000000"
PLACEHOLDER_EMAIL = "sample@example.com"

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# demo 覆盖后应当出现的数据文件（相对工作区根）
EXPECTED_DATA_FILES = [
    "05_投递追踪/tracker.csv",
    "05_投递追踪/interviews.csv",
    "05_投递追踪/contacts.csv",
    "05_投递追踪/offers.csv",
    "05_投递追踪/history.csv",
    "02_简历工坊/source/resume_backend.json",
]


def _run_init(monkeypatch, tmp_path, argv):
    """在临时目录里跑一次 init_workspace.main()。"""
    monkeypatch.setattr(init_workspace, "ROOT", str(tmp_path))
    saved = sys.argv
    sys.argv = ["init_workspace.py"] + argv
    try:
        return init_workspace.main()
    finally:
        sys.argv = saved


@pytest.fixture
def demo_ws(tmp_path, monkeypatch):
    assert _run_init(monkeypatch, tmp_path, ["--target", "ws", "--demo"]) == 0
    return os.path.join(str(tmp_path), "ws")


def _walk_files(root):
    for base, _dirs, names in os.walk(root):
        for name in names:
            yield os.path.join(base, name)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_demo_creates_all_data_files(demo_ws):
    for rel in EXPECTED_DATA_FILES:
        assert os.path.isfile(os.path.join(demo_ws, rel)), "缺少 %s" % rel


def test_demo_creates_two_parsed_job_cards(demo_ws):
    """岗位池里要有解析卡 + JD 原文，否则岗位页是空的，demo 就没意义。"""
    pool = os.path.join(demo_ws, "01_岗位池")
    cards = [d for d in os.listdir(pool)
             if os.path.isdir(os.path.join(pool, d))]
    assert len(cards) == 2, "demo 应带 2 个岗位目录，实际 %s" % cards
    for name in cards:
        assert os.path.isfile(os.path.join(pool, name, "解析卡.md"))
        assert os.path.isfile(os.path.join(pool, name, "JD原文.md"))


def test_demo_passes_tracker_check(demo_ws):
    """开箱自检必须全绿——这是 --demo 的核心可用性承诺。"""
    result = tracker.run_check(demo_ws)
    assert result["quarantined"] == [], "demo 数据不该有文件被隔离"
    bad = [(f["file"], f["issues"]) for f in result["files"] if not f["ok"]]
    assert bad == [], "demo 数据自检未通过：%s" % bad
    assert result["ok"] is True


def test_demo_installs_domain_plugin_by_default(demo_ws):
    """不传 --domain 也要装 software-backend，否则「方向」列会报无效值。"""
    directions = os.path.join(demo_ws, "config", "directions")
    assert os.path.isdir(directions), "默认领域插件没装上"
    assert "backend.md" in os.listdir(directions)


def test_demo_contains_only_placeholder_contacts(demo_ws):
    """红线：demo 数据里除占位值外不允许出现任何手机号或邮箱。"""
    for path in _walk_files(demo_ws):
        text = _read(path)
        other_phones = set(PHONE_RE.findall(text)) - {PLACEHOLDER_PHONE}
        other_emails = set(EMAIL_RE.findall(text)) - {PLACEHOLDER_EMAIL}
        rel = os.path.relpath(path, demo_ws)
        assert other_phones == set(), "%s 含非占位手机号：%s" % (rel, other_phones)
        assert other_emails == set(), "%s 含非占位邮箱：%s" % (rel, other_emails)


def test_plain_init_has_no_filled_tracker(tmp_path, monkeypatch):
    """对照组：不加 --demo 时只该有 _示例_ 骨架，绝不能凭空出现 tracker.csv。"""
    assert _run_init(monkeypatch, tmp_path, ["--target", "plain"]) == 0
    plain = os.path.join(str(tmp_path), "plain", "05_投递追踪")
    assert not os.path.isfile(os.path.join(plain, "tracker.csv"))
    assert os.path.isfile(os.path.join(plain, "_示例_tracker.csv"))


def test_plain_init_does_not_install_default_domain(tmp_path, monkeypatch):
    """--demo 的默认插件是 demo 的便利，不该泄漏到普通初始化。"""
    assert _run_init(monkeypatch, tmp_path, ["--target", "plain"]) == 0
    assert not os.path.isdir(os.path.join(str(tmp_path), "plain", "config"))


def test_refuses_non_empty_target_without_force(tmp_path, monkeypatch):
    assert _run_init(monkeypatch, tmp_path, ["--target", "ws"]) == 0
    assert _run_init(monkeypatch, tmp_path, ["--target", "ws"]) == 1


def test_demo_reports_overwritten_data_files(tmp_path, monkeypatch, capsys):
    """--demo 覆盖既有数据时必须点名说出覆盖了哪些文件。"""
    assert _run_init(monkeypatch, tmp_path, ["--target", "ws"]) == 0
    tracker_csv = os.path.join(str(tmp_path), "ws", "05_投递追踪", "tracker.csv")
    with open(tracker_csv, "w", encoding="utf-8") as f:
        f.write("id,公司\nA001,我的真实公司\n")

    capsys.readouterr()  # 丢掉第一次初始化的输出
    assert _run_init(monkeypatch, tmp_path,
                     ["--target", "ws", "--demo", "--force"]) == 0
    out = capsys.readouterr().out
    assert "已被 demo 数据覆盖" in out
    assert "tracker.csv" in out
    # 覆盖确实发生了（demo 数据到位），且提示了恢复途径
    assert "我的真实公司" not in _read(tracker_csv)
    assert "备份" in out
