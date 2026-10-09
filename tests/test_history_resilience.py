# -*- coding: utf-8 -*-
"""history.csv 双保险（2026-10-08 审计 1.1-6，用户选「双保险」）。

**写侧**：追加写此前完全非原子——崩溃把最后一条记录写了一半时，残缺行没有换行
结尾，下一次追加会和它**粘成一行**（中间坏行，读侧连"这是尾巴"都判断不了）。
现在追加前先补齐结尾换行：残缺记录自成一行。

**读侧**：残缺行此前让 `track check` 把**整份时间线**送去 quarantine。现在按
"追加写只会触碰文件尾部、残缺行会被后续追加续到中间"的现实做**逐行**容错——
结构不完好（缺列 / 多列，csv 默认宽容不会抛异常）或半字符的行逐条丢弃、
如实计数（自检报出条数，不静默），其余记录一行不丢，且**不隔离**整份文件。

先红后绿：修复前读侧没有 `read_history_rows`，写侧会粘行。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web", "backend"))

from jobws_core import tracker  # noqa: E402
from jobws_core.tracker import _history, applications  # noqa: E402
from jobws_core.tracker._schema import HISTORY_FILE  # noqa: E402

HEADER = ",".join(applications.HISTORY_FIELDS)


def _ws(tmp_path):
    ws = tmp_path / "personal"
    tracking = ws / "05_投递追踪"
    tracking.mkdir(parents=True)
    (tracking / "tracker.csv").write_text(
        ",".join(tracker.FIELDS) + "\n", encoding="utf-8-sig")
    return str(ws)


def _history_file(ws):
    return os.path.join(ws, "05_投递追踪", HISTORY_FILE)


def _write_torn(ws, good_rows=2):
    """写一份"追加被中断"的时间线：N 条好记录 + 一条无换行结尾的残缺记录。"""
    lines = [HEADER]
    for i in range(good_rows):
        lines.append("2026-10-09 10:00,A%03d,阶段,原,新" % i)
    text = "\n".join(lines) + "\n"
    text += '2026-10-09 10:01,A007,备注,"未闭合'      # 撕裂：引号未闭合、无结尾换行
    with io.open(_history_file(ws), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return good_rows


def test_read_history_keeps_good_rows_and_drops_torn_tail(tmp_path):
    ws = _ws(tmp_path)
    good = _write_torn(ws)

    rows, dropped = _history.read_history_rows(_history_file(ws))

    assert len(rows) == good, rows
    assert dropped == 1
    assert applications.read_history(ws) == rows


def test_read_history_recovers_from_torn_multibyte_tail(tmp_path):
    """追加撕裂可能把 UTF-8 字符切一半——尾部丢一条，前面不受影响。"""
    ws = _ws(tmp_path)
    _write_torn(ws, good_rows=2)
    with open(_history_file(ws), "rb") as fh:
        head = fh.read()
    head = head[:head.rfind(b"\n") + 1]                 # 去掉撕裂行，保留好记录
    with open(_history_file(ws), "wb") as fh:
        fh.write(head + "2026-10-09 10:01,A007,备注,".encode("utf-8")
                 + "中".encode("utf-8")[:2])            # 半字符结尾

    rows, dropped = _history.read_history_rows(_history_file(ws))

    assert dropped == 1 and len(rows) == 2, (dropped, rows)


def test_read_history_raises_when_file_is_garbage(tmp_path):
    """整份都解析不出时保持抛错语义（真损坏由 check 隔离）——容错不掩盖损坏。"""
    ws = _ws(tmp_path)
    with open(_history_file(ws), "wb") as fh:
        fh.write(b"\xff\xfe\x00\x01")                   # 头部即非法 UTF-8、无换行

    try:
        _history.read_history_rows(_history_file(ws))
    except ValueError:
        pass
    else:
        raise AssertionError("整份垃圾文件必须抛错，不能被容错吞成空列表")


def test_append_repairs_missing_newline_before_writing(tmp_path):
    """写侧：残缺尾行先被补断行——新记录绝不与它粘成中间坏行。"""
    ws = _ws(tmp_path)
    _write_torn(ws, good_rows=1)

    applications.append_history(
        [{"id": "A008", "字段": "阶段", "原值": "a", "新值": "b"}], ws)

    raw = io.open(_history_file(ws), encoding="utf-8", newline="").read()
    torn = [line for line in raw.split("\n") if line.startswith("2026-10-09 10:01")]
    assert len(torn) == 1, raw
    assert "A008" not in torn[0], "残缺行被新记录粘住了：%r" % torn[0]

    rows, dropped = _history.read_history_rows(_history_file(ws))
    assert dropped == 1
    assert [r["id"] for r in rows] == ["A000", "A008"]


def test_track_check_reports_tail_drop_and_keeps_file(tmp_path):
    """自检：残缺尾行 → 报「已忽略 N 条」而不是把整份时间线隔离。"""
    ws = _ws(tmp_path)
    _write_torn(ws)

    result = tracker.run_check(ws)

    assert result["quarantined"] == [], result["quarantined"]
    history = [f for f in result["files"] if f["file"] == HISTORY_FILE][0]
    assert history["ok"] is False, "残缺尾行必须如实报出来（不静默）"
    assert any("残缺" in issue for issue in history["issues"]), history["issues"]
    assert os.path.isfile(_history_file(ws)), "整份文件不许被隔离"
