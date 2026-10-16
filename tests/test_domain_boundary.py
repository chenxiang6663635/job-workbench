# -*- coding: utf-8 -*-
"""领域层读取与追加边界收口（#307）：tracker 读 / jd_score 预检 / append_history 写。

三族此前各自裸露（判据只在岗位文件一族收过口）：
- **tracker 读**：`csv_path()` 纯 `path.join` 无 realpath，`os.path.isfile` 正判定
  **跟随链接**——`05_投递追踪` 是区外 junction / `tracker.csv`、`history.csv`
  是区外文件链接时，读侧直接读穿；
- **jd_score 读**：`gap_analysis` 的 JD / 简历 / 词典 / 母版 / 事实库全部经
  `_read_text` 直读，无归属无界；
- **追加写**：`append_history` 的 `"a"` 模式**跟随链接写穿**。

四拓扑：
- T1 `05_投递追踪/` 是区外 junction；
- T2 `tracker.csv` 文件级链接到区外；
- T3 `history.csv` 文件级链接到区外；
- T4 `tracker.csv` / `history.csv` 链接到**工作区内**另一份文件（反向约束：
  合法链接不被误伤）。

判据（用户裁决）：越界一律**显式拒绝**——读侧与写侧都抛领域层
`WorkspaceBoundaryError`（协议层转译，见 `test_domain_boundary_ends.py`
与 `mcp/tests/test_tracker_boundary.py`），不返空列表（那会让调用方误判
「没投过」，正是本项目一路在治的「看起来丢数据」）。

写侧证据形态照抄 `tests/test_prep_toggle.py` 的「预览是承诺：一个字节都不动」：
外部文件的 size + mtime_ns 前后逐字节相等。
"""

import io
import os

import pytest

from jobws_core import jd_score
from jobws_core import workspace_read
from jobws_core.tracker import applications
from jobws_core.tracker._schema import HISTORY_FILE

TRACKING = "05_投递追踪"


def _write(path, text, encoding="utf-8"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding=encoding, newline="") as handle:
        handle.write(text)


def _tracker_csv(ws):
    return os.path.join(ws, TRACKING, "tracker.csv")


def _history_csv(ws):
    return os.path.join(ws, TRACKING, HISTORY_FILE)


def _ws_with_tracking(tmp_path, tracker_rows=1, history_rows=1):
    """一个常规工作区：真 tracker.csv / history.csv 都在区内。"""
    ws = str(tmp_path / "personal")
    _write(_tracker_csv(ws),
           ",".join(applications.FIELDS) + "\n"
           + "".join("A%03d,云帆,后端,,,,,,,待投,,,,,,\n" % i
                     for i in range(1, tracker_rows + 1)),
           encoding="utf-8-sig")
    _write(_history_csv(ws),
           ",".join(applications.HISTORY_FIELDS) + "\n"
           + "".join("2026-10-16 10:00,A%03d,当前阶段,,待投\n" % i
                     for i in range(1, history_rows + 1)))
    return ws


def _write_history_file(path, good_rows=1):
    """一份独立的时间线文件（追加写穿后的落点）。"""
    _write(path, ",".join(applications.HISTORY_FIELDS) + "\n"
           + "".join("2026-10-16 09:00,A%03d,备注,,\n" % i
                     for i in range(1, good_rows + 1)))
    return path


def _snapshot(path):
    """(size, mtime_ns)——「一个字节都没动」的判据口径。"""
    st = os.stat(path)
    return (st.st_size, st.st_mtime_ns)


def _make_dir_link_or_skip(link, target):
    """建目录链接（symlink；Windows 无特权时回退 junction），都不行才跳过并明说。"""
    target, link = str(target), str(link)
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        result = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                capture_output=True)
        if result.returncode == 0:
            return
    pytest.skip("本机不能创建目录符号链接 / junction：%s -> %s" % (link, target))


def _replace_dir_with_link_or_skip(link, target):
    """T1 拓扑：`05_投递追踪` 已存在（调试区里有真数据），先整体移走再换链接。

    mklink /J 对**已存在的名字**返回「Cannot create a file when that file already
    exists」——先删后建才是「目录被掉包成链接」的现场。
    """
    import shutil
    if os.path.isdir(str(link)) and not os.path.islink(str(link)):
        shutil.rmtree(str(link))
    _make_dir_link_or_skip(link, target)


def _make_file_link_or_skip(link, target):
    """建文件链接；Windows 上文件链接要特权，拿不到就跳过（CI 的 ubuntu 跑真实行为）。"""
    target, link = str(target), str(link)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建文件符号链接：%s" % exc)


# --- ① tracker 读：T1 / T2 显式拒绝，T4 照常 ------------------------------------

def test_read_rows_rejects_tracking_dir_escape(tmp_path):
    """T1：`05_投递追踪` 是指向工作区外的 junction——isfile 正判定会把它当本地表。"""
    ws = _ws_with_tracking(tmp_path)
    outside = tmp_path / "外部追踪"
    outside.mkdir()
    _write(str(outside / "tracker.csv"),
           ",".join(applications.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    _replace_dir_with_link_or_skip(os.path.join(ws, TRACKING), outside)

    with pytest.raises(workspace_read.WorkspaceBoundaryError) as excinfo:
        applications.read_rows(ws)

    assert "越出工作区" in str(excinfo.value)
    assert "外部来客" not in str(excinfo.value), "错误消息不夹带外部数据"


def test_read_rows_rejects_tracker_file_escape(tmp_path):
    """T2：tracker.csv 文件级链接到区外——读侧拒绝，不返空列表、不读穿。"""
    ws = _ws_with_tracking(tmp_path)
    outside = _write_history_file(str(tmp_path / "外部主表.csv"))
    with io.open(str(tmp_path / "外部主表.csv"), "w", encoding="utf-8") as handle:
        handle.write(",".join(applications.FIELDS) + "\nA099,外部来客,秘密岗位,,,,,,,待投,,,,,,\n")
    _make_file_link_or_skip(_tracker_csv(ws), outside)

    with pytest.raises(workspace_read.WorkspaceBoundaryError):
        applications.read_rows(ws)


def test_read_rows_allows_internal_file_link(tmp_path):
    """T4（反向约束）：tracker.csv 链接到**工作区内**另一份文件——照常读到。"""
    ws = _ws_with_tracking(tmp_path)
    real_csv = os.path.join(ws, TRACKING, "主表真身.csv")
    _write(real_csv, ",".join(applications.FIELDS) + "\nA042,星海,算法,,,,,,,一面,,,,,,\n",
           encoding="utf-8-sig")
    _make_file_link_or_skip(_tracker_csv(ws), real_csv)

    rows = applications.read_rows(ws)

    assert [r["id"] for r in rows] == ["A042"], "区内链接的目标照常读回"
    assert rows[0]["公司"] == "星海"


# --- ② 时间线读：T3 显式拒绝，T4 照常 --------------------------------------------

def test_read_history_rejects_history_file_escape(tmp_path):
    """T3：history.csv 文件级链接到区外——读侧拒绝（不是 `([], 0)` 空结局）。"""
    ws = _ws_with_tracking(tmp_path)
    outside = _write_history_file(str(tmp_path / "外部时间线.csv"))
    _make_file_link_or_skip(_history_csv(ws), outside)

    with pytest.raises(workspace_read.WorkspaceBoundaryError):
        applications.read_history(ws)


def test_read_history_allows_internal_file_link(tmp_path):
    """T4（反向约束）：区内链接的时间线照常读取。"""
    ws = _ws_with_tracking(tmp_path)
    real_history = os.path.join(ws, TRACKING, "时间线真身.csv")
    _write_history_file(real_history, good_rows=2)
    _make_file_link_or_skip(_history_csv(ws), real_history)

    rows = applications.read_history(ws)

    assert len(rows) == 2, "区内链接的目标照常读回"


# --- ③ 追加写：T3 显式拒绝且外部一字节不多，T4 追加进目标 ------------------------

def test_append_history_refuses_escaped_link_without_touching_a_byte(tmp_path):
    """T3（写侧）：`"a"` 模式**跟随链接写穿**——追加前先过归属判据。

    证据形态 = 外部文件 (size, mtime_ns) 前后不变：一个字节都不能多。
    """
    ws = _ws_with_tracking(tmp_path)
    outside = _write_history_file(str(tmp_path / "外部时间线.csv"))
    before = _snapshot(outside)
    _make_file_link_or_skip(_history_csv(ws), outside)

    with pytest.raises(workspace_read.WorkspaceBoundaryError):
        applications.append_history(
            [{"id": "A001", "字段": "当前阶段", "原值": "待投", "新值": "一面"}], ws)

    assert _snapshot(outside) == before, "外部文件一个字节都不许动（size + mtime_ns）"
    with io.open(outside, "r", encoding="utf-8") as handle:
        assert "一面" not in handle.read(), "新值一个字都不许落进外部文件"


def test_append_history_appends_through_internal_link(tmp_path):
    """T4（反向约束）：区内链接允许追加，且写进**链接目标**（"a" 模式跟随链接）。"""
    ws = _ws_with_tracking(tmp_path)
    real_history = _write_history_file(os.path.join(ws, TRACKING, "时间线真身.csv"))
    before = _snapshot(real_history)
    _make_file_link_or_skip(_history_csv(ws), real_history)

    written = applications.append_history(
        [{"id": "A042", "字段": "当前阶段", "原值": "待投", "新值": "二面"}], ws)

    assert written == 1
    size, mtime_ns = _snapshot(real_history)
    assert size > before[0] and mtime_ns != before[1], "追加落进了链接目标"
    with io.open(real_history, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "A042" in text and "二面" in text
    assert applications.read_history(ws)[-1]["新值"] == "二面"


def test_write_rows_rejects_tracker_file_escape(tmp_path):
    """写侧一族对齐（T2）：`os.replace` 替换的是**链接本身**——重写后它仍是链接，
    内容仍读穿。同样先过归属判据，判据两种后果一起挡。"""
    ws = _ws_with_tracking(tmp_path)
    outside = str(tmp_path / "外部主表.csv")
    _write(outside, ",".join(applications.FIELDS) + "\nA001,云帆,后端,,,,,,,待投,,,,,,\n",
           encoding="utf-8-sig")
    before = _snapshot(outside)
    os.remove(_tracker_csv(ws))
    _make_file_link_or_skip(_tracker_csv(ws), outside)

    rows = [dict((f, "") for f in applications.FIELDS)]
    rows[0].update({"id": "A001", "公司": "星海", "岗位": "算法", "当前阶段": "待投"})
    with pytest.raises(workspace_read.WorkspaceBoundaryError):
        applications.write_rows(rows, ws)

    assert _snapshot(outside) == before, "外部文件一个字节都不许动"


# --- jd_score 差距分析：输入锚点预检 ----------------------------------------------

JD_TEXT = "# 云帆 后端\n\n要求 Python、Kubernetes、ClickHouse、独家秘技 经验。\n"
LEXICON = ("## Primary（3 分/项）\n\nPython、Kubernetes、独家秘技\n"
           "## Weak（1 分/项）\n\nClickHouse\n")


def _gap_ws(tmp_path):
    """可供差距分析的最小工作区（造数照抄 tests/test_gap_analysis.py）。"""
    ws = str(tmp_path / "personal")
    job = os.path.join(ws, "01_岗位池", "云帆_后端")
    _write(os.path.join(job, "解析卡.md"), "# 卡\n")
    _write(os.path.join(job, "JD原文.md"), JD_TEXT)
    _write(os.path.join(ws, "config", "profile.md"), "# 档案\n")
    _write(os.path.join(ws, "config", "lexicon.md"), LEXICON)
    _write(os.path.join(ws, "config", "directions", "datacenter.md"), "# 方向\n")
    _write(os.path.join(ws, "02_简历工坊", "source", "resume_hvac.json"),
           '{"skills": "Python"}')
    _write(os.path.join(ws, "02_简历工坊", "简历_主版_v1.0.md"), "# 主版\n")
    return ws, os.path.join(job, "解析卡.md")


def test_gap_analysis_refuses_escaped_fact_dir(tmp_path):
    """事实库（母版全集）是区外 junction：预检不过 → (None, errors) 说清理由，
    且结论不得包含外部 md 的词条（宁可明确跳过，不拿半拉母版算 injectable）。"""
    ws, card = _gap_ws(tmp_path)
    outside = tmp_path / "外部事实库"
    outside.mkdir()
    _write(str(outside / "secret.md"), "独家秘技 是我独有的。\n")
    _make_dir_link_or_skip(os.path.join(ws, "00_事实库"), outside)

    result, errors = jd_score.gap_analysis(ws, card, "hvac")

    assert result is None
    assert any("越出工作区" in e and "00_事实库" in e for e in errors), errors
    dumped = repr(result) + repr(errors)
    assert "独家秘技" not in dumped, "外部事实库的词条一个字都不许进结论"


def test_gap_analysis_keeps_internal_fact_dir_link(tmp_path):
    """反向约束：事实库是**区内** junction 时 injectable 判定照旧成立。"""
    ws, card = _gap_ws(tmp_path)
    real_facts = os.path.join(ws, "事实库真身")
    _write(os.path.join(real_facts, "note.md"), "Kubernetes 集群运维。\n")
    _make_dir_link_or_skip(os.path.join(ws, "00_事实库"), real_facts)

    result, errors = jd_score.gap_analysis(ws, card, "hvac")

    assert errors == [] and result is not None
    assert [i["term"] for i in result["matched"]] == ["Python"]
    assert result["injectable"] == ["Kubernetes"], "母版（含区内链接的事实库）照常召回"
    assert result["missing"] == ["独家秘技", "ClickHouse"], "顺序随词典遍历（Primary 先）"
