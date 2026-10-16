# -*- coding: utf-8 -*-
"""tracker 批量导入的读侧闭环：外部 CSV 必须过还原（#298）。

写侧（`csv_cell`）自 2026-09-23 起给「以 `=` `+` `-` `@` Tab CR 开头」的单元格前置
一个单引号，让 Excel / WPS 按文本显示而不是当公式执行。题库侧的读侧闭环在 PR #297
补齐（`question_bank._read_import_csv` 的 `restore_row`），**同一批漏了 tracker**：
`parse_import_csv` 用裸 `csv.reader`，只 strip 不还原。

后果不是"少一个字符"：导入后界面立刻多一个撇号（用户没写过的字符），用户再存一次盘
就过一遍 `csv_cell` 变成 `''=X`——每往返一轮多一层。判重键是「公司+岗位」，不含
备注/下次动作这类自由文本列，所以既有的往返幂等用例照旧全绿，漂移被藏住。

三个入口（Web `routers/applications.py` / MCP `tools_writable.py` /
CLI `jobws track import`）都调这一个函数，缺口是同一处；本文件既钉核心口径，
也各给三入口一条真路径（Web 在 `test_approvals_api.py`、MCP 在
`mcp/tests/test_tools_writable.py`，各随自己那棵树的 pytest 跑）。

口径与 `question_bank._read_import_csv` 对齐：**先还原、后 strip**。
"""

import csv
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import jobws  # noqa: E402
from jobws_core import tracker  # noqa: E402

TRACKING = "05_投递追踪"
HEAD = ["公司", "岗位", "方向", "批次", "当前阶段"]
FIRST_ROW = ["示例公司甲", "示例岗位乙", "backend", "正式批", "待投"]
DANGER = "=SUM(A1:A9)"


@pytest.fixture(autouse=True)
def _isolate_tracker_workspace(monkeypatch):
    """CLI 用例会就地改 `tracker.WORKSPACE`。

    包化后真身在 `jobws_core.tracker._core`（门面只做 PEP 562 转发，setattr 门面
    改不到真身），与 `tests/test_cli_surface.py` 同款做法。这里走**新包名**取模块
    对象而不是写 `from tracker import _core`：旧名 import 点是「只许下降」的存量，
    新增一处就会被 `jobws lint legacy-imports` 拦下（那条闸门是对的）。
    """
    from jobws_core.tracker import _core as tracker_core
    monkeypatch.setattr(tracker_core, "WORKSPACE", tracker_core.WORKSPACE)


def _make_ws(root):
    """最小工作区：只建投递追踪目录，够 tracker 落盘用。"""
    ws = root / "ws"
    (ws / TRACKING).mkdir(parents=True)
    return ws


def _import_text(**cells):
    """把 {字段: 单元格原文} 拼成一份可直接喂给导入的 CSV（含必填列）。

    走 `csv.writer` 而不是手拼字符串：Tab / CR 这类单元格必须被正确引起来，
    手拼容易在"引号到底谁加的"上含糊——而本文件测的正是引号。
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEAD + list(cells))
    writer.writerow(FIRST_ROW + [cells[name] for name in cells])
    return buf.getvalue()


def _parse_one(cell, field="备注"):
    """解析一份单行 CSV，返回该字段的导入结果。"""
    rows, _unknown = tracker.parse_import_csv(_import_text(**{field: cell}))
    return rows[0][field]


def _tracker_text(ws):
    """盘上原文（即"用户导出、再拿去导入"的那份字节）。"""
    with io.open(os.path.join(str(ws), TRACKING, "tracker.csv"),
                 "r", encoding="utf-8-sig", newline="") as handle:
        return handle.read()


def _raw_cells(ws):
    """盘上单元格原文——**不过** `restore_row`：要断言的正是落盘的形态。"""
    with io.open(os.path.join(str(ws), TRACKING, "tracker.csv"),
                 "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))[-1]


def _write_text(path, text):
    """按原样写文本（`newline=""`：不让 Windows 把 `\\r\\n` 再翻一遍）。"""
    with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _invoke_jobws(monkeypatch, capsys, argv):
    """经**统一入口**跑一次命令（与 `tests/test_cli_surface.py` 同款）。"""
    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        result = jobws.main()
        code = 0 if result is None else result
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


# --- 验收 1：合法前导单引号不得被误剥 -----------------------------------------

def test_legit_leading_quote_is_kept():
    """`'Hello` 是用户真想留的值——`_needs_escape("Hello")` 为假，读侧不许动它。

    这条是**护栏**（修前修后都该绿）：还原若图省事写成"见撇号就剥"，用户的
    `'Hello` 会被悄悄改成 `Hello`——同一个缺口换成丢数据。
    """
    assert _parse_one("'Hello") == "'Hello"


def test_double_quote_form_loses_exactly_one_layer():
    """`''=X` 是「本来就是引号 + 公式前缀」：读侧只剥一层（`_needs_escape` 递归支）。

    剥两层会把用户真写的那个撇号也吃掉，一层都不剥则撇号照样累积。
    """
    assert _parse_one("''=X") == "'=X"


# --- 验收 2：危险前缀导入后不带撇号 -------------------------------------------

@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_formula_prefix_is_restored_to_the_original_characters(prefix):
    """写侧中和过的 `=` `+` `-` `@`：读回来必须是原始字符、不带撇号。"""
    value = prefix + "SUM(A1:A9)"
    assert _parse_one("'" + value) == value


@pytest.mark.parametrize("prefix", ["\t", "\r"])
def test_whitespace_prefix_does_not_leave_the_quote_behind(prefix):
    """Tab / CR 同属写侧的中和对象：这里钉的是**撇号不残留**。

    为什么不断言「Tab 原样保留」：还原之后仍走既有 `.strip()`（与题库
    `_read_import_csv` 同一口径），而 strip 吃两端空白——前导 Tab/CR 会被它收尾。
    这是 strip 这条既有宽松口径的已知代价，不是本批引入的漂移（见文件末尾 NOTE）。
    修前这里拿到的是 `"'\\tSUM…"`（撇号还在），才是要修的那个。
    """
    got = _parse_one("'" + prefix + "SUM(A1:A9)")
    assert not got.startswith("'"), got
    assert got == "SUM(A1:A9)"


# --- 验收 3：先还原、后 strip 的次序 ------------------------------------------

def test_restore_runs_before_strip_so_position_zero_is_keyed_on_the_raw_cell():
    """还原以**原文第 0 位**为判据：先 strip 再还原会重新判定谁该被还原。

    `" '=X"`（Excel 手改常留下的行首空格）里的撇号是**数据**，不是中和符：
    restore 在读到的原文上跑，它就不该被剥；反过来先 strip 会得到 `=X`，
    把用户的一个字符吃掉。这条是**次序守卫**（修前修后都绿，只对顺序写反的实现变红）。
    """
    assert _parse_one(" '=X") == "'=X"


def test_restored_hyphen_prefix_survives_strip():
    """`'- 待定` 还原成 `- 待定`：前导连字符与它后面的空格都不许被 strip 吃掉。

    这是最常见的真实数据（"待定/未定"式的自由文本），写侧为 Excel 中和了那个
    `-`；读侧只 strip 的话用户看到的是「'- 待定」——多一个自己没写过的字符。
    """
    assert _parse_one("'- 待定") == "- 待定"


# --- 验收 4：多轮往返，撇号不累积 ---------------------------------------------

def test_two_import_generations_do_not_accumulate_quotes(tmp_path):
    """导出 → 导入 → 再导出 → 再导入：盘上始终只有**一个**中和撇号。

    判重键是「公司+岗位」，不含备注/下次动作，所以这类列上的漂移不会被既有的往返
    幂等用例发现——必须直接断言**盘上原文**（不过 `restore_row`）。
    """
    pending = "- 回信给 HR"

    first = _make_ws(tmp_path / "gen1")
    tracker.write_rows([{"公司": "示例公司甲", "岗位": "示例岗位乙", "方向": "backend",
                         "批次": "正式批", "当前阶段": "待投",
                         "备注": DANGER, "下次动作": pending}], str(first))
    assert _raw_cells(first)["备注"] == "'" + DANGER      # 写侧：恰一个中和撇号
    assert _raw_cells(first)["下次动作"] == "'" + pending

    generation = _tracker_text(first)
    for name in ("gen2", "gen3"):
        target = _make_ws(tmp_path / name)
        # 用户视角：把上一代那份 CSV 原样喂回来（Excel 里看过、存过，字节不变）
        rows, _unknown = tracker.parse_import_csv(generation)
        assert rows[0]["备注"] == DANGER
        assert rows[0]["下次动作"] == pending
        preview = tracker.preview_import(rows, workspace=str(target))
        assert preview["error"] == []
        with tracker.tracking_lock(str(target)):
            assert tracker.commit_import(preview, workspace=str(target)) == 1
        # 再导出：仍是 `'=SUM…`，不是 `''=SUM…`（后者就是"每轮多一层"的现场）
        assert _raw_cells(target)["备注"] == "'" + DANGER
        assert _raw_cells(target)["下次动作"] == "'" + pending
        generation = _tracker_text(target)


# --- 验收 5·CLI：`jobws track import` 走的就是 parse_import_csv ---------------

def test_cli_import_restores_before_writing_to_disk(tmp_path, monkeypatch, capsys):
    """CLI 真路径：喂一份带中和撇号的 CSV，盘上仍只落一个撇号。"""
    ws = _make_ws(tmp_path)
    src = tmp_path / "exported.csv"
    _write_text(src, _import_text(**{"备注": "'" + DANGER}))

    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", str(ws),
                               "import", "--file", str(src)])

    assert code == 0, out
    assert _raw_cells(ws)["备注"] == "'" + DANGER


# NOTE：`\t` / `\r` 打头的值经「导出 → 导入」会丢掉那个前导空白——还原之后仍走既有
# `.strip()`（本批刻意不改这条宽松口径，题库侧一模一样）。要改就是另一个话题
# （"导入是否该保留两端空白"），与 #298 的撇号累积不是同一件事。
