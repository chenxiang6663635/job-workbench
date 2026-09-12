# -*- coding: utf-8 -*-
"""CLI 面的冒烟回归（B8 的前置安全网）。

为什么需要这一层：B8 要做的是把 `tools/` 下 9 个脚本的 CLI 面合并成 `jobws`
统一入口且**不丢功能**，而在此之前 `tests/` 对 CLI 面**零覆盖**——等于没网搬家。
搬家时最容易丢掉的恰好是参数名与退出码语义，所以这里钉三件：

1. **每个入口都能被 `--help` 叫醒**，且子命令一个不少；
2. **退出码语义**：`--help` 是 0、用法错误是 2、不合法输入是 1（三种都有实例钉住）；
3. **有副作用的子命令在临时工作区跑一条真实路径**，断言真的落盘。

不启子进程、不碰网络：全部在进程内改 `sys.argv` 再调 `main()`（沿用
`test_demo_workspace.py` 的做法）。唯一例外是 `resume_build`——它真会 spawn
浏览器，所以只测它的「不合法输入」分支（那条路不会启动任何进程）。
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import check_pr_title  # noqa: E402
import check_skills  # noqa: E402
import commit_header  # noqa: E402
import init_workspace  # noqa: E402
import install_skills  # noqa: E402
import jd_score  # noqa: E402
import report  # noqa: E402
import resume_build  # noqa: E402
import tracker  # noqa: E402

# 有 CLI 面的入口（commit_header 是纯库，不在此列，见文末那条断言）
CLI_MODULES = [tracker, report, resume_build, jd_score,
               init_workspace, install_skills, check_skills, check_pr_title]

TRACKER_SUBCOMMANDS = ["add", "update", "list", "show", "history",
                       "interview", "contact", "offer", "import", "check"]


@pytest.fixture(autouse=True)
def _isolate_module_globals(monkeypatch):
    """把模块级全局挡在测试边界内。

    `tracker.WORKSPACE` 会被 `main()` 就地覆盖，`report.main` 还会经
    `set_workspace` 改同一个全局；`resume_build.VERIFY_FACTS_FILE` 同理。
    不隔离的话测试之间会串味，且顺序一变就飘。
    """
    monkeypatch.setattr(tracker, "WORKSPACE", tracker.WORKSPACE)
    monkeypatch.setattr(resume_build, "VERIFY_FACTS_FILE", resume_build.VERIFY_FACTS_FILE)
    monkeypatch.delenv("PR_TITLE", raising=False)


def _invoke(monkeypatch, capsys, module, argv):
    """进程内跑一次 CLI，返回 (退出码, 输出)。

    统一处理两种收尾方式：`return <code>` 与 argparse 的 `SystemExit`。
    后者在 `--help`（0）与用法错误（2）时都会出现，写测试时最容易漏。
    """
    monkeypatch.setattr(sys, "argv", [module.__name__] + list(argv))
    code = 0
    try:
        result = module.main()
        code = 0 if result is None else result
    except SystemExit as exc:
        if exc.code is None:
            code = 0
        elif isinstance(exc.code, int):
            code = exc.code
        else:
            code = 1
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _make_ws(tmp_path):
    """最小工作区：只建投递追踪目录，够 tracker 落盘用。"""
    ws = tmp_path / "ws"
    (ws / "05_投递追踪").mkdir(parents=True)
    return ws


# --- 1. 每个入口都能被 --help 叫醒 -------------------------------------------

@pytest.mark.parametrize("module", CLI_MODULES, ids=lambda m: m.__name__)
def test_help_exits_zero(module, monkeypatch, capsys):
    code, out = _invoke(monkeypatch, capsys, module, ["--help"])
    assert code == 0, out
    assert "usage" in out.lower(), out


@pytest.mark.parametrize("sub", TRACKER_SUBCOMMANDS)
def test_tracker_subcommand_help_exits_zero(sub, monkeypatch, capsys):
    code, out = _invoke(monkeypatch, capsys, tracker, [sub, "--help"])
    assert code == 0, out
    assert "usage" in out.lower(), out


# --- 2. 参数名钉住（搬家最容易丢的东西）--------------------------------------

def test_tracker_add_option_names_are_pinned(monkeypatch, capsys):
    _code, out = _invoke(monkeypatch, capsys, tracker, ["add", "--help"])
    for option in ("--company", "--role", "--direction", "--batch", "--source",
                   "--deadline", "--applied", "--stage", "--reason", "--next",
                   "--next-date", "--resume", "--score", "--archive", "--note"):
        assert option in out, "tracker add 少了参数 %s" % option


def test_tracker_import_keeps_dry_run(monkeypatch, capsys):
    _code, out = _invoke(monkeypatch, capsys, tracker, ["import", "--help"])
    assert "--file" in out and "--dry-run" in out


def test_interview_contact_offer_keep_their_positional_action(monkeypatch, capsys):
    """这三组是「位置参数 action + 四个取值」的形态，搬家时最容易被改成子子命令。"""
    for sub in ("interview", "contact", "offer"):
        _code, out = _invoke(monkeypatch, capsys, tracker, [sub, "--help"])
        for action in ("add", "list", "show", "update"):
            assert action in out, "%s 少了 action %s" % (sub, action)


def test_tracker_keeps_top_level_workspace(monkeypatch, capsys):
    """--workspace 只在顶层（子命令之前）。B8 统一入口时这条语义要保留。"""
    _code, out = _invoke(monkeypatch, capsys, tracker, ["--help"])
    assert "--workspace" in out


# --- 3. 退出码语义 -----------------------------------------------------------

def test_usage_error_exits_two(monkeypatch, capsys):
    """jd_score 既没给 card 也没给 --show-profile → parser.error → 退出码 2。"""
    code, _out = _invoke(monkeypatch, capsys, jd_score, [])
    assert code == 2


def test_tracker_without_subcommand_returns_one(tmp_path, monkeypatch, capsys):
    """必须显式给一个**存在**的工作区。

    tracker.main 先查工作区存在性再看有没有子命令，而默认工作区是 `<仓库>/personal`
    ——它在 CI 与任何新克隆上都不存在（已 gitignore）。不给 --workspace 的话，这条用例
    在本机走「打印帮助」分支、在 CI 走「工作区不存在」分支，断言会随机器变红。
    """
    ws = _make_ws(tmp_path)
    code, out = _invoke(monkeypatch, capsys, tracker, ["--workspace", str(ws)])
    assert code == 1
    assert "usage" in out.lower()


def test_resume_build_rejects_unknown_command(tmp_path, monkeypatch, capsys):
    """唯一有效值是 render；其它命令直接返回 1，不会去 spawn 浏览器。

    同样要显式给存在的工作区：`resume_build` 的工作区检查在未知子命令判断**之前**，
    不给的话这条断言在 CI 上会因为另一个原因通过（去掉未知命令 guard 也照样绿）。
    所以这里连错误文案一起钉住。
    """
    ws = _make_ws(tmp_path)
    code, out = _invoke(monkeypatch, capsys, resume_build,
                        ["--workspace", str(ws), "not-a-command"])
    assert code == 1
    assert "未知子命令" in out, out


def test_check_pr_title_exit_codes(monkeypatch, capsys):
    assert _invoke(monkeypatch, capsys, check_pr_title,
                   ["--title", "feat(x): 中文说明"])[0] == 0
    assert _invoke(monkeypatch, capsys, check_pr_title,
                   ["--title", "english only subject"])[0] == 1
    # 既没给 --title 也没设 PR_TITLE → 退出码 2（与用法错误同档）
    assert _invoke(monkeypatch, capsys, check_pr_title, [])[0] == 2


def test_init_workspace_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    """目标目录非空且没给 --force → 返回 1：静默覆盖已填数据是数据丢失。"""
    monkeypatch.setattr(init_workspace, "ROOT", str(tmp_path))
    occupied = tmp_path / "ws"
    occupied.mkdir()
    (occupied / "occupant.txt").write_text("x", encoding="utf-8")
    code, _out = _invoke(monkeypatch, capsys, init_workspace, ["--target", "ws"])
    assert code == 1
    assert (occupied / "occupant.txt").exists()  # 没被动过


# --- 4. 真实路径：有副作用的子命令在临时工作区跑一遍 --------------------------

def test_tracker_add_writes_row_and_history(tmp_path, monkeypatch, capsys):
    ws = _make_ws(tmp_path)
    code, out = _invoke(monkeypatch, capsys, tracker, [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    assert code == 0, out
    assert [r["公司"] for r in tracker.read_rows(str(ws))] == ["示例公司"]
    # 新建也要入账时间线：否则「停留天数」没有基准
    assert [h["字段"] for h in tracker.read_history(str(ws))] == ["创建"]


def test_tracker_list_reads_back_what_add_wrote(tmp_path, monkeypatch, capsys):
    ws = _make_ws(tmp_path)
    _invoke(monkeypatch, capsys, tracker, [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke(monkeypatch, capsys, tracker, ["--workspace", str(ws), "list"])
    assert code == 0, out
    assert "示例公司" in out


def test_tracker_rejects_missing_workspace(tmp_path, monkeypatch, capsys):
    """工作区不存在 → 返回 1，而不是在别处建一个目录。"""
    code, _out = _invoke(monkeypatch, capsys, tracker,
                         ["--workspace", str(tmp_path / "nope"), "list"])
    assert code == 1


def test_report_stdout_prints_and_does_not_write_a_file(tmp_path, monkeypatch, capsys):
    """先真的写一条记录进去，否则 report 会提前返回「追踪表尚未创建」——
    那样这条用例只是在测一个空断言（写盘路径压根没跑到）。"""
    ws = _make_ws(tmp_path)
    _invoke(monkeypatch, capsys, tracker, [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke(monkeypatch, capsys, report, ["--workspace", str(ws), "--stdout"])
    assert code == 0
    # 断言「真的走了生成路径」：看板是聚合报表，不会列出公司名，
    # 所以钉的是「出看板了」且「不是那条尚未创建的提前返回」
    assert "投递看板" in out, out
    assert "尚未创建" not in out, out
    assert not (ws / "05_投递追踪" / "看板.md").exists()


def test_check_skills_passes_on_repo_skills(monkeypatch, capsys):
    code, out = _invoke(monkeypatch, capsys, check_skills,
                        ["--root", os.path.join(ROOT, "skills")])
    assert code == 0, out


def test_install_skills_dry_run_validates_but_writes_nothing(monkeypatch, capsys):
    """--dry-run 的要点是「**先校验**、只不复制」（install_skills.py 的注释写明了）。

    所以这条要同时钉住两件：真的跑了校验、真的没复制。只比较仓库根目录的列表是
    钉不住的——复制发生在子目录里。
    """
    target = os.path.join(ROOT, ".codebuddy", "skills")
    before = sorted(os.listdir(target)) if os.path.isdir(target) else None

    code, out = _invoke(monkeypatch, capsys, install_skills,
                        ["--target", "codebuddy", "--dry-run"])
    assert code == 0, out
    assert "校验通过" in out, out
    assert "将复制（演练）" in out, out

    after = sorted(os.listdir(target)) if os.path.isdir(target) else None
    assert after == before


def test_tracker_update_changes_stage_and_records_history(tmp_path, monkeypatch, capsys):
    """update 是仅次于 add 的高频子命令，且它同时写主表与时间线。"""
    ws = _make_ws(tmp_path)
    _invoke(monkeypatch, capsys, tracker, [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke(monkeypatch, capsys, tracker, [
        "--workspace", str(ws), "update", "--id", "A001", "--stage", "已投",
    ])
    assert code == 0, out
    assert tracker.read_rows(str(ws))[0]["当前阶段"] == "已投"
    assert [h["字段"] for h in tracker.read_history(str(ws))] == ["创建", "当前阶段"]


def _scored_card(total, dims):
    """四位维度之和必须等于总分，否则评分卡被判为不一致（consistent=False）。"""
    assert sum(dims) == total
    lines = ["%s: %d/%d" % (name, num, maximum)
             for (name, maximum), num in zip(jd_score.DIMENSIONS, dims)]
    return "# 解析卡\n\n## 评分\n" + "\n".join(lines) + "\n总分: %d\n" % total


def test_jd_score_prints_a_verdict_for_a_real_card(tmp_path, monkeypatch, capsys):
    """评分脚本的只读真实路径：给一张自洽的卡，必须打出档位。

    这条网对 B8 尤其重要——jd_score 是搬家时最容易「参数还在、逻辑走了样」的那种脚本。
    """
    ws = _make_ws(tmp_path)
    job = ws / "01_岗位池" / "示例公司_示例岗位"
    job.mkdir(parents=True)
    card = job / "解析卡.md"
    card.write_text(_scored_card(80, (24, 20, 24, 12)), encoding="utf-8")

    code, out = _invoke(monkeypatch, capsys, jd_score,
                        [str(card), "--workspace", str(ws)])
    assert code == 0, out
    assert "80" in out, out
    assert "强烈建议投" in out, out


# --- 5. 记录下来供 B8 用的事实 ----------------------------------------------

def test_commit_header_has_no_cli():
    """commit_header 是纯库（无 main、无 argparse）：B8 合并入口时它不该凭空长出子命令。"""
    assert not hasattr(commit_header, "main")
    assert callable(commit_header.validate)
