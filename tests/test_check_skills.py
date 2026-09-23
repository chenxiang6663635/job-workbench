# -*- coding: utf-8 -*-
"""tools/check_skills.py 的回归。

命门在两个方向都要测：合规的必须放行（否则校验成了噪音），
不合规的必须拦住（否则等于没校验）。重名那条尤其要留反例——它拦的是
「宿主静默覆盖」这种**不报错**的事故，一旦回归失手，不会有任何红字提醒。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from check_skills import describe, inspect_skills, version_problems  # noqa: E402

GOOD = """---
name: {name}
description: Use when 用户要做某件事时。English triggers：do a thing.
compatibility: Python 3.12+；需仓库内 tools/ 脚本。
---

# 标题

正文。
"""


def _make(tmp_path, dirname, body=None, name=None):
    d = tmp_path / dirname
    d.mkdir()
    (d / "SKILL.md").write_text(
        GOOD.format(name=name or dirname) if body is None else body,
        encoding="utf-8")
    return d


def test_compliant_skill_passes(tmp_path):
    _make(tmp_path, "jwb-demo")
    results = inspect_skills(str(tmp_path))
    assert len(results) == 1
    assert results[0]["name"] == "jwb-demo"
    assert results[0]["problems"] == []


def test_frontmatter_may_reference_tools_path(tmp_path):
    """frontmatter 里的 `tools/` 是**合法**的（校验项第 6 条只扫正文）。

    `compatibility` 正是说明"命令在仓库里长什么样"的地方——把它也禁掉的话，
    技能就没有任何位置能写清 `jobws` 到底是什么了。
    """
    assert "tools/" in GOOD, "固件要在 frontmatter 里带 tools/，这条断言才有意义"
    _make(tmp_path, "jwb-demo")
    assert inspect_skills(str(tmp_path))[0]["problems"] == []


def test_body_referencing_repo_path_is_reported(tmp_path):
    """正文出现 `tools/...` → 拦住。

    技能会被分发到宿主的技能目录，那时的工作目录是**用户自己的工作区**、
    不在这个仓库里，正文里的 `tools/jobws.py` 只会把宿主引到死路径上。
    """
    body = GOOD.format(name="jwb-demo").replace(
        "# 标题", "# 标题\n\n先运行 `python tools/jobws.py track list`。")
    _make(tmp_path, "jwb-demo", body=body)

    problems = inspect_skills(str(tmp_path))[0]["problems"]

    assert any("仓库相对路径" in p for p in problems), problems
    # 行号要准：GOOD 的正文第 4 行（文件第 9 行）就是那处引用
    assert any("第 9 行" in p for p in problems), problems


def test_body_may_use_bare_jobws_command(tmp_path):
    """正文写命令名 `jobws`（不带路径）→ 放行——这正是改完之后的形态。"""
    body = GOOD.format(name="jwb-demo").replace(
        "# 标题", "# 标题\n\n运行 `jobws track list` 查看投递记录。")
    _make(tmp_path, "jwb-demo", body=body)

    assert inspect_skills(str(tmp_path))[0]["problems"] == []


def test_body_references_to_other_repo_dirs_are_reported(tmp_path):
    """仓库顶层目录不止 `tools/` 一个：web/、template/、skills/、tests/ 同样会被拦。

    独立审查指出最初只禁 `tools/` 是漏的——那些路径分发到宿主后一样是死的。
    """
    for index, path in enumerate(("skills/jwb-x/SKILL.md", "web/backend/demo.py",
                                  "template/profiles/x/lexicon.md", "tests/test_x.py")):
        dirname = "jwb-demo%d" % index
        body = GOOD.format(name=dirname).replace(
            "# 标题", "# 标题\n\n见 `%s`。" % path)
        _make(tmp_path, dirname, body=body)

        problems = inspect_skills(str(tmp_path))[0]["problems"]
        assert any("仓库相对路径" in p for p in problems), (path, problems)


def test_result_shape_is_stable(tmp_path):
    """CI 与分发脚本都按这三个键取值，形状不能悄悄变。"""
    _make(tmp_path, "jwb-demo")
    item = inspect_skills(str(tmp_path))[0]
    assert set(item.keys()) == {"dir", "name", "problems"}
    assert isinstance(item["problems"], list)


def test_missing_skill_md_is_reported(tmp_path):
    (tmp_path / "jwb-empty").mkdir()
    results = inspect_skills(str(tmp_path))
    assert results[0]["problems"] == ["缺少 SKILL.md"]


def test_missing_frontmatter_is_reported(tmp_path):
    _make(tmp_path, "jwb-demo", body="# 没有 frontmatter\n")
    item = inspect_skills(str(tmp_path))[0]
    assert any("缺少 frontmatter" in p for p in item["problems"])


def test_unclosed_frontmatter_is_reported(tmp_path):
    _make(tmp_path, "jwb-demo", body="---\nname: jwb-demo\n正文没有闭合\n")
    item = inspect_skills(str(tmp_path))[0]
    assert any("未闭合" in p for p in item["problems"])


def test_name_must_equal_dir_name(tmp_path):
    _make(tmp_path, "jwb-demo", name="some-other-name")
    item = inspect_skills(str(tmp_path))[0]
    assert any("name 与目录名不一致" in p for p in item["problems"])


def test_missing_required_fields_are_reported(tmp_path):
    _make(tmp_path, "jwb-demo", body="---\nname: jwb-demo\n---\n\n正文。\n")
    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("缺 description" in p for p in problems)
    assert any("缺 compatibility" in p for p in problems)


def test_too_long_description_is_reported(tmp_path):
    long_desc = "x" * 400
    _make(tmp_path, "jwb-demo", body=(
        "---\nname: jwb-demo\ndescription: %s\ncompatibility: ok\n---\n" % long_desc))
    item = inspect_skills(str(tmp_path))[0]
    assert any("description 过长" in p for p in item["problems"])


def test_duplicate_names_are_reported_on_both_sides(tmp_path):
    """同名静默覆盖的反例：两个目录都用了同一个 name。

    只报后一个是错的——读者会以为前一个没问题。两个都要标记。
    """
    _make(tmp_path, "jwb-a", name="resume")
    _make(tmp_path, "jwb-b", name="resume")
    results = inspect_skills(str(tmp_path))
    flagged = [r for r in results if any("技能名重复" in p for p in r["problems"])]
    assert len(flagged) == 2
    for item in flagged:
        assert any("静默覆盖" in p for p in item["problems"])


def test_same_name_as_dir_but_different_dirs_is_not_duplicate(tmp_path):
    """目录名不同、name 各等于自己的目录名——不该被判重名。"""
    _make(tmp_path, "jwb-a")
    _make(tmp_path, "jwb-b")
    results = inspect_skills(str(tmp_path))
    assert all(r["problems"] == [] for r in results)


def test_describe_renders_problems_and_ok(tmp_path):
    _make(tmp_path, "jwb-ok")
    _make(tmp_path, "jwb-bad", body="no frontmatter here\n")
    text = describe(inspect_skills(str(tmp_path)))
    assert "已检查 2 个技能，1 个不合规。" in text
    assert "[jwb-bad]" in text


def test_empty_root_returns_empty_list(tmp_path):
    assert inspect_skills(str(tmp_path)) == []


def test_name_without_prefix_is_reported(tmp_path):
    """前缀规则：唯一性只保证仓库内不重名，兑现「不撞车」的是命名空间。"""
    _make(tmp_path, "stray", body=(
        "---\nname: stray\ndescription: x\ncompatibility: ok\n---\n"))
    item = inspect_skills(str(tmp_path))[0]
    assert any("jwb- 前缀" in p for p in item["problems"])


def test_legacy_generic_name_is_rejected(tmp_path):
    """旧通用名即便「name == 目录名」也必须被拦下——否则改名会被悄悄退回去。"""
    _make(tmp_path, "apply")
    item = inspect_skills(str(tmp_path))[0]
    assert any("jwb- 前缀" in p for p in item["problems"])


def test_block_scalar_description_is_rejected(tmp_path):
    """`description: |` 会被单行解析器读成 "|"，从而绕过长度上限。"""
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: |\n  这里可以写八百字\ncompatibility: ok\n---\n"))
    item = inspect_skills(str(tmp_path))[0]
    assert any("块标量" in p for p in item["problems"])


def test_yaml_unsafe_colon_in_description_is_rejected(tmp_path):
    """description 里半角冒号+空格：严格 YAML 宿主拒绝整个技能（Codex 实测）。

    本仓库自己的解析器用 partition 切分、对冒号宽容——所以「本地全绿、Codex
    全红」正是这条要堵的盲区（2026-09-14：`English triggers: …` 让 5 个技能
    在三处镜像目录全部加载失败）。
    """
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: Use when 做事。English triggers: do it.\n"
        "compatibility: ok\n---\n"))
    item = inspect_skills(str(tmp_path))[0]
    assert any("半角冒号" in p for p in item["problems"])


def test_quoted_colon_in_description_is_still_rejected(tmp_path):
    """引号包裹**不**豁免 `: ` 检查——这是有意的仓库额外限制。

    跨宿主审查第三轮指出「合法引号字符串会被误拒」：本仓库刻意不支持引号
    写法（单行解析器没有引号语义，支持一半比不支持更危险），描述文案统一
    不用半角冒号+空格。把这条边界固定下来。
    """
    _make(tmp_path, "jwb-x", body=(
        '---\nname: jwb-x\ndescription: "Use when 做事。English triggers: review"\n'
        "compatibility: ok\n---\n"))
    item = inspect_skills(str(tmp_path))[0]
    assert any("半角冒号" in p for p in item["problems"])


def test_unknown_frontmatter_field_is_reported(tmp_path):
    """字段白名单（批 10，对齐 Open Agent Skills 规范）：拼错的字段名必须拦住。

    `licence` / `allowed_tools` 这类手滑不会让宿主报错——它只是**静默失效**
    （元数据没生效，而本地全绿）。规范字段集之外的键一律报出来。
    """
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: x\ncompatibility: ok\nlicence: MIT\n---\n"))
    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("未登记" in p and "licence" in p for p in problems), problems


def test_standard_optional_fields_are_accepted(tmp_path):
    """规范允许的可选字段（license / metadata / allowed-tools）要放行。"""
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: x\ncompatibility: ok\n"
        "license: MIT\nmetadata:\n  version: 1.2.3\nallowed-tools: Bash(jobws:*)\n"
        "---\n\n正文。\n"))
    assert inspect_skills(str(tmp_path))[0]["problems"] == []


def test_nested_metadata_keys_are_not_treated_as_unknown(tmp_path):
    """`metadata:` 的下级键（缩进行）属于父字段，不算未登记字段。"""
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: x\ncompatibility: ok\n"
        "metadata:\n  version: 0.1.0\n  author: someone\n---\n\n正文。\n"))
    assert inspect_skills(str(tmp_path))[0]["problems"] == []


def test_missing_reference_file_is_reported(tmp_path):
    """正文引用的 `references/xxx.md` 必须真的存在。

    渐进披露靠引用分流；路径写错时宿主不会报错，只会读到一个空引用——
    技能看起来还在，实际少了一半内容。
    """
    body = GOOD.format(name="jwb-demo").replace(
        "# 标题", "# 标题\n\n细节见 `references/details.md`。")
    _make(tmp_path, "jwb-demo", body=body)

    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("references/details.md" in p for p in problems), problems


def test_existing_reference_file_passes(tmp_path):
    body = GOOD.format(name="jwb-demo").replace(
        "# 标题", "# 标题\n\n细节见 `references/details.md`。")
    d = _make(tmp_path, "jwb-demo", body=body)
    (d / "references").mkdir()
    (d / "references" / "details.md").write_text("# 细节\n", encoding="utf-8")

    assert inspect_skills(str(tmp_path))[0]["problems"] == []


def test_overlong_skill_body_is_reported(tmp_path):
    """主文件超过行数上限 → 提示拆到 references/（渐进披露第二级）。"""
    body = GOOD.format(name="jwb-demo") + "\n".join(
        "第 %d 行" % i for i in range(600))
    _make(tmp_path, "jwb-demo", body=body)

    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("行" in p and "references/" in p for p in problems), problems


def test_reference_file_with_repo_path_is_reported(tmp_path):
    """`references/` 下的文件随技能一起分发，仓库相对路径禁令同样适用（批 10 审查 MAJOR-4）。

    只查 SKILL.md 的话，「把长内容搬进 references/」恰好绕过了规则——而它的死路径
    后果与主文件里写死路径完全一样。
    """
    body = GOOD.format(name="jwb-demo").replace(
        "# 标题", "# 标题\n\n见 `references/details.md`。")
    d = _make(tmp_path, "jwb-demo", body=body)
    (d / "references").mkdir()
    (d / "references" / "details.md").write_text(
        "# 细节\n\n跑 `python tools/jobws.py track list`。\n", encoding="utf-8")

    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("references/details.md" in p and "仓库相对路径" in p for p in problems), problems


def test_indented_field_outside_metadata_is_reported(tmp_path):
    """缩进只允许出现在 `metadata:` 之下（批 10 审查 MINOR-4）。

    误缩进的 `licence:` 若被当成「嵌套键」放过，白名单就形同虚设；而误缩进的
    `license:` 在严格 YAML 宿主里会变成上一个字段的子键，两边判定不一致。
    """
    _make(tmp_path, "jwb-x", body=(
        "---\nname: jwb-x\ndescription: x\ncompatibility: ok\n"
        "  licence: MIT\n---\n\n正文。\n"))
    problems = inspect_skills(str(tmp_path))[0]["problems"]
    assert any("缩进" in p for p in problems), problems


def test_version_must_match_app_version(tmp_path):
    """技能 metadata.version 与插件壳 version 必须等于应用版本（批 10 审查 MAJOR-1）。"""
    skills_root = tmp_path / "skills"
    d = skills_root / "jwb-x"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: jwb-x\ndescription: x\ncompatibility: ok\n"
        "metadata:\n  version: 1.0.0\n---\n\n正文。\n", encoding="utf-8")
    electron = tmp_path / "web" / "electron"
    electron.mkdir(parents=True)
    (electron / "package.json").write_text('{"version": "26.9.15"}\n', encoding="utf-8")
    plugin_dir = tmp_path / ".codebuddy-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"version": "26.9.15"}\n', encoding="utf-8")

    problems = version_problems(str(tmp_path), str(skills_root))

    assert any("metadata.version=1.0.0" in p for p in problems), problems


def test_version_check_skips_without_app_package(tmp_path):
    """没有 `web/electron/package.json`（独立使用校验器的场景）→ 跳过，不误报。"""
    skills_root = tmp_path / "skills"
    (skills_root / "jwb-x").mkdir(parents=True)
    assert version_problems(str(tmp_path), str(skills_root)) == []


def test_repo_skills_are_compliant():
    """真实 skills/ 必须合规。

    合成目录全绿、真仓库却红，是这类测试最大的盲区：贡献者把目录改名却忘了
    改 frontmatter 的 name，本地一片绿，只有推到 CI 才红。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(os.path.dirname(here), "skills")
    results = inspect_skills(root)
    assert results, "skills/ 下应当有技能目录"
    assert all(r["problems"] == [] for r in results), describe(results)
