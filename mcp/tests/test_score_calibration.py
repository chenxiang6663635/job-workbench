# -*- coding: utf-8 -*-
r"""筛选校准的 MCP 腿（设计文档 §八.5 四端同源）。

主套件 `tests/test_score_calibration_ends.py` 钉 core ↔ Web API；本文件钉
**MCP 工具 ↔ core**——MCP SDK 只装在 MCP venv，两条腿各自跑在自己的 venv。

除逐字段比对外，还钉三件接线事实：
1. 工具真的注册上了，且注解是只读（不写任何配置 / tracker / 投递动作）；
2. 序列化走 `json.dumps(ensure_ascii=False)`（中文不能变成 \uXXXX）；
3. 空工作区不炸——返回"样本不足"而不是异常（宿主看到的是可读结论）。
"""
import io
import json
import os
import sys
from datetime import date

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

# 导入顺序有讲究（同 test_read_boundary.py 顶部注释）：`jobws_mcp.paths` 在
# **导入期**注入应用根，而 `jobws_core.jd_score` 导入期就求值 ROOT——先导前者，
# 后者才不会 RuntimeError。
from jobws_mcp import paths, tool_registry  # noqa: E402,F401
from jobws_core import jd_score, score_calibration, tracker  # noqa: E402

JOB_DIR = "01_岗位池"
TRACK_DIR = "05_投递追踪"


class _FakeMcp(object):
    """接住 @mcp.tool 注册的最小替身（不引 SDK 的服务装配）。"""

    def __init__(self):
        self.tools = {}
        self.annotations = {}

    def tool(self, annotations=None):
        def deco(fn):
            self.tools[fn.__name__] = fn
            self.annotations[fn.__name__] = annotations
            return fn
        return deco


def _card(dims):
    lines = ["%s: %d/%d" % (name, num, maximum)
             for (name, maximum), num in zip(jd_score.DIMENSIONS, dims)]
    return ("## 基本信息\n公司: 校准科技\n岗位: 后端\n\n"
            "## 评分\n" + "\n".join(lines) + "\n总分: %d\n\n"
            "## 硬门槛\n门槛结论: 通过\n" % sum(dims))


def _seed(ws, n_high, n_mid):
    os.makedirs(os.path.join(ws, JOB_DIR))
    os.makedirs(os.path.join(ws, TRACK_DIR))
    rows = []
    for i in range(n_high):
        name = "高分%d_后端" % i
        os.makedirs(os.path.join(ws, JOB_DIR, name))
        with io.open(os.path.join(ws, JOB_DIR, name, "解析卡.md"), "w", encoding="utf-8") as fh:
            fh.write(_card([24, 20, 24, 12]))            # 80 → 强烈建议投
        rows.append({"id": "H%03d" % i, "公司": "高分%d" % i, "岗位": "后端",
                     "当前阶段": "offer" if i % 2 else "已投", "评分": "80"})
    for i in range(n_mid):
        name = "中分%d_后端" % i
        os.makedirs(os.path.join(ws, JOB_DIR, name))
        with io.open(os.path.join(ws, JOB_DIR, name, "解析卡.md"), "w", encoding="utf-8") as fh:
            fh.write(_card([15, 12, 15, 8]))             # 50 → 斟酌
        rows.append({"id": "M%03d" % i, "公司": "中分%d" % i, "岗位": "后端",
                     "当前阶段": "已挂", "评分": "50"})
    # 时间线：中档那些行进过「已投」再挂——没有它，该档「已投」到达数为 0、
    # rate=None，就退化成"不可比较"（与主套件夹具同一用意）。
    with io.open(os.path.join(ws, TRACK_DIR, "history.csv"), "w", encoding="utf-8-sig") as fh:
        fh.write("时间,id,字段,原值,新值\n")
        for i in range(n_mid):
            fh.write("2026-10-01 10:00,M%03d,当前阶段,已投,已挂\n" % i)
    os.makedirs(os.path.join(ws, JOB_DIR, "没投_后端"))
    with io.open(os.path.join(ws, JOB_DIR, "没投_后端", "解析卡.md"), "w", encoding="utf-8") as fh:
        fh.write(_card([24, 20, 24, 12]))
    tracker.write_rows(rows, ws)


def _register(ws):
    fake = _FakeMcp()
    tool_registry.register_calibration_tools(fake, ws)
    return fake


def test_tool_matches_core_field_by_field(tmp_path):
    ws = str(tmp_path / "personal")
    _seed(ws, 4, 4)
    fake = _register(ws)
    assert "score_calibration" in fake.tools, "工具没注册上"

    rows = tracker.read_rows(ws)
    # today 必须给真值：report.retrospective 用它算停留天数（None 会炸）——
    # 工具内部同样传 date.today()，两侧才逐字段可比
    expected = score_calibration.calibration_data(rows, date.today(), ws)
    got = json.loads(fake.tools["score_calibration"]())

    assert got == expected, "MCP 与 core 漂移"
    tiers = {t["tier"]: t for t in got["tiers"]}
    assert tiers["强烈建议投"]["applied"] == 4
    assert tiers["斟酌"]["applied"] == 4
    assert got["unapplied"]["total"] == 1
    assert "数据显示" in got["conclusion"]["text"]


def test_tool_is_read_only_annotated(tmp_path):
    fake = _register(str(tmp_path))
    anno = fake.annotations["score_calibration"]
    assert anno is not None, "只读工具必须带注解（宿主的确认策略读这个字段）"
    assert anno.read_only_hint is True
    assert anno.open_world_hint is False      # 全本地，不访问网络


def test_tool_keeps_chinese_readable(tmp_path):
    """ensure_ascii=False：中文不能变成 \\uXXXX（宿主直接读给用户看）。"""
    ws = str(tmp_path / "personal")
    _seed(ws, 3, 3)
    fake = _register(ws)
    raw = fake.tools["score_calibration"]()

    assert "强烈建议投" in raw, raw[:200]
    assert "\\u" not in raw.split('"tiers"')[0], "键名区出现转义"


def test_tool_on_empty_workspace_says_samples_too_thin(tmp_path):
    """空工作区不炸：给一句可读的「样本不足」，而不是异常栈。"""
    ws = str(tmp_path / "personal")
    os.makedirs(os.path.join(ws, TRACK_DIR))
    fake = _register(ws)

    data = json.loads(fake.tools["score_calibration"]())

    assert "样本不足" in data["conclusion"]["text"]
    assert all(t["applied"] == 0 for t in data["tiers"])
    assert data["unapplied"]["total"] == 0
