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


# --- 技能镜像 ----------------------------------------------------------------


def test_mirror_skips_missing_targets(tmp_path):
    """目标目录不存在＝该宿主没分发过，属正常状态，不报错也不计入已检查。"""
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "内容")
    issues, checked = four_ends_extras.skill_mirrors(str(tmp_path))
    assert issues == []
    assert checked == []


def test_mirror_reports_content_drift(tmp_path):
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-x" / "SKILL.md"), "旧的副本")
    issues, checked = four_ends_extras.skill_mirrors(str(tmp_path))
    # 标签从 install_skills.TARGETS 派生（批 4.7 审查修复：不再手抄），随源措辞
    assert checked == ["项目级 .claude/skills/"]
    assert any("内容不一致" in item for item in issues), issues


def test_mirror_reports_extra_file(tmp_path):
    _write(str(tmp_path / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-x" / "SKILL.md"), "真源")
    _write(str(tmp_path / ".claude" / "skills" / "jwb-extra" / "SKILL.md"), "多余的")
    issues, _checked = four_ends_extras.skill_mirrors(str(tmp_path))
    assert any("多出" in item for item in issues), issues
