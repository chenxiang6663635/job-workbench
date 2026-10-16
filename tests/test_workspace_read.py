# -*- coding: utf-8 -*-
"""`jobws_core.workspace_read` 原语单测（#307 领域层读取与追加边界收口）。

原语是三端共用的「工作区内读取」唯一实现（MCP `paths` / Web `routers/jobs` /
领域层 tracker 与 jd_score 都走它），所以这一层钉三件事：

1. **归属判定**（收集式不抛 + `assert_within` 抛）：判「链接目标」（realpath 展开），
   区外 fail-closed、**区内合法链接不误伤**（反向约束，与判据层
   `tests/test_containment.py` 的三级钉子各钉一级）；
2. **字节上限**：`max_bytes` 数的是**字节**（文本模式 `read(n)` 数的是字符），
   超限**拒绝**（None）而不是截断；
3. **读取量**：证据形态是「从文件里真正取走多少字节」——照抄
   `mcp/tests/test_read_boundary.py` 的 `_counting_open` 计数范式，证明的是
   cap+1 一次读，不是输出长度。

建链范式照抄 `tests/test_prep_toggle.py`（目录链 symlink → Windows junction 回退，
文件链直接 skip 并明说）；Windows 无特权 `WinError 1314` 不是回归。
"""

import io
import os

import pytest

from jobws_core import workspace_read


def _make_ws(tmp_path):
    ws = tmp_path / "personal"
    ws.mkdir()
    return str(ws)


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


def _make_file_link_or_skip(link, target):
    """建文件链接；Windows 上文件链接要特权，拿不到就跳过（CI 的 ubuntu 跑真实行为）。"""
    target, link = str(target), str(link)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建文件符号链接：%s" % exc)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


# --- 归属判定（收集式，不抛） ----------------------------------------------------

def test_is_in_workspace_rejects_outside_but_allows_root(tmp_path):
    """越界（`..` 段 / 区外链接）False；等于工作区自身 True（拼接类场景的既有语义）。"""
    ws = _make_ws(tmp_path)

    assert workspace_read.is_in_workspace(ws) is True
    assert workspace_read.is_in_workspace(ws, "config") is True
    assert workspace_read.is_in_workspace(ws, "..", "外部.md") is False
    assert workspace_read.is_in_workspace(ws, os.pardir, os.pardir, "外部.md") is False


def test_is_in_workspace_rejects_escaped_dir_link(tmp_path):
    """T1 形态：`05_投递追踪` 是指向工作区外的 junction——判据展开链接目标。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "outside-tracking"
    outside.mkdir()
    (outside / "history.csv").write_text("外部\n", encoding="utf-8")
    _make_dir_link_or_skip(os.path.join(ws, "05_投递追踪"), outside)

    assert workspace_read.is_in_workspace(ws, "05_投递追踪") is False
    assert workspace_read.is_in_workspace(ws, "05_投递追踪", "tracker.csv") is False


def test_exists_in_workspace_fails_closed_on_escaped_file_link(tmp_path):
    """T2 形态：`tracker.csv` 是文件级链接到区外——**不透露外部文件的存在性**。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("外部\n", encoding="utf-8")
    _make_file_link_or_skip(os.path.join(ws, "tracker.csv"), outside)

    assert os.path.isfile(os.path.join(ws, "tracker.csv")) is True, "isfile 跟随链接（现状）"
    assert workspace_read.exists_in_workspace(ws, "tracker.csv") is False


def test_is_in_workspace_allows_internal_dir_link(tmp_path):
    """反向约束 ②（每条原语一条）：区内 junction / 链接的目标仍在工作区内。"""
    ws = _make_ws(tmp_path)
    real_dir = os.path.join(ws, "05_投递追踪真身")
    os.makedirs(real_dir)
    _make_dir_link_or_skip(os.path.join(ws, "05_投递追踪"), real_dir)

    assert workspace_read.is_in_workspace(ws, "05_投递追踪") is True
    assert workspace_read.is_in_workspace(ws, "05_投递追踪", "tracker.csv") is True


# --- assert_within：写侧 / 读侧显式拒绝（抛，不返 bool） --------------------------

def test_assert_within_raises_readable_error_on_escape(tmp_path):
    """越界抛领域异常：消息面向用户（含路径与工作区），且必须可被协议层转译。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("外部\n", encoding="utf-8")
    _make_file_link_or_skip(os.path.join(ws, "tracker.csv"), outside)

    with pytest.raises(workspace_read.WorkspaceBoundaryError) as excinfo:
        workspace_read.assert_within(ws, os.path.join(ws, "tracker.csv"))
    message = str(excinfo.value)
    assert "越出工作区" in message
    assert "tracker.csv" in message, "消息要点名具体路径（协议层原样透出）"


def test_assert_within_returns_path_for_internal_link(tmp_path):
    """反向约束 ②：区内链接的目标照常放行，返回值是原 path（链式友好）。"""
    ws = _make_ws(tmp_path)
    _write(os.path.join(ws, "真身.csv"), "内容\n")
    _make_file_link_or_skip(os.path.join(ws, "tracker.csv"), os.path.join(ws, "真身.csv"))

    path = os.path.join(ws, "tracker.csv")
    assert workspace_read.assert_within(ws, path) == path


# --- 有界读：字节口径 + 超限拒绝 -------------------------------------------------

def test_read_in_workspace_fails_closed(tmp_path):
    """越界 / 读不到一律 None（fail-closed，不抛错）。"""
    ws = _make_ws(tmp_path)

    assert workspace_read.read_in_workspace(ws, "不存在.md") is None
    assert workspace_read.read_in_workspace(ws, "..", "外部.md") is None
    assert workspace_read.read_in_workspace(ws, os.pardir, os.pardir, "外部.md") is None


def test_read_in_workspace_honours_byte_cap(tmp_path):
    """`max_bytes` 数的是**字节**，超限**拒绝**（None）而不是截断。"""
    ws = _make_ws(tmp_path)
    _write(os.path.join(ws, "正文.md"), "中文" * 100)      # 200 字符 / 600 字节

    assert workspace_read.read_in_workspace(ws, "正文.md") == "中文" * 100
    assert workspace_read.read_in_workspace(ws, "正文.md", max_bytes=600) == "中文" * 100
    assert workspace_read.read_in_workspace(ws, "正文.md", max_bytes=200) is None, \
        "200 字节上限下 600 字节的文件必须拒（按字符算的实现会放行）"
    assert workspace_read.read_in_workspace(ws, "正文.md", max_bytes=599) is None


def test_read_in_workspace_reads_internal_file_link(tmp_path):
    """反向约束 ②：文件级链接的目标在区内时照常读到（归属判的是目标）。"""
    ws = _make_ws(tmp_path)
    _write(os.path.join(ws, "内部共享.md"), "内部正文\n")
    _make_file_link_or_skip(os.path.join(ws, "解析卡.md"), os.path.join(ws, "内部共享.md"))

    assert workspace_read.read_in_workspace(ws, "解析卡.md") == "内部正文\n"


def test_read_in_workspace_refuses_escaped_file_link(tmp_path):
    """T2 形态（读侧）：文件级链接到区外 → None（不读穿）。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "outside.md"
    _write(str(outside), "外部正文\n")
    _make_file_link_or_skip(os.path.join(ws, "解析卡.md"), outside)

    assert workspace_read.read_in_workspace(ws, "解析卡.md") is None


def test_read_in_workspace_measures_bytes_read(tmp_path, monkeypatch):
    """有界读的**读取量证据**：不是「输出了多少字符」，是「从文件里取走多少字节」——
    照抄 `mcp/tests/test_read_boundary.py` 的 `_counting_open` 计数范式。

    旧实现（无 / 字符口径的有界读）会把整份 ~600KB 一次读走；现在只发一次
    「上限 + 1 字节」的读（多读 1 字节是为判断「后面还有内容」）。
    """
    ws = _make_ws(tmp_path)
    _write(os.path.join(ws, "JD原文.md"), "岗位描述正文" * 100000)   # ≈ 600KB 字节
    cap = 64 * 1024
    counter = {"bytes": 0, "calls": []}
    real_open = io.open

    class _Handle(object):
        def __init__(self, handle):
            self._handle = handle

        def read(self, size=-1):
            data = self._handle.read(size)
            counter["calls"].append(size)
            counter["bytes"] += len(data)
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

    def opener(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        target = os.path.join(ws, "JD原文.md")
        if os.path.normcase(os.path.realpath(str(path))) == os.path.normcase(
                os.path.realpath(target)):
            return _Handle(handle)
        return handle

    monkeypatch.setattr(io, "open", opener)

    text = workspace_read.read_in_workspace(ws, "JD原文.md", max_bytes=cap)

    assert text is None, "600KB > 64KB 上限：应当拒绝（None，不截断）"
    assert counter["calls"] == [cap + 1], "应当只发一次「上限 + 1 字节」的读"
    assert counter["bytes"] <= cap + 1, "读取量有界：读走 %d 字节" % counter["bytes"]
    assert counter["bytes"] >= cap, "不能少读（多读 1 字节是为判断是否还有内容）"


# --- 换行归一并进原语（收编自 MCP `resources.read_job_text`） ---------------------

def test_read_in_workspace_normalises_crlf_like_text_mode(tmp_path):
    """CRLF 读出来是 LF——原语内完成归一，协议层不再各自补（同一份 CRLF 两个宿主
    原先会给出不同文本；2026-10-16 独立审查点名的同源口径）。"""
    ws = _make_ws(tmp_path)
    with io.open(os.path.join(ws, "正文.md"), "wb") as handle:
        handle.write("第一行\r\n第二行\r\n\r\n末行".encode("utf-8"))

    text = workspace_read.read_in_workspace(ws, "正文.md")

    assert text == "第一行\n第二行\n\n末行"
    assert "\r" not in text


def test_normalise_newlines_handles_cr_and_crlf():
    """归一两件套（原 CRLF + 旧 Mac CR）——先 CRLF 后 CR，顺序不可颠倒。"""
    assert workspace_read.normalise_newlines("a\r\nb\rc\nd") == "a\nb\nc\nd"
