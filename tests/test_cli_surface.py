# -*- coding: utf-8 -*-
"""CLI 面的冒烟回归（B8 的前置安全网）。

为什么需要这一层：B8 把 `tools/` 下 10 个脚本的 CLI 面合并成 `jobws` 统一入口
且**不丢功能**，而在此之前 `tests/` 对 CLI 面**零覆盖**——等于没网搬家。
搬家时最容易丢掉的恰好是参数名与退出码语义，所以这里钉四件：

1. **每个入口都能被 `--help` 叫醒**，且子命令一个不少；
2. **退出码语义**：`--help` 是 0、用法错误是 2、不合法输入是 1（三种都有实例钉住）；
3. **有副作用的子命令在临时工作区跑一条真实路径**，断言真的落盘；
4. **分发层自身**：`jobws` 无参数、未知命令、缺子命令这些分支的退出码——
   网要跟着鱼走，新网自己也得钉住。

全部在进程内改 `sys.argv` 再调入口（沿用 `test_demo_workspace.py` 的做法），
不碰网络。两类例外：`resume_build` 真会 spawn 浏览器，所以只测它的「不合法
输入」分支；「旧脚本路径只给迁移提示」那一条必须起子进程——它验的正是
`python tools/xxx.py` 这种独立进程的行为。
"""

import os
import subprocess
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
import jobws  # noqa: E402
from jobws_core import jd_score  # noqa: E402
import release_assist  # noqa: E402  （`release version` 的号要走同一套判定函数）
from jobws_core import report  # noqa: E402
import resume_build  # noqa: E402
import tracker  # noqa: E402

# 有 CLI 面的入口（commit_header 是纯库，不在此列，见文末那条断言）
CLI_MODULES = [["track"], ["bank"], ["report"], ["resume"], ["jd"], ["init"],
               ["export"], ["prefs"], ["skills", "install"], ["skills", "check"],
               ["lint", "pr-title"], ["lint", "domains"], ["lint", "themes"],
               ["lint", "size"], ["lint", "four-ends"], ["lint", "legacy-imports"],
               ["release", "check"], ["release", "version"]]

TRACKER_SUBCOMMANDS = ["add", "update", "list", "show", "history", "delete",
                       "interview", "talk", "mail", "contact", "offer",
                       "import", "check"]


@pytest.fixture(autouse=True)
def _isolate_module_globals(monkeypatch):
    """把模块级全局挡在测试边界内。

    `tracker.WORKSPACE` 会被 `main()` 就地覆盖，`report.main` 还会经
    `set_workspace` 改同一个全局；`resume_build.VERIFY_FACTS_FILE` 同理。
    不隔离的话测试之间会串味，且顺序一变就飘。
    """
    # tracker 包化后 WORKSPACE 的真身在 tracker._core（门面只做 PEP 562 转发，
    # setattr 包门面只会改门面命名空间、真身不受影响——必须打真身）
    from tracker import _core as tracker_core
    monkeypatch.setattr(tracker_core, "WORKSPACE", tracker_core.WORKSPACE)
    monkeypatch.setattr(resume_build, "VERIFY_FACTS_FILE", resume_build.VERIFY_FACTS_FILE)
    monkeypatch.delenv("PR_TITLE", raising=False)


def _invoke_jobws(monkeypatch, capsys, argv):
    """经过**统一入口**调用一次命令：argv 形如 ["track", "list", ...]。

    B8 之后 CLI 面由 tools/jobws.py 承载，安全网必须跟着改指向——否则这些断言
    测的是各模块的 main()，而用户与 CI 实际走的是 jobws，等于网还在、鱼换了道。
    """
    monkeypatch.setattr(sys, "argv", ["jobws"] + list(argv))
    try:
        result = jobws.main()
        code = 0 if result is None else result
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _make_ws(tmp_path):
    """最小工作区：只建投递追踪目录，够 tracker 落盘用。"""
    ws = tmp_path / "ws"
    (ws / "05_投递追踪").mkdir(parents=True)
    return ws


# --- 1. 每个入口都能被 --help 叫醒 -------------------------------------------

@pytest.mark.parametrize("module", CLI_MODULES, ids=lambda m: " ".join(m))
def test_help_exits_zero(module, monkeypatch, capsys):
    code, out = _invoke_jobws(monkeypatch, capsys, module + ["--help"])
    assert code == 0, out
    assert "usage" in out.lower(), out


@pytest.mark.parametrize("sub", TRACKER_SUBCOMMANDS)
def test_tracker_subcommand_help_exits_zero(sub, monkeypatch, capsys):
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [sub, "--help"])
    assert code == 0, out
    assert "usage" in out.lower(), out


# --- 2. 参数名钉住（搬家最容易丢的东西）--------------------------------------

def test_tracker_add_option_names_are_pinned(monkeypatch, capsys):
    _code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["add", "--help"])
    for option in ("--company", "--role", "--direction", "--batch", "--source",
                   "--deadline", "--applied", "--stage", "--reason", "--next",
                   "--next-date", "--resume", "--score", "--archive", "--note"):
        assert option in out, "tracker add 少了参数 %s" % option


def test_tracker_import_keeps_dry_run(monkeypatch, capsys):
    _code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["import", "--help"])
    assert "--file" in out and "--dry-run" in out


def test_interview_contact_offer_keep_their_positional_action(monkeypatch, capsys):
    """这三组是「位置参数 action + 四个取值」的形态，搬家时最容易被改成子子命令。"""
    for sub in ("interview", "contact", "offer"):
        _code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [sub, "--help"])
        for action in ("add", "list", "show", "update", "delete"):
            assert action in out, "%s 少了 action %s" % (sub, action)


def test_tracker_keeps_top_level_workspace(monkeypatch, capsys):
    """--workspace 只在顶层（子命令之前）。B8 统一入口时这条语义要保留。"""
    _code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["--help"])
    assert "--workspace" in out


# --- 3. 退出码语义 -----------------------------------------------------------

def test_usage_error_exits_two(monkeypatch, capsys):
    """jd_score 既没给 card 也没给 --show-profile → parser.error → 退出码 2。"""
    code, _out = _invoke_jobws(monkeypatch, capsys, ["jd"] + [])
    assert code == 2


def test_tracker_without_subcommand_returns_one(tmp_path, monkeypatch, capsys):
    """必须显式给一个**存在**的工作区。

    tracker.main 先查工作区存在性再看有没有子命令，而默认工作区是 `<仓库>/personal`
    ——它在 CI 与任何新克隆上都不存在（已 gitignore）。不给 --workspace 的话，这条用例
    在本机走「打印帮助」分支、在 CI 走「工作区不存在」分支，断言会随机器变红。
    """
    ws = _make_ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["--workspace", str(ws)])
    assert code == 1
    assert "usage" in out.lower()


def test_resume_build_rejects_unknown_command(tmp_path, monkeypatch, capsys):
    """唯一有效值是 render；其它命令直接返回 1，不会去 spawn 浏览器。

    同样要显式给存在的工作区：`resume_build` 的工作区检查在未知子命令判断**之前**，
    不给的话这条断言在 CI 上会因为另一个原因通过（去掉未知命令 guard 也照样绿）。
    所以这里连错误文案一起钉住。
    """
    ws = _make_ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, ["resume"] + ["--workspace", str(ws), "not-a-command"])
    assert code == 1
    assert "未知子命令" in out, out


def test_check_pr_title_exit_codes(monkeypatch, capsys):
    assert _invoke_jobws(monkeypatch, capsys, ["lint", "pr-title"] + ["--title", "feat(x): 中文说明"])[0] == 0
    assert _invoke_jobws(monkeypatch, capsys, ["lint", "pr-title"] + ["--title", "english only subject"])[0] == 1
    # 既没给 --title 也没设 PR_TITLE → 退出码 2（与用法错误同档）
    assert _invoke_jobws(monkeypatch, capsys, ["lint", "pr-title"] + [])[0] == 2


def test_init_workspace_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    """目标目录非空且没给 --force → 返回 1：静默覆盖已填数据是数据丢失。"""
    monkeypatch.setattr(init_workspace, "ROOT", str(tmp_path))
    occupied = tmp_path / "ws"
    occupied.mkdir()
    (occupied / "occupant.txt").write_text("x", encoding="utf-8")
    code, _out = _invoke_jobws(monkeypatch, capsys, ["init"] + ["--target", "ws"])
    assert code == 1
    assert (occupied / "occupant.txt").exists()  # 没被动过


# --- 4. 真实路径：有副作用的子命令在临时工作区跑一遍 --------------------------

def test_tracker_add_writes_row_and_history(tmp_path, monkeypatch, capsys):
    ws = _make_ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [
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
    _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["--workspace", str(ws), "list"])
    assert code == 0, out
    assert "示例公司" in out


def test_tracker_rejects_missing_workspace(tmp_path, monkeypatch, capsys):
    """工作区不存在 → 返回 1，而不是在别处建一个目录。"""
    code, _out = _invoke_jobws(monkeypatch, capsys, ["track"] + ["--workspace", str(tmp_path / "nope"), "list"])
    assert code == 1


def test_report_stdout_prints_and_does_not_write_a_file(tmp_path, monkeypatch, capsys):
    """先真的写一条记录进去，否则 report 会提前返回「追踪表尚未创建」——
    那样这条用例只是在测一个空断言（写盘路径压根没跑到）。"""
    ws = _make_ws(tmp_path)
    _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke_jobws(monkeypatch, capsys, ["report"] + ["--workspace", str(ws), "--stdout"])
    assert code == 0
    # 断言「真的走了生成路径」：看板是聚合报表，不会列出公司名，
    # 所以钉的是「出看板了」且「不是那条尚未创建的提前返回」
    assert "投递看板" in out, out
    assert "尚未创建" not in out, out
    assert not (ws / "05_投递追踪" / "看板.md").exists()


def test_check_skills_passes_on_repo_skills(monkeypatch, capsys):
    code, out = _invoke_jobws(monkeypatch, capsys, ["skills", "check"] + ["--root", os.path.join(ROOT, "skills")])
    assert code == 0, out


def test_domain_and_release_checks_pass_on_repo(monkeypatch, capsys):
    """两条入口的真实路径（与 CI 同一命令）：真仓库的插件清单必须过；
    release check 只要求**可执行且给出结论**。

    时间戳体系（2026-09-15）之后，package.json 的版本是"下一个待发布"的机器形态
    （如 26.9.15），而 CHANGELOG 段要等**发布时**才落章——因此「未落章 → 退出码 1」
    是正常状态，不是缺陷（旧体系"bump 与落章必须同 PR"的假设已随单一发布节点作废）。
    真错是退出码 2（文件缺失/读取失败）。
    """
    code, out = _invoke_jobws(monkeypatch, capsys, ["lint", "domains"])
    assert code == 0, out
    code, out = _invoke_jobws(monkeypatch, capsys, ["release", "check"])
    assert code in (0, 1), out
    assert "版本：" in out, out
    # 同为退出码 1 也要区分原因：「段缺失」（未落章，正常）与「读取失败」（真错）
    # 不能混为一谈——否则这条例句对抽取逻辑漂移已经失去意义（第二轨 MINOR-13）。
    if code == 1:
        assert "CHANGELOG" in out, out
        assert "读取" not in out, out


def test_release_version_prints_next_timestamp_number(monkeypatch, capsys):
    """`jobws release version`：打印「今日若发布」的号（YY.MM.DD.N）与当前机器版本。"""
    code, out = _invoke_jobws(monkeypatch, capsys, ["release", "version"])
    assert code == 0, out
    lines = [line for line in out.splitlines() if "今日版本号：" in line]
    assert lines, out
    number = lines[0].split("：", 1)[1].strip()
    assert len(number.split(".")) == 4, number          # YY.MM.DD.N
    # 只数段数钉不住任何东西——走同一套判定函数，把月/日的取值范围也验上；
    # 且不依赖"测试跑在当天"，避免跨日 flaky（第二轨 MINOR-14）。
    parsed = release_assist.version_tuple(number)
    assert parsed is not None, number
    assert parsed[3] >= 1, number                       # N 从 1 起
    assert "当前 package.json 版本：" in out, out


def test_install_skills_dry_run_validates_but_writes_nothing(monkeypatch, capsys):
    """--dry-run 的要点是「**先校验**、只不复制」（install_skills.py 的注释写明了）。

    所以这条要同时钉住两件：真的跑了校验、真的没复制。只比较仓库根目录的列表是
    钉不住的——复制发生在子目录里。
    """
    target = os.path.join(ROOT, ".codebuddy", "skills")
    before = sorted(os.listdir(target)) if os.path.isdir(target) else None

    code, out = _invoke_jobws(monkeypatch, capsys, ["skills", "install"] + ["--target", "codebuddy", "--dry-run"])
    assert code == 0, out
    assert "校验通过" in out, out
    assert "将复制（演练）" in out, out

    after = sorted(os.listdir(target)) if os.path.isdir(target) else None
    assert after == before


def test_tracker_update_changes_stage_and_records_history(tmp_path, monkeypatch, capsys):
    """update 是仅次于 add 的高频子命令，且它同时写主表与时间线。"""
    ws = _make_ws(tmp_path)
    _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "add",
        "--company", "示例公司", "--role", "示例岗位",
        "--direction", "other", "--batch", "正式批",
    ])
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "update", "--id", "A001", "--stage", "已投",
    ])
    assert code == 0, out
    assert tracker.read_rows(str(ws))[0]["当前阶段"] == "已投"
    assert [h["字段"] for h in tracker.read_history(str(ws))] == ["创建", "当前阶段"]


def test_tracker_talk_add_writes_row(tmp_path, monkeypatch, capsys):
    """talk 是与 interview 平级的独立子命令：真实落一条，证明接线完整。"""
    ws = _make_ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "talk", "add",
        "--company", "示例公司", "--form", "线上",
    ])
    assert code == 0, out
    assert [r["公司"] for r in tracker.read_talks(str(ws))] == ["示例公司"]


def test_tracker_mail_add_writes_row(tmp_path, monkeypatch, capsys):
    """mail 是与 talk 平级的独立子命令：真实落一条，证明接线完整。"""
    ws = _make_ws(tmp_path)
    code, out = _invoke_jobws(monkeypatch, capsys, ["track"] + [
        "--workspace", str(ws), "mail", "add",
        "--subject", "面试通知",
    ])
    assert code == 0, out
    assert [r["主题"] for r in tracker.read_mails(str(ws))] == ["面试通知"]


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

    code, out = _invoke_jobws(monkeypatch, capsys, ["jd"] + [str(card), "--workspace", str(ws)])
    assert code == 0, out
    assert "80" in out, out
    assert "强烈建议投" in out, out


def test_legacy_script_paths_only_print_migration_hint():
    """旧路径不再执行功能：只给一条可复制的新命令，并以退出码 2 结束。

    这条钉的是「不保留旧别名」的**另一半**——不是让旧命令静默退出 0（那更危险：
    用户以为执行了、其实什么都没做），而是明确失败并指出该改用什么。
    """
    # `report` / `jd_score` / `question_bank` 已于 2026-09-19（PR-B）搬进领域包，
    # 旧脚本路径连同它们的提示文件一起消失——直跑 `python tools/report.py` 现在是
    # "文件不存在"，不再需要（也不该）有迁移提示。
    for script in ("tracker", "resume_build", "init_workspace", "install_skills",
                   "check_skills", "check_pr_title"):
        path = os.path.join(TOOLS, script + ".py")
        # timeout + cwd：任一脚本将来在导入期阻塞时，别把整轮 pytest 挂死
        proc = subprocess.run([sys.executable, path], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, encoding="utf-8",
                              errors="replace", timeout=60, cwd=ROOT)
        assert proc.returncode == 2, "%s 应以退出码 2 结束" % script
        assert "jobws" in proc.stdout, "%s 应给出 jobws 迁移提示" % script


def test_track_import_respects_explicit_workspace(tmp_path, monkeypatch, capsys):
    """`track --workspace X import` 必须写进 X。

    回归守卫（重构批独立审查 MAJOR-1）：包化后 importing 曾持 WORKSPACE 的
    值快照——显式 --workspace 被忽略、静默写去默认工作区（本机路径下就是
    tools/personal），落盘时还会静默建目录。这条用真实入口跑一次完整链路。
    """
    ws_x = tmp_path / "ws-explicit"
    ws_x.mkdir()
    csv_file = tmp_path / "in.csv"
    csv_file.write_text(
        "公司,岗位,方向,批次,当前阶段\n示例公司甲,示例岗位乙,backend,正式批,待投\n",
        encoding="utf-8")
    code, out = _invoke_jobws(monkeypatch, capsys,
                              ["track", "--workspace", str(ws_x),
                               "import", "--file", str(csv_file)])
    assert code == 0, out
    written = ws_x / "05_投递追踪" / "tracker.csv"
    assert written.is_file(), "导入必须落在显式指定的工作区（不是默认工作区）"


# --- 5. 分发层自身（网要跟着鱼走，新网自己也得钉）----------------------------

@pytest.mark.parametrize("argv,expected", [
    ([], 1),                      # 无命令：打印帮助并退出 1
    (["nope"], 2),                # 未知命令
    (["skills", "nope"], 2),      # 未知子命令
    (["skills"], 2),              # 缺子命令
    (["lint"], 2),                # 缺子命令
    (["--help"], 0),              # 顶层帮助
    (["skills", "--help"], 0),    # 只是想知道这组有哪些子命令
])
def test_dispatch_exit_codes(argv, expected, monkeypatch, capsys):
    code, out = _invoke_jobws(monkeypatch, capsys, argv)
    assert code == expected, out


def test_command_map_covers_every_merged_module():
    """19 个命令全部有映射，且每个模块仍然真的暴露 main()。

    安全网改走 jobws 之后，命令到模块的映射只由 TARGETS / SUB_TARGETS 单方保证；
    这里从「模块侧」反查一遍，免得改映射时悄悄漏掉一个。数字改动必须显式经过
    这行断言——新增命令时连 CLI_MODULES 的 --help 冒烟一起补（那是刻意的摩擦）。
    批 4.7 由 18 → 19：新增 `lint four-ends`（四端一致性检查器）。
    批 6 由 19 → 20：新增 `lint legacy-imports`（旧名 import 存量，只许下降）。
    2026-09-19 由 20 → 21：新增 `export --obsidian`（八张 CSV → Obsidian 笔记）。
    """
    mapped = {}
    for name, module, _help in jobws.TARGETS:
        if module is not None:
            mapped[name] = module
    for key, module in jobws.SUB_TARGETS.items():
        mapped[" ".join(key)] = module
    assert len(mapped) == 21, sorted(mapped)
    for command, module in mapped.items():
        assert callable(getattr(module, "main", None)), \
            "%s 指向的 %s 没有 main()" % (command, module)


# --- 5. 记录下来供 B8 用的事实 ----------------------------------------------

def test_commit_header_has_no_cli():
    """commit_header 是纯库（无 main、无 argparse）：B8 合并入口时它不该凭空长出子命令。"""
    assert not hasattr(commit_header, "main")
    assert callable(commit_header.validate)


# --- 6. 命令层分离的回归（2026-09-21 H 批：jd / resume）----------------------

def test_resume_cli_passes_facts_file_explicitly(tmp_path, monkeypatch, capsys):
    """手工 HTML 路径显式传 facts_file（H-2d 的行为变化点），不再靠模块级全局。

    打桩浏览器与 PDF 生成，只断言 verify_pdf 收到了 <ws>/config/ats_required_facts.txt——
    这条钉住「显式传参」这条链，防止将来有人把它改回 main 里写全局。
    """
    import io
    import _cli_resume

    ws = tmp_path / "ws"
    pdf_dir = ws / "02_简历工坊" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "resume_hvac.html").write_text("<html></html>", encoding="utf-8")
    facts = ws / "config" / "ats_required_facts.txt"
    facts.parent.mkdir()
    facts.write_text("关键事实一\n", encoding="utf-8")

    def fake_build(_browser, _html, pdf_path):
        io.open(pdf_path, "w", encoding="utf-8").write("x")
        return True

    seen = {}

    def fake_verify(pdf_path, min_len, facts_file=None):
        seen["facts"] = facts_file
        return True, [("页数", "1 页", True)]

    monkeypatch.setattr(_cli_resume, "find_browser", lambda: "chrome")
    monkeypatch.setattr(_cli_resume, "build_pdf", fake_build)
    monkeypatch.setattr(_cli_resume, "verify_pdf", fake_verify)

    code, out = _invoke_jobws(monkeypatch, capsys, ["resume", "--workspace", str(ws)])
    assert code == 0, out
    assert seen["facts"] == os.path.join(str(ws), "config", "ats_required_facts.txt")


# --- 7. CLI 真接线补网（T 批，2026-09-21）--------------------------------------

BANK_SUBCOMMANDS = ["list", "due", "wrong", "add", "update", "delete", "drill",
                    "import", "import-csv", "export"]


@pytest.mark.parametrize("sub", BANK_SUBCOMMANDS)
def test_bank_subcommand_help_exits_zero(sub, monkeypatch, capsys):
    """bank 分发层每个子命令都能被 --help 叫醒（此前只冒烟到 bank 这一层）。"""
    code, out = _invoke_jobws(monkeypatch, capsys, ["bank", sub, "--help"])
    assert code == 0, out
    assert "usage" in out.lower(), out


def test_track_contact_add_list_show_roundtrip(tmp_path, monkeypatch, capsys):
    """contact 此前只有 --help 名录：真跑 add → list → show，断言落盘与回读。"""
    ws = _make_ws(tmp_path)

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "contact", "add",
        "--name", "林工", "--role", "HR", "--company", "云帆",
        "--next-follow", "2026-09-25"])
    assert code == 0, out
    assert "已记录联系人" in out

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "contact", "list"])
    assert code == 0, out
    assert "林工" in out and "C001" in out

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "contact", "show", "--id", "C001"])
    assert code == 0, out
    assert "林工" in out


def test_track_offer_add_list_roundtrip(tmp_path, monkeypatch, capsys):
    """offer 同上：真跑 add（未关联时 --company 必给）→ list 回读。"""
    ws = _make_ws(tmp_path)

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "offer", "add",
        "--company", "云帆", "--monthly", "20k", "--deadline", "2026-10-01"])
    assert code == 0, out
    assert "已记录 offer" in out

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "offer", "list"])
    assert code == 0, out
    assert "O001" in out and "20k" in out


def test_track_show_and_history_roundtrip(tmp_path, monkeypatch, capsys):
    """show / history 此前只有 --help 名录：先 add 一条（写时间线）再真读。"""
    ws = _make_ws(tmp_path)

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "add",
        "--company", "云帆", "--role", "后端", "--direction", "other",
        "--batch", "正式批", "--stage", "已投"])
    assert code == 0, out

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "show", "--id", "A001"])
    assert code == 0, out
    assert "云帆" in out

    code, out = _invoke_jobws(monkeypatch, capsys, [
        "track", "--workspace", str(ws), "history", "--id", "A001"])
    assert code == 0, out
    assert "已投" in out or "A001" in out
