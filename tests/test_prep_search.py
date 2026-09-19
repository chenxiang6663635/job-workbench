# -*- coding: utf-8 -*-
"""笔记全文搜索（`GET /api/prep/search`）：命中口径、诚实截断与批量遍历的防护。

钉住五件容易悄悄坏掉的事：
1. **路由顺序**：`/search` 必须排在 `/{section}` 之前，否则 "search" 会被当成
   section 名 → 404 `prep.unknownSection`（本文件第一条用例）；
2. **命中口径**：子串 + 大小写不敏感、**不分词**；文件名命中与正文命中都给结果；
   一条命中 = 一行；
3. **诚实截断**：`total` 是真实命中总数，`items` 只给展示上限，超出置
   `truncated`——绝不把"返回条数"当"命中数"；
4. **批量遍历的防护**：逐文件 `inside()`（`walk_files` 自己不查归属，文件级
   符号链接会以普通文件身份出现）；
5. **读不动不静默**：非 UTF-8 / 读不到的文件进 `skipped`，其余文件照常返回。
"""

import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
PREP_DIR = "03_面试准备"
KB_DIR = "04_知识库"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _write(tmp_path, rel, content, base=PREP_DIR):
    path = tmp_path / WS / base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


def _search(client, q):
    return client.get("/api/prep/search", params={"ws": WS, "q": q})


# --- 路由与基本口径 ---------------------------------------------------------


def test_search_route_is_not_eaten_by_section_route(client, tmp_path):
    """`/api/prep/search` 不能落到 `/{section}`（那会把 "search" 当成分类名）。"""
    _write(tmp_path, "缓存雪崩.md", "# 缓存雪崩\n雪崩是怎么发生的\n")
    res = _search(client, "雪崩")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["keyword"] == "雪崩"
    assert body["total"] >= 1


def test_hits_cover_file_name_and_body(client, tmp_path):
    _write(tmp_path, "缓存雪崩.md", "# 缓存\n正文里没有那个词\n")
    _write(tmp_path, "别的.md", "# 无关\n这里出现 雪崩 两个字\n")

    body = _search(client, "雪崩").json()

    rels = [(h["rel"], h["line"], h["inName"]) for h in body["items"]]
    # 文件名命中（正文无）→ 一条 line=1；正文命中 → 一条，行号真实
    assert ("缓存雪崩.md", 1, True) in rels
    assert ("别的.md", 2, False) in rels


def test_match_is_case_insensitive_substring(client, tmp_path):
    _write(tmp_path, "x.md", "# Redis\nredis 持久化与 Redis Cluster\n")

    body = _search(client, "REDIS").json()

    # 同一行只算一条；大小写不敏感（lower 后子串匹配）
    assert body["total"] == 2
    assert [h["line"] for h in body["items"]] == [1, 2]


def test_no_word_splitting(client, tmp_path):
    """不按空格分词：「缓存 雪崩」是一个短语，不是一个词表。"""
    _write(tmp_path, "a.md", "# 缓存雪崩\n缓存与雪崩分开写\n")

    assert _search(client, "缓存 雪崩").json()["total"] == 0
    assert _search(client, "缓存雪崩").json()["total"] == 1


def test_empty_keyword_returns_empty_result(client, tmp_path):
    _write(tmp_path, "a.md", "# 有内容\n")
    for q in ("", "   "):
        res = _search(client, q)
        assert res.status_code == 200
        body = res.json()
        assert body["items"] == [] and body["total"] == 0
        assert body["truncated"] is False


def test_both_sections_are_searched(client, tmp_path):
    _write(tmp_path, "a.md", "关键词甲\n")
    _write(tmp_path, "b.md", "关键词甲\n", base=KB_DIR)

    body = _search(client, "关键词甲").json()

    assert [(h["section"], h["rel"]) for h in body["items"]] == [
        ("interview", "a.md"), ("knowledge", "b.md")]


def test_order_is_section_then_rel_then_line(client, tmp_path):
    _write(tmp_path, "b.md", "关键词\nx\n关键词\n")
    _write(tmp_path, "a/深.md", "关键词\n")
    _write(tmp_path, "z.md", "关键词\n", base=KB_DIR)

    body = _search(client, "关键词").json()

    assert [(h["section"], h["rel"], h["line"]) for h in body["items"]] == [
        ("interview", "a/深.md", 1), ("interview", "b.md", 1),
        ("interview", "b.md", 3), ("knowledge", "z.md", 1)]


# --- 诚实截断 ---------------------------------------------------------------


def test_limit_truncates_items_but_total_stays_true(client, tmp_path):
    _write(tmp_path, "big.md", "\n".join("第 %d 行 关键词" % i for i in range(1, 61)))

    body = _search(client, "关键词").json()

    assert body["total"] == 60
    assert len(body["items"]) == 50
    assert body["truncated"] is True


def test_no_truncation_below_limit(client, tmp_path):
    _write(tmp_path, "x.md", "\n".join("关键词 %d" % i for i in range(3)))
    body = _search(client, "关键词").json()
    assert body["total"] == 3 and body["truncated"] is False


def test_limit_boundary_is_not_truncated_at_exactly_the_cap(client, tmp_path):
    """恰好等于上限时**不算**截断（钉住 `>` 与 `>=` 的分界）。"""
    cap = 50
    _write(tmp_path, "x.md", "\n".join("关键词 %d" % i for i in range(cap)))
    body = _search(client, "关键词").json()
    assert body["total"] == cap
    assert len(body["items"]) == cap
    assert body["truncated"] is False


def test_directory_name_counts_as_hit(client, tmp_path):
    """与左树过滤同口径：目录名也参与匹配（否则树里搜得到、全文搜不到）。"""
    _write(tmp_path, "行为面/无关键词.md", "正文里也没有那个词\n")
    body = _search(client, "行为").json()
    assert [h["rel"] for h in body["items"]] == ["行为面/无关键词.md"]
    assert body["items"][0]["inName"] is True


# --- 批量遍历的边界 ---------------------------------------------------------


def test_unreadable_file_goes_to_skipped_without_hiding_others(client, tmp_path):
    # 非法 UTF-8 的坏文件里也写着关键词：它该进 skipped，而不是被当成命中
    _write(tmp_path, "坏编码.md", b"\xff\xfe\x00bad " + "关键词".encode("utf-8") + b"\n")
    _write(tmp_path, "好的.md", "关键词 在这里\n")

    body = _search(client, "关键词").json()

    assert [h["rel"] for h in body["items"]] == ["好的.md"]
    assert any(s["rel"] == "坏编码.md" for s in body["skipped"])


def test_oversize_file_is_searched_partially_and_said_so(client, tmp_path):
    # 超过只读端点的 256 KB：只搜前半，并明确写进 skipped（不能默默只搜一半）
    _write(tmp_path, "big.md", "关键词\n" + "x" * (256 * 1024))
    body = _search(client, "关键词").json()
    assert [h["rel"] for h in body["items"]] == ["big.md"]
    assert any("256 KB" in s["reason"] for s in body["skipped"])


def test_readme_and_templates_are_searchable(client, tmp_path):
    """树里看得见、点得开的东西就该搜得到（与 1a 导入跳过它们的口径不同）。"""
    _write(tmp_path, "README.md", "目录说明：关键词\n")
    _write(tmp_path, "_模板_行为故事.md", "模板里的关键词\n")
    body = _search(client, "关键词").json()
    assert sorted(h["rel"] for h in body["items"]) == [
        "README.md", "_模板_行为故事.md"]


@pytest.mark.skipif(os.name != "posix", reason="符号链接场景仅在 POSIX 上验证")
def test_file_symlink_escape_is_not_returned(client, tmp_path):
    """文件级符号链接：`os.walk` 不跟随目录却会把它当普通文件——必须被 inside 拦下。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("关键词 在工作区外\n", encoding="utf-8")
    prep = tmp_path / WS / PREP_DIR
    prep.mkdir()
    os.symlink(str(outside / "secret.md"), str(prep / "link.md"))

    body = _search(client, "关键词").json()

    assert [h["rel"] for h in body["items"]] == []
    assert any(s["rel"] == "link.md" for s in body["skipped"])
