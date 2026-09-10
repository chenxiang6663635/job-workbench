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

import csv
import json
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

# 身份类字段的白名单。手机号/邮箱的正则只能证明「没有留联系方式」，证明不了
# 「公司与人都不是真的」——有人把真实公司名填进 demo 时，只查号码的断言会照过，
# 而那才是这个骨架最容易被弄脏的地方。用白名单后，新值必须被显式加进来。
PLACEHOLDER_ORGS = {
    "示例科技", "云帆智算", "星河物流", "蓝湖数科",
    "极光支付", "青梧文档", "白泽安全", "沧澜云",
}
PLACEHOLDER_PEOPLE = {"示例同学", "李工", "王老师", "张工", "陈工"}
PLACEHOLDER_SCHOOLS = {"示例大学"}

# 逐列指定白名单：列名写错时下面「一条都没检查到」的断言会立刻失败
IDENTITY_COLUMNS = {
    "公司": PLACEHOLDER_ORGS,
    "姓名": PLACEHOLDER_PEOPLE,
    "面试官": PLACEHOLDER_PEOPLE,
}

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
    """在临时目录里跑一次 init_workspace.main()。

    只重定向 ROOT（它决定 `--target` 落在哪）。TEMPLATE / DEMO / PROFILES 是模块导入时
    按**真实仓库路径**算好的常量，这里**故意不动**——测试要验证的正是「仓库里的真模板
    能装出一个生效的工作区」，把它们也重定向到 tmp 就什么都没测了。
    """
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
    """红线：demo 数据里除占位值外不允许出现任何手机号或邮箱。

    扫**两个**根：`template/demo/`（真正需要被锁住的源）与生成出来的工作区。只扫后者的话，
    某个骨架文件若因复制失败没进工作区，它的内容就完全不被检查。
    """
    roots = [os.path.join(ROOT, "template", "demo"), demo_ws]
    for root in roots:
        for path in _walk_files(root):
            text = _read(path)
            other_phones = set(PHONE_RE.findall(text)) - {PLACEHOLDER_PHONE}
            other_emails = set(EMAIL_RE.findall(text)) - {PLACEHOLDER_EMAIL}
            rel = os.path.relpath(path, root)
            assert other_phones == set(), "%s/%s 含非占位手机号：%s" % (root, rel, other_phones)
            assert other_emails == set(), "%s/%s 含非占位邮箱：%s" % (root, rel, other_emails)


def test_skeleton_is_committed_in_repo():
    """骨架必须**在仓库里**，而不是只存在于某台机器上。

    文档承诺「一条命令得到满数据工作区」，靠的是 `template/demo/` 被提交。这是那条承诺
    唯一可复跑的守卫——比「作者本机对比过一次哈希」有意义得多。
    """
    root = os.path.join(ROOT, "template", "demo")
    missing = [rel for rel in EXPECTED_DATA_FILES
               if not os.path.isfile(os.path.join(root, rel))]
    assert missing == [], "demo 骨架缺文件：%s" % missing


def test_demo_missing_skeleton_fails_readably(tmp_path, monkeypatch, capsys):
    """骨架被删/改名时要给出可读错误并返回 1，而不是抛栈。"""
    monkeypatch.setattr(init_workspace, "DEMO", os.path.join(str(tmp_path), "已删除骨架"))
    assert _run_init(monkeypatch, tmp_path, ["--target", "ws", "--demo"]) == 1
    assert "找不到 demo 数据骨架" in capsys.readouterr().out


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


def test_demo_identity_fields_are_allowlisted(demo_ws):
    """demo 里的公司/人名必须都在占位白名单里（手机号正则挡不住真实公司名）。"""
    tracking = os.path.join(demo_ws, "05_投递追踪")
    checked = 0
    for name in ("tracker.csv", "interviews.csv", "contacts.csv", "offers.csv"):
        with open(os.path.join(tracking, name), "r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                for column, allowed in IDENTITY_COLUMNS.items():
                    value = (row.get(column) or "").strip()
                    if not value:
                        continue
                    checked += 1
                    assert value in allowed, (
                        "%s 的「%s」列出现白名单外的值：%r —— 要么占位数据里混进了真实信息，"
                        "要么需要把它显式加进白名单" % (name, column, value))
    assert checked >= 10, "只检查到 %d 处身份字段，列名或遍历范围可能不对" % checked


def test_demo_resume_identity_is_placeholder(demo_ws):
    source = os.path.join(demo_ws, "02_简历工坊", "source")
    paths = [os.path.join(source, f) for f in os.listdir(source) if f.endswith(".json")]
    assert paths, "demo 没带简历 JSON"
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["basics"]["name"] in PLACEHOLDER_PEOPLE, "%s 的姓名不是占位值" % path
        for edu in data.get("education", []):
            assert edu.get("school") in PLACEHOLDER_SCHOOLS, "%s 的学校不是占位值" % path
