# -*- coding: utf-8 -*-
"""四端一致性检查器（批 4.7）的解析与校验分支。

两条线：
1. **真实仓库基线**：当前仓库必须通过——矩阵、说明页、技能镜像三者同步。
   谁改坏了矩阵或忘了重新生成说明页，这条会先红。
2. **解析分支**：把最容易悄悄坏掉的三处单独钉住——MCP 工具的 ast 抓取、
   GUI 两层 prefix（包 __init__ 的 prefix 要拼到子模块路由上）、
   共享 glob 的两层匹配、以及镜像比对的"目标不存在＝正常"语义。
"""
from __future__ import annotations

import os
import sys

import pytest

# 自插 sys.path：单独跑本文件也要能过
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import check_four_ends  # noqa: E402
# 取值与渲染按规模预算拆在两个模块里（批 4.7）；测试直接打各自的归属处。
import four_ends_extras  # noqa: E402
import four_ends_probe  # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


# --- 真实仓库基线 ------------------------------------------------------------


def test_repo_baseline_is_ok():
    """当前仓库必须通过：矩阵登记的都在、存在的都登记了、说明页同步、镜像一致。"""
    issues, doc = check_four_ends.check(ROOT)
    assert doc, "说明页渲染不应为空"
    assert issues == [], "四端一致性检查未通过：\n" + "\n".join(issues)


def test_matrix_covers_main_flow_stages():
    """主线七个阶段都要有登记——漏一个阶段等于整段能力无人看管。"""
    matrix, errors = check_four_ends.load_matrix(ROOT)
    assert errors == []
    stages = {cap.get("stage") for cap in matrix["capabilities"]}
    for stage in ("JD 解析", "岗位池", "投递", "跟进", "面试", "复盘", "题库", "通用"):
        assert stage in stages, "矩阵缺少阶段：%s" % stage


# --- 解析分支 ----------------------------------------------------------------


def test_mcp_tools_parsed_in_registration_order(tmp_path):
    """工具清单必须按注册顺序取到（冒烟测试按顺序钉住，缺一个就报）。"""
    server = tmp_path / "mcp" / "jobws_mcp" / "server.py"
    _write(str(server), (
        "def build_server():\n"
        "    @mcp.tool()\n"
        "    def list_applications():\n"
        "        pass\n"
        "    @mcp.tool()\n"
        "    def preview_add_application():\n"
        "        pass\n"
    ))
    names, errors = four_ends_probe.mcp_tools(str(tmp_path))
    assert errors == []
    assert names == ["list_applications", "preview_add_application"]


def test_gui_routes_includes_package_prefix(tmp_path):
    """两层结构：包 __init__ 声明 prefix，子模块的 router 不带 prefix。

    少了这条拼接，所有 `/api/progress/*` 的能力都会被误报成"找不到路由"。
    """
    pkg = tmp_path / "web" / "backend" / "routers" / "progress"
    _write(str(pkg / "__init__.py"),
           'router = APIRouter(prefix="/api/progress")\n')
    _write(str(pkg / "questions.py"), (
        "router = APIRouter()\n\n"
        '@router.get("/questions")\n'
        "def list_questions():\n"
        "    pass\n"
    ))
    routes, errors = four_ends_probe.gui_routes(str(tmp_path))
    assert errors == []
    assert ("GET", "/api/progress/questions") in routes


def test_gui_routes_reads_own_prefix(tmp_path):
    routers = tmp_path / "web" / "backend" / "routers"
    _write(str(routers / "jobs.py"), (
        'router = APIRouter(prefix="/api/jobs")\n\n'
        '@router.post("/fetch-jd")\n'
        "def fetch_jd():\n"
        "    pass\n"
    ))
    routes, _errors = four_ends_probe.gui_routes(str(tmp_path))
    assert ("POST", "/api/jobs/fetch-jd") in routes


def test_glob_field_present_two_levels(tmp_path):
    _write(str(tmp_path / "skills" / "jwb-track" / "SKILL.md"),
           "---\nname: jwb-track\ncompatibility: 本地运行\n---\n")
    assert four_ends_extras.glob_field_present(
        str(tmp_path), "skills/*/SKILL.md", "compatibility")
    assert not four_ends_extras.glob_field_present(
        str(tmp_path), "skills/*/SKILL.md", "agentMode")


def test_glob_field_present_flat_dir(tmp_path):
    _write(str(tmp_path / "commands" / "today.md"),
           "---\ndescription: 今日待办\n---\n")
    assert four_ends_extras.glob_field_present(
        str(tmp_path), "commands/*.md", "description")
    assert not four_ends_extras.glob_field_present(
        str(tmp_path), "commands/*.md", "allowed-tools")


# --- 资产镜像（skills / commands / agents）-------------------------------------


def test_mirror_skips_missing_targets(tmp_path):
    """目标目录不存在＝该宿主没分发过，属正常状态，不报错也不计入已检查。"""
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "内容")
    issues, checked = four_ends_extras.asset_mirrors(str(tmp_path))
    assert issues == []
    assert checked == []


def test_mirror_reports_content_drift(tmp_path):
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-x" / "SKILL.md"), "旧的副本")
    issues, checked = four_ends_extras.asset_mirrors(str(tmp_path))
    # 标签从 install_skills.ASSETS 派生（批 4.7 审查修复：不再手抄），随源措辞
    assert checked == ["skills → 项目级 .claude/skills/"]
    assert any("内容不一致" in item for item in issues), issues


def test_mirror_reports_extra_file(tmp_path):
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-extra" / "SKILL.md"), "多余的")
    issues, _checked = four_ends_extras.asset_mirrors(str(tmp_path))
    assert any("多出" in item for item in issues), issues


def test_mirror_covers_commands_and_agents(tmp_path):
    """批 10：命令与子代理也纳入镜像比对——它们同样是「仓库即插件」的一半。

    只比技能的话，改了 `commands/today.md` 却忘记重新分发，本地与 CI 全绿，
    而宿主侧跑的还是旧命令。
    """
    _write(str(tmp_path / "commands" / "today.md"), "真源命令")
    _write(str(tmp_path / ".claude" / "commands" / "today.md"), "旧命令")
    _write(str(tmp_path / "agents" / "resume-jd-gap.md"), "真源子代理")
    _write(str(tmp_path / ".codebuddy" / "agents" / "resume-jd-gap.md"), "真源子代理")

    issues, checked = four_ends_extras.asset_mirrors(str(tmp_path))

    assert "commands → 项目级 .claude/commands/" in checked
    assert "agents → 项目级 .codebuddy/agents/" in checked
    assert any("today.md 与真源内容不一致" in item for item in issues), issues
    # 一致的那一份不该报
    assert not any("resume-jd-gap" in item for item in issues), issues


def test_extra_files_are_only_reported_for_skills(tmp_path):
    """「多出」只在技能上判（批 10 审查 MINOR-5）。

    `.claude/commands` 这类目录也是用户放自己文件的地方——把他们的文件报成
    「手工加的副本」会让这张网失去信任（而它主要在本机跑，CI 看不到）。
    """
    _write(str(tmp_path / "commands" / "today.md"), "真源命令")
    _write(str(tmp_path / ".claude" / "commands" / "today.md"), "真源命令")
    _write(str(tmp_path / ".claude" / "commands" / "my-own.md"), "用户自己的命令")
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-leftover" / "SKILL.md"), "残留")

    issues, _checked = four_ends_extras.asset_mirrors(str(tmp_path))

    assert not any("my-own.md" in item for item in issues), issues
    assert any("jwb-leftover" in item for item in issues), issues


def test_mirror_follows_symlinked_entries(tmp_path):
    """`--link` 分发出来的目标项是符号链接：不跟随的话会把正确分发报成缺件。"""
    _write(str(tmp_path / "commands" / "today.md"), "真源命令")
    target_dir = tmp_path / ".claude" / "commands"
    target_dir.mkdir(parents=True)
    try:
        os.symlink(str(tmp_path / "commands" / "today.md"),
                   str(target_dir / "today.md"))
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许建符号链接（Windows 未开开发者模式）")

    issues, checked = four_ends_extras.asset_mirrors(str(tmp_path))

    assert "commands → 项目级 .claude/commands/" in checked
    assert issues == [], issues
