# -*- coding: utf-8 -*-
"""宣讲会 / 招聘会（v0.4.0-A）：数据层、CLI、API 与 ICS 的最小闭环。

钉住的核心口径（每条都对应一个真实会出事的场景）：

1. **关联记录是外键**——指到不存在的投递记录必须被拒绝（CLI 与 API 两处），
   否则列表里会出现对不上任何记录的孤儿行；
2. **未关联时公司必填**——不能有无主语的记录；
3. **枚举在三个入口都被拦**（CLI argparse choices / API 422 / run_check 自检），
   手改 CSV 绕过前两道时自检是最后一道拦网；
4. **入账纪律**：宣讲会不写主表时间线（它不是投递推进节点）——本文件用
   「主表与时间线在 talk 写入后逐字节不变」把它钉住。
"""

import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from jobws_core import tracker  # noqa: E402


def _ws(tmp_path):
    ws = os.path.join(str(tmp_path), "ws")
    os.makedirs(os.path.join(ws, "05_投递追踪"))
    return ws


def _seed_main(ws, app_id="A001"):
    row = {field: "" for field in tracker.FIELDS}
    row.update({"id": app_id, "公司": "示例公司", "岗位": "示例岗位",
                "方向": "other", "批次": "正式批", "当前阶段": "已投"})
    tracker.write_rows([row], ws)
    return row


# ---- 数据层 -----------------------------------------------------------------

def test_talk_roundtrip_and_next_id(tmp_path):
    ws = _ws(tmp_path)
    assert tracker.read_talks(ws) == []
    tracker.write_talks([{"宣讲会id": "T001", "公司": "示例公司",
                          "是否参加": "待定"}], ws)
    again = tracker.read_talks(ws)
    assert again[0]["宣讲会id"] == "T001"
    assert again[0]["公司"] == "示例公司"
    assert tracker.next_talk_id(again) == "T002"


def test_find_talk_and_app_filter(tmp_path):
    ws = _ws(tmp_path)
    tracker.write_talks([
        {"宣讲会id": "T001", "公司": "甲", "关联记录": "A001"},
        {"宣讲会id": "T002", "公司": "乙", "关联记录": ""},
    ], ws)
    assert tracker.find_talk(tracker.read_talks(ws), "T002")["公司"] == "乙"
    only_a1 = tracker.read_talks(ws, app_id="A001")
    assert [r["宣讲会id"] for r in only_a1] == ["T001"]


def test_talk_write_does_not_touch_main_table_or_timeline(tmp_path):
    """入账纪律：宣讲会不写主表、不入时间线——写前后主表与 history.csv 逐字节不变。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    main_path = os.path.join(ws, "05_投递追踪", "tracker.csv")
    before = io.open(main_path, "rb").read()

    tracker.write_talks([{"宣讲会id": "T001", "公司": "甲"}], ws)

    assert io.open(main_path, "rb").read() == before
    assert not os.path.isfile(os.path.join(ws, "05_投递追踪", "history.csv"))


def test_talk_apply_path_also_skips_timeline(tmp_path):
    """两段式落盘路径（apply_approved_talk）同样不写主表时间线（独立审查建议）。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    errors, plan = tracker.preview_talk_fields(
        {"公司": "示例公司", "关联记录": "A001", "是否参加": "参加"}, ws)
    assert errors == [] and plan
    tracker.apply_approved_talk(plan["payload"], ws)
    assert tracker.read_talks(ws)[0]["宣讲会id"] == "T001"
    assert not os.path.isfile(os.path.join(ws, "05_投递追踪", "history.csv"))


# ---- CLI --------------------------------------------------------------------

def _invoke_jobws(monkeypatch, capsys, argv):
    import jobws  # noqa: E402  （与 test_cli_surface 同一手法：进程内改 argv）
    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        code = jobws.main()
        code = 0 if code is None else code
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_cli_talk_add_and_list(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "talk", "add",
        "--company", "示例科技", "--when", "2026-09-20 14:00",
        "--form", "线上", "--attend", "参加", "--gain", "讲了流程"])
    assert code == 0, out
    rows = tracker.read_talks(ws)
    assert rows[0]["宣讲会id"] == "T001"
    assert rows[0]["是否参加"] == "参加"

    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", ws, "talk", "list"])
    assert code == 0, out
    assert "示例科技" in out


def test_cli_talk_add_requires_company_or_link(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    _seed_main(ws)
    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", ws, "talk", "add"])
    assert code == 1
    assert "company" in out


def test_cli_talk_add_rejects_missing_link(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    _seed_main(ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "talk", "add", "--app", "A999"])
    assert code == 1
    assert "A999" in out


def test_cli_talk_add_links_existing_record(tmp_path, monkeypatch, capsys):
    """关联记录存在时公司自动带出（与面试记录同款）。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "talk", "add", "--app", "A001"])
    assert code == 0, out
    rows = tracker.read_talks(ws)
    assert rows[0]["公司"] == "示例公司"
    assert rows[0]["关联记录"] == "A001"


def test_cli_talk_update_attendance(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    tracker.write_talks([{"宣讲会id": "T001", "公司": "甲", "是否参加": "待定"}], ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "talk", "update",
        "--id", "T001", "--attend", "参加"])
    assert code == 0, out
    assert tracker.read_talks(ws)[0]["是否参加"] == "参加"


# ---- run_check --------------------------------------------------------------

def test_run_check_flags_bad_talk_enum_and_missing_fk(tmp_path):
    ws = _ws(tmp_path)
    _seed_main(ws)
    tracker.write_talks([
        {"宣讲会id": "T001", "公司": "甲", "形式": "元宇宙",
         "是否参加": "待定", "关联记录": "A999"},
    ], ws)
    result = tracker.run_check(ws)
    issues = next(f for f in result["files"]
                  if f["file"] == tracker.TALK_FILE)["issues"]
    assert any("形式" in issue and "元宇宙" in issue for issue in issues)
    assert any("关联记录" in issue and "A999" in issue for issue in issues), issues


def test_run_check_talk_file_may_be_absent(tmp_path):
    """talks.csv 尚未创建不是错误——旧工作区升级上来就是没有这个文件。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    result = tracker.run_check(ws)
    item = next(f for f in result["files"] if f["file"] == tracker.TALK_FILE)
    assert item["ok"] is True and "尚未创建" in item["note"]


# ---- API --------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import deps  # noqa: E402
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / "ws-ok").mkdir()

    import main  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402
    return TestClient(main.app)


WS = "ws-ok"


def test_api_talk_create_list_and_patch(tmp_path, client):
    _seed_main(os.path.join(str(tmp_path), WS))
    res = client.post("/api/progress/talks", params={"ws": WS},
                      json={"公司": "示例科技", "时间": "2026-09-20 14:00",
                            "形式": "线下", "是否参加": "待定"})
    assert res.status_code == 201, res.text
    talk_id = res.json()["宣讲会id"]

    res = client.get("/api/progress/talks", params={"ws": WS})
    assert res.status_code == 200
    assert [r["宣讲会id"] for r in res.json()["rows"]] == [talk_id]

    res = client.patch("/api/progress/talks/%s" % talk_id, params={"ws": WS},
                       json={"是否参加": "参加"})
    assert res.status_code == 200, res.text
    assert res.json()["是否参加"] == "参加"


def test_api_talk_link_brings_company(tmp_path, client):
    _seed_main(os.path.join(str(tmp_path), WS))
    res = client.post("/api/progress/talks", params={"ws": WS},
                      json={"关联记录": "A001"})
    assert res.status_code == 201, res.text
    assert res.json()["公司"] == "示例公司"


def test_api_talk_rejects_bad_enum(client):
    res = client.post("/api/progress/talks", params={"ws": WS},
                      json={"公司": "甲", "形式": "元宇宙"})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.talkFormInvalid"


def test_api_talk_rejects_missing_link(tmp_path, client):
    _seed_main(os.path.join(str(tmp_path), WS))
    res = client.post("/api/progress/talks", params={"ws": WS},
                      json={"关联记录": "A999"})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.talkLinkNotFound"


def test_api_talk_requires_company_when_unlinked(client):
    res = client.post("/api/progress/talks", params={"ws": WS}, json={})
    assert res.status_code == 422
    assert res.json()["error_code"] == "progress.talkCompanyRequired"


def test_api_talks_ics_exports_events(tmp_path, client):
    ws = os.path.join(str(tmp_path), WS)
    _seed_main(ws)
    tracker.write_talks([
        {"宣讲会id": "T001", "公司": "示例科技", "时间": "2026-09-20 14:00",
         "形式": "线上", "是否参加": "参加"},
    ], ws)
    res = client.get("/api/progress/talks.ics", params={"ws": WS})
    assert res.status_code == 200
    text = res.text
    assert "BEGIN:VCALENDAR" in text
    assert "示例科技 宣讲会/招聘会" in text
    assert "DTSTART:20260920T140000" in text


def test_api_talks_ics_empty_gives_404(client):
    res = client.get("/api/progress/talks.ics", params={"ws": WS})
    assert res.status_code == 404
    assert res.json()["error_code"] == "progress.talksIcsEmpty"
