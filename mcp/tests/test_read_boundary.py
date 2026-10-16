# -*- coding: utf-8 -*-
"""只读面的三级归属边界与有界读（2026-10-16，外部审计 P1-A / P2-A）。

审计指认 MCP 与 Web **不同源**：Web 早在 2026-09-23 二轮审计就给岗位读取补了
`_read_in_workspace`（safe_join → inside → 有界读），MCP 侧漏了三处：

1. 岗位池**根**：`list_jobs` 直接 `os.listdir(join(ws, "01_岗位池"))`——该目录若是
   指向工作区外的 junction，一次调用就把**外部目录的条目名**列出来；
2. 岗位**子目录**与 `解析卡.md` / `JD原文.md` **文件级**链接：`_read_text` 与
   `os.path.isfile` 都**跟随链接**，读穿出去、并且用 `有解析卡` / `有JD原文`
   正判定把「工作区外存在某文件」这件事告诉了宿主；
3. 正文通道：`resources.read_job_text` 的归属判定是对的，但 `io.open(..., "r")`
   + `handle.read()` 在**文本模式**下无界——`read(n)` 数的是**字符**不是字节。

六条验收（用户裁决）在本文件里各有对应用例，标注在各 docstring 里：
① 岗位池根链接 ② 岗位子目录链接 ③ `解析卡.md` 文件级链接
④ `list_jobs` 与 `score_jd` 同一道防护 ⑤ **工作区内的链接保持可读**（反向约束，
不是一刀切禁链接） ⑥ 越界时 `有解析卡` / `有JD原文` 为 False（不透露外部状态）。

建链范式照抄既有用例（Windows 无特权时回退 junction，都不行才跳过并明说）：
`mcp/tests/test_tools_batch47.py:159` 的目录链与
`mcp/tests/test_resources_prompts.py:184` 的文件链。
"""

import io
import json
import os
import sys

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

# 导入顺序有讲究：`jobws_mcp.paths` 在**导入期**注入应用根（pathres），而
# `jobws_core.jd_score` 在导入期就求值 `ROOT`——先导前者，后者才不会 RuntimeError
# （其余 mcp 用例能跑，也是因为它们先导 jobws_mcp）。
from jobws_mcp import job_files, paths, resources, tools_readonly  # noqa: E402
from jobws_core import jd_score  # noqa: E402

POOL = "01_岗位池"


# --- 造数 ----------------------------------------------------------------------

def _make_ws(tmp_path):
    ws = tmp_path / "personal"
    os.makedirs(os.path.join(str(ws), "05_投递追踪"))
    return str(ws)


def _write_card(path, company, role, total=78):
    """一张评分自洽（四维之和 = 总分）且带「基本信息」的解析卡。"""
    assert total == 78, "四维固定 24/20/24/10"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write("## 基本信息\n\n公司: %s\n岗位: %s\n\n## 评分\n"
                     "技术匹配: 24/30\n经历匹配: 20/25\n方向契合: 24/30\n"
                     "培养与稳定性: 10/15\n总分: %d\n" % (company, role, total))


def _write_job(job_dir, company="云帆", role="后端开发"):
    _write_card(os.path.join(job_dir, tools_readonly.CARD_FILE), company, role)
    with io.open(os.path.join(job_dir, tools_readonly.JD_FILE), "w",
                 encoding="utf-8") as handle:
        handle.write("# JD\n\n示例正文。\n")


def _make_dir_link_or_skip(link, target):
    """建目录链接（symlink；Windows 无特权时回退 junction），都不行才跳过并明说。"""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True)
        if result.returncode == 0:
            return
    pytest.skip("本机不能创建目录符号链接 / junction：%s -> %s" % (link, target))


def _make_file_link_or_skip(link, target):
    """建文件链接；Windows 上文件链接要特权，拿不到就跳过（CI 的 ubuntu 跑真实行为）。"""
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不能创建符号链接：%s" % exc)


# --- ① 岗位池根目录：链接不得读穿 ------------------------------------------------

def test_list_jobs_rejects_escaped_pool_root(tmp_path):
    """验收①：`01_岗位池` 是指向工作区外的链接时，`os.listdir` 会把外部目录的**条目名**
    一次性列出来——这是「读穿」里最隐晦的一种（内容一个字没读，名字全漏了）。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "外部岗位池"
    _write_job(str(outside / "外部来客_秘密岗位"), company="外部来客", role="秘密岗位")
    _make_dir_link_or_skip(os.path.join(ws, POOL), outside)

    data = tools_readonly.list_jobs(ws)

    assert data["total"] == 0 and data["items"] == []
    assert "外部来客_秘密岗位" not in json.dumps(data, ensure_ascii=False)


def test_score_jd_rejects_escaped_pool_root(tmp_path):
    """验收①（另一侧）：根被掉包成链接时，岗位名解析同样读不到外部目录。"""
    ws = _make_ws(tmp_path)
    outside = tmp_path / "外部岗位池"
    _write_job(str(outside / "外部来客_秘密岗位"), company="外部来客", role="秘密岗位")
    _make_dir_link_or_skip(os.path.join(ws, POOL), outside)

    data = tools_readonly.score_jd(ws, "外部来客_秘密岗位")

    assert data["ok"] is False
    assert "越出工作区" in data["errors"][0]


# --- ② 岗位子目录：链接不得读穿 --------------------------------------------------

def test_list_jobs_does_not_read_through_job_dir_link(tmp_path):
    """验收②：岗位池内的子目录是指向外部的链接——条目可以列（链接本身在工作区内），
    但卡片的公司名、评分一个字都不许从外部读回来。"""
    ws = _make_ws(tmp_path)
    os.makedirs(os.path.join(ws, POOL))
    outside = tmp_path / "外部岗位"
    _write_job(str(outside), company="外部来客", role="秘密岗位")
    _make_dir_link_or_skip(os.path.join(ws, POOL, "逃逸岗"), outside)

    data = tools_readonly.list_jobs(ws)

    assert data["total"] == 1, "链接本身在工作区内：条目仍在，只是读不到外部内容"
    item = data["items"][0]
    assert (item["公司"], item["岗位"]) == ("逃逸岗", ""), "展示名回退目录名切分"
    assert item["评分"] is None
    assert "外部来客" not in json.dumps(data, ensure_ascii=False)


# --- ③ 解析卡 / JD 原文：文件级链接不得读穿 --------------------------------------

def _escaped_job(tmp_path, company="外部来客", role="秘密岗位"):
    """一个**合法**岗位目录，`解析卡.md` 被掉包成指向工作区外的链接。"""
    ws = _make_ws(tmp_path)
    job = os.path.join(ws, POOL, "云帆_后端")
    _write_job(job)
    outside = tmp_path / "outside-card.md"
    _write_card(str(outside), company, role)
    card = os.path.join(job, tools_readonly.CARD_FILE)
    os.remove(card)
    _make_file_link_or_skip(card, outside)
    return ws


def test_list_jobs_does_not_read_through_card_file_link(tmp_path):
    """验收③（list 侧）：岗位目录合法、`解析卡.md` 是文件级链接——读穿发生在**第二层**。"""
    ws = _escaped_job(tmp_path)

    item = tools_readonly.list_jobs(ws)["items"][0]

    assert item["目录"] == "云帆_后端"
    assert (item["公司"], item["岗位"]) == ("云帆", "后端"), "回退目录名切分"
    assert item["评分"] is None


def test_score_jd_does_not_read_through_card_file_link(tmp_path):
    """验收③（score 侧）：同一条拓扑，`score_jd` 也不许把外部卡片读回来。"""
    ws = _escaped_job(tmp_path)

    data = tools_readonly.score_jd(ws, "云帆_后端")

    assert data["ok"] is True, "岗位目录本身合法，不是「岗位不存在」"
    assert (data["公司"], data["岗位"]) == ("云帆", "后端")
    assert data["评分"] is None


def test_list_jobs_and_score_jd_agree_on_escaped_card(tmp_path):
    """验收④：同一条链接拓扑下，两侧对「有没有卡 / 有没有 JD / 评分」的答复必须一致
    ——两套判据迟早给出互相矛盾的结论（文件头第三条纪律）。"""
    ws = _escaped_job(tmp_path)

    item = tools_readonly.list_jobs(ws)["items"][0]
    data = tools_readonly.score_jd(ws, "云帆_后端")

    for field in ("有解析卡", "有JD原文", "评分"):
        assert item[field] == data[field], "%s 两侧不一致" % field


# --- ⑥ 字段 fail-closed：不透露工作区外文件的存在 --------------------------------

def test_escaped_card_and_jd_are_reported_absent(tmp_path):
    """验收⑥：越界按「不存在」给（False），**不是**「存在但读不到」——布尔本身也是
    一次信息泄漏（宿主据此就能探测工作区外有没有某个文件）。"""
    ws = _escaped_job(tmp_path)
    outside_jd = tmp_path / "outside-jd.md"
    with io.open(str(outside_jd), "w", encoding="utf-8") as handle:
        handle.write("# 外部 JD\n")
    jd = os.path.join(ws, POOL, "云帆_后端", tools_readonly.JD_FILE)
    os.remove(jd)
    _make_file_link_or_skip(jd, outside_jd)

    item = tools_readonly.list_jobs(ws)["items"][0]
    data = tools_readonly.score_jd(ws, "云帆_后端")

    assert item["有解析卡"] is False and item["有JD原文"] is False
    assert data["有解析卡"] is False and data["有JD原文"] is False


def test_gap_analysis_is_not_called_with_escaped_paths(tmp_path, monkeypatch):
    """差距分析的输入是**领域层自己再读一遍**（`jd_score._read_text` 不走本侧闸）：
    越界时不能把已判越界的 path 递进去，必须跳过并注明。"""
    ws = _escaped_job(tmp_path)
    calls = []
    real = jd_score.gap_analysis

    def counting(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(jd_score, "gap_analysis", counting)

    data = tools_readonly.score_jd(ws, "云帆_后端", resume_version="hvac")

    assert calls == [], "越界的 path 不该交给领域层"
    assert data["差距"] is None
    assert any("越出工作区" in e for e in data["差距错误"])


# --- ⑤ 反向约束：工作区内的链接仍照旧可读 ----------------------------------------

def test_internal_dir_links_keep_working(tmp_path):
    """验收⑤（目录层）：把工作区内的目录做成链接是合法用法（用户常把工作区放在同步盘、
    或分片存放再链进来）——一刀切禁掉所有链接等于把这类工作区封死。

    两层一起钉：岗位池**根**、岗位**子目录**，目标全在**工作区内**。
    """
    ws = _make_ws(tmp_path)
    # 真身全在**工作区内**的另一棵目录树（在 tmp_path 下不算——那是工作区之外）
    real_pool = tmp_path / "personal" / "岗位池真身"
    _write_job(str(real_pool / "云帆_后端"), company="云帆", role="后端开发")
    _make_dir_link_or_skip(os.path.join(ws, POOL), real_pool)

    # ②岗位子目录也是链接（真身放池内的 `_` 前缀目录：列表按既有规则跳过它）
    real_job = tmp_path / "personal" / POOL / "_岗位真身_星海"
    _write_job(str(real_job), company="星海智能", role="算法工程师")
    _make_dir_link_or_skip(os.path.join(ws, POOL, "星海智能_算法工程师"), real_job)

    items = dict((i["目录"], i) for i in tools_readonly.list_jobs(ws)["items"])
    assert set(items) == {"云帆_后端", "星海智能_算法工程师"}
    assert (items["云帆_后端"]["公司"], items["云帆_后端"]["岗位"]) == ("云帆", "后端开发")
    assert items["云帆_后端"]["评分"]["total"] == 78, "工作区内的链接仍要读出内容"
    assert items["云帆_后端"]["有解析卡"] is True
    assert items["星海智能_算法工程师"]["公司"] == "星海智能"
    assert items["星海智能_算法工程师"]["评分"]["total"] == 78

    data = tools_readonly.score_jd(ws, "云帆_后端")
    assert data["评分"]["total"] == 78 and data["有解析卡"] is True

    text, error = resources.read_job_text(ws, "云帆_后端", "card")
    assert error is None, error
    assert "云帆" in text and "总分: 78" in text


def test_internal_file_link_keeps_working(tmp_path):
    """验收⑤（文件层）：`解析卡.md` 是指向**工作区内**另一份文件的链接时照旧可读
    （归属判的是链接目标，不是「是不是链接」）。

    Windows 上建**文件**链接需要开发者模式：拿不到权限就跳过（CI 的 ubuntu 跑真实
    行为）——与既有用例 `test_resources_prompts.py:177` 同款处理。
    """
    ws = _make_ws(tmp_path)
    job = os.path.join(ws, POOL, "云帆_后端")
    _write_job(job, company="云帆", role="后端开发")
    real_card = tmp_path / "personal" / "内部共享卡片.md"
    _write_card(str(real_card), company="星海智能", role="算法工程师")
    card = os.path.join(job, tools_readonly.CARD_FILE)
    os.remove(card)
    _make_file_link_or_skip(card, real_card)

    item = tools_readonly.list_jobs(ws)["items"][0]
    data = tools_readonly.score_jd(ws, "云帆_后端")

    assert (item["公司"], item["岗位"]) == ("星海智能", "算法工程师"), "展示名取自链接目标"
    assert item["评分"]["total"] == 78 and item["有解析卡"] is True
    assert data["评分"]["total"] == 78 and data["有解析卡"] is True


# --- 读一次：列表为展示名与评分各读一次卡是旧病 -----------------------------------

def test_list_jobs_reads_each_card_once(tmp_path, monkeypatch):
    """卡片改为「读一次喂给两个解析器」（与 Web 的 `_parse_card(text=...)` 同款）：
    同一份文件在一次调用里被读两遍是 2026-10-08 审计点名的读放大。"""
    ws = _make_ws(tmp_path)
    _write_job(os.path.join(ws, POOL, "云帆_后端"), company="云帆", role="后端开发")
    reads = []
    real = paths.read_in_workspace

    def counting(workspace, *parts, **kwargs):
        reads.append("/".join(parts))
        return real(workspace, *parts, **kwargs)

    monkeypatch.setattr(paths, "read_in_workspace", counting)

    item = tools_readonly.list_jobs(ws)["items"][0]

    assert reads == ["%s/云帆_后端/%s" % (POOL, tools_readonly.CARD_FILE)], reads
    assert item["公司"] == "云帆" and item["评分"]["total"] == 78, "少读了文件不能也少给数据"


# --- 原语与有界读（审计 P2-A）----------------------------------------------------

def test_read_in_workspace_fails_closed(tmp_path):
    """原语契约：越界 / 读不到一律 None（fail-closed，不抛错）。"""
    ws = _make_ws(tmp_path)
    os.makedirs(os.path.join(ws, POOL))

    assert paths.read_in_workspace(ws, POOL, "不存在.md") is None
    assert paths.read_in_workspace(ws, "..", "外部.md") is None
    assert paths.read_in_workspace(ws, os.pardir, os.pardir, "外部.md") is None

    assert paths.is_in_workspace(ws, POOL) is True
    assert paths.is_in_workspace(ws, "..") is False
    assert paths.exists_in_workspace(ws, POOL, "不存在.md") is False


def test_read_in_workspace_honours_byte_cap(tmp_path):
    """原语契约：`max_bytes` 数的是**字节**（文本模式的 `read(n)` 数的是字符），
    超限**拒绝**（None）而不是截断——截断后的正文会被解析成半真半假的结果。"""
    ws = _make_ws(tmp_path)
    target = os.path.join(ws, "正文.md")
    with io.open(target, "w", encoding="utf-8") as handle:
        handle.write("中文" * 100)          # 200 字符 / 600 字节

    assert paths.read_in_workspace(ws, "正文.md") == "中文" * 100
    assert paths.read_in_workspace(ws, "正文.md", max_bytes=600) == "中文" * 100
    assert paths.read_in_workspace(ws, "正文.md", max_bytes=200) is None, \
        "200 字节上限下 600 字节的文件必须拒（按字符算的实现会放行）"
    assert paths.read_in_workspace(ws, "正文.md", max_bytes=599) is None


def test_oversized_card_is_refused_not_half_parsed(tmp_path, monkeypatch):
    """超限的解析卡按「读不到」给（评分 None），**不是**给一个切掉尾巴的半截分档；
    `有解析卡` 仍为 True——文件确实在工作区内，两件事不混。"""
    ws = _make_ws(tmp_path)
    _write_job(os.path.join(ws, POOL, "云帆_后端"), company="云帆", role="后端开发")
    monkeypatch.setattr(job_files, "MAX_CARD_BYTES", 64)

    item = tools_readonly.list_jobs(ws)["items"][0]

    assert item["评分"] is None
    assert item["有解析卡"] is True
    assert tools_readonly.score_jd(ws, "云帆_后端")["评分"] is None


def _counting_open(counter, target):
    """包住 `io.open`：只统计**目标文件**上真正被 `read()` 取走的字节。"""
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
        if os.path.normcase(os.path.realpath(str(path))) == os.path.normcase(target):
            return _Handle(handle)
        return handle

    return opener


def test_read_job_text_stops_reading_at_the_byte_cap(tmp_path, monkeypatch):
    """验收（P2-A）：有界读的**证据形态**是「读了多少字节」，不是「输出了多少字符」——
    `handle.read(n)` 在文本模式下按字符计数，纯中文时 20K 字符 ≈ 60K 字节。

    做法：造一份 4.8 MB 的中文 JD（多字节），包住 `io.open` 统计真正从文件里取走的
    字节数。旧实现会一次 `read()` 走完全部 ~4.8 MB（计数器断言必红）。
    """
    ws = _make_ws(tmp_path)
    job = os.path.join(ws, POOL, "云帆_后端")
    _write_job(job)
    jd = os.path.join(job, tools_readonly.JD_FILE)
    with io.open(jd, "w", encoding="utf-8") as handle:
        handle.write("岗位描述正文" * 400000)     # 6 字 × 40 万 ≈ 7.2 MB 字节
    assert os.path.getsize(jd) > 4 * 1024 * 1024

    counter = {"bytes": 0, "calls": []}
    monkeypatch.setattr(io, "open", _counting_open(counter, os.path.realpath(jd)))

    text, error = resources.read_job_text(ws, "云帆_后端", "jd")

    assert error is None, error
    cap = resources.JD_TEXT_MAX_BYTES
    assert counter["calls"] == [cap + 1], "应当只发一次「上限 + 1 字节」的读"
    assert counter["bytes"] <= cap + 1, "读取量有界：读走 %d 字节" % counter["bytes"]
    assert counter["bytes"] >= cap, "不能少读（多读 1 字节是为判断是否还有内容）"
    assert text.endswith("…（已截断，完整内容见工作区 %s/%s/%s）"
                         % (POOL, "云帆_后端", tools_readonly.JD_FILE))
    assert len(text.encode("utf-8")) < cap + 300, "返回体也不许超上限"
