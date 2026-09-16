# -*- coding: utf-8 -*-
"""邮件记录（批 4.5）：数据层、CLI 与 schema 自检的最小闭环（API 段后续补）。

钉住的核心口径（每条都对应一个真实会出事的场景）：

1. **关联记录是外键**——指到不存在的投递记录必须被拒绝，否则邮件列表里
   会出现对不上任何记录的孤儿行；
2. **主题必填**——没有主语的记录进了表，一个月后没人认得出它是什么；
3. **消息id 去重**——同一封邮件导两遍，列表会长出一模一样的行；
4. **枚举三入口**（CLI argparse choices / API 422 / run_check 自检）——手改
   CSV 绕过前两道时，自检是最后一道拦网；
5. **入账纪律**：邮件不推进阶段、不入主表时间线——主表在写入前后逐字节不变；
6. **两段式**：--preview 不碰工作区一个字节；令牌一次性，复用即失败。
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import tracker  # noqa: E402


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


def _read_bytes(path):
    with io.open(path, "rb") as f:
        return f.read()


# ---- 数据层 -----------------------------------------------------------------

def test_mail_roundtrip_and_next_id(tmp_path):
    ws = _ws(tmp_path)
    assert tracker.read_mails(ws) == []
    tracker.write_mails([{"邮件id": "M001", "主题": "面试通知",
                          "标签": "邀约"}], ws)
    again = tracker.read_mails(ws)
    assert again[0]["主题"] == "面试通知"
    assert tracker.next_mail_id(again) == "M002"


def test_validate_mail_fields(tmp_path):
    ws = _ws(tmp_path)
    _seed_main(ws)
    errors = tracker._validate_mail_fields(
        {"关联记录": "A999", "主题": "", "方向": "元宇宙", "标签": "广告"}, ws)
    assert any("A999" in e for e in errors)
    assert any("--subject" in e for e in errors)
    assert any("--direction" in e for e in errors)
    assert any("--tag" in e for e in errors)


def test_validate_rejects_duplicate_message_id(tmp_path):
    ws = _ws(tmp_path)
    tracker.write_mails([{"邮件id": "M001", "消息id": "abc@example.com",
                          "主题": "一"}], ws)
    errors = tracker._validate_mail_fields(
        {"消息id": "abc@example.com", "主题": "二"}, ws)
    assert any("已记录过" in e for e in errors)


def test_preview_does_not_touch_workspace(tmp_path):
    """「预览即承诺」的反面：预览阶段不碰工作区一个字节（两段式的硬闸门）。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    main_path = os.path.join(ws, "05_投递追踪", "tracker.csv")
    before = _read_bytes(main_path)
    errors, plan = tracker.preview_mail_fields(
        {"主题": "面试通知", "关联记录": "A001", "标签": "邀约"}, ws)
    assert errors == [] and plan
    assert not os.path.isfile(tracker.mail_path(ws)), "预览不允许创建 mails.csv"
    assert _read_bytes(main_path) == before


def test_apply_writes_and_leaves_main_and_history_untouched(tmp_path):
    """邮件不入主表时间线：它不是投递流程的推进节点，只是往来证据。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    main_path = os.path.join(ws, "05_投递追踪", "tracker.csv")
    before = _read_bytes(main_path)
    errors, plan = tracker.preview_mail_fields(
        {"主题": "面试通知", "关联记录": "A001", "方向": "收", "标签": "邀约",
         "发件人": "hr@example.com", "日期": "2026-09-16 10:00"}, ws)
    assert errors == [], errors
    result = tracker.apply_approved_mail(plan["payload"], ws)
    assert result["id"] == "M001"
    rows = tracker.read_mails(ws)
    assert rows[0]["主题"] == "面试通知" and rows[0]["关联记录"] == "A001"
    assert _read_bytes(main_path) == before
    assert tracker.read_history(ws) == []


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


def test_cli_mail_add_and_list(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    _seed_main(ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "mail", "add",
        "--subject", "面试通知（一面）", "--app", "A001",
        "--tag", "邀约", "--message-id", "abc@example.com",
        "--from", "hr@example.com", "--when", "2026-09-16 10:00"])
    assert code == 0, out
    rows = tracker.read_mails(ws)
    assert rows[0]["邮件id"] == "M001"
    assert rows[0]["消息id"] == "abc@example.com"
    assert rows[0]["标签"] == "邀约"

    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", ws, "mail", "list"])
    assert code == 0, out
    assert "面试通知（一面）" in out


def test_cli_mail_add_requires_subject(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", ws, "mail", "add"])
    assert code == 1
    assert "--subject" in out


def test_cli_mail_preview_token_flow(tmp_path, monkeypatch, capsys):
    """两段式：--preview 出令牌且不落盘；apply 落盘；令牌一次性。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "mail", "add",
        "--subject", "笔试通知", "--preview"])
    assert code == 0, out
    assert not os.path.isfile(tracker.mail_path(ws)), "预览阶段不允许落盘"
    token = out.split("apply ")[1].split()[0].strip()
    assert token

    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["apply", token, "--workspace", ws])
    assert code == 0, out
    assert tracker.read_mails(ws)[0]["主题"] == "笔试通知"

    # 令牌一次性：第二次 apply 必须失败（退出码 1）
    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["apply", token, "--workspace", ws])
    assert code == 1


def test_cli_mail_update_and_argparse_rejects_bad_enum(tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path)
    tracker.write_mails([{"邮件id": "M001", "主题": "一", "标签": "其他"}], ws)
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "mail", "update",
        "--id", "M001", "--tag", "拒信"])
    assert code == 0, out
    assert tracker.read_mails(ws)[0]["标签"] == "拒信"
    # argparse choices 在用法层拦截（退出码 2）
    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", ws, "mail", "update",
        "--id", "M001", "--tag", "广告"])
    assert code == 2


# ---- run_check --------------------------------------------------------------

def test_run_check_flags_bad_mail_enum_and_missing_fk(tmp_path):
    """手改 CSV 填了枚举外的值 / 指到不存在的记录：自检是最后一道拦网。"""
    ws = _ws(tmp_path)
    _seed_main(ws)
    tracker.write_mails([
        {"邮件id": "M001", "主题": "甲", "方向": "读", "标签": "邀约",
         "关联记录": "A001"},
        {"邮件id": "M002", "主题": "乙", "方向": "收", "标签": "广告",
         "关联记录": "A999"},
    ], ws)
    result = tracker.run_check(ws)
    item = next(f for f in result["files"] if f["file"] == tracker.MAIL_FILE)
    assert not item["ok"]
    joined = " ".join(item["issues"])
    assert "方向" in joined and "读" in joined
    assert "标签" in joined and "广告" in joined
    assert "A999" in joined
