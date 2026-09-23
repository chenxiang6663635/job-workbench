# -*- coding: utf-8 -*-
"""技能校验的规则层（批 10 自 check_skills.py 拆出：那里是水位文件，只许变小）。

两条纪律：

1. **规则只写一处**：`check_skills` 仍是唯一入口（CI、分发脚本、本地自查都调它），
   本模块只把「检查什么」与「怎么遍历目录」分开，并由 check_skills 原样再导出；
2. **纯函数**：入参是文本与路径，不读环境、不写文件——规则可以用合成目录直接测
   （见 `tests/test_check_skills.py`）。
"""

import os
import re

DESC_MAX = 300
REQUIRED = ["name", "description", "compatibility"]

# 允许出现的 frontmatter 顶层字段（对齐 Open Agent Skills 规范）。
# 为什么要有白名单：`licence`、`allowed_tools` 这类手滑**不会让宿主报错**——
# 它只是静默失效（元数据没生效，而本地全绿）。规范字段集：
# name / description 必需；compatibility / license / metadata / allowed-tools 可选。
ALLOWED_FIELDS = {"name", "description", "compatibility", "license", "metadata",
                  "allowed-tools"}

# 主文件行数上限（渐进披露第二级：元数据 → 主文件 → references/ 按需）。
# 规范建议 500 行，我们取同一条线：超过就该把重参考资料拆到 references/。
BODY_MAX_LINES = 500

# 正文里引用的参考资料相对路径（`references/xxx.md`，相对技能根）。
REFERENCE_RE = re.compile(r"references/[A-Za-z0-9][A-Za-z0-9._\-/]*")

# 本仓库技能的命名空间。用户级 ~/.agents/skills/ 是与别人共用的同一个目录，
# 通用名（apply / resume / track …）撞车概率高，而撞车的结果是**静默覆盖**。
NAME_RE = re.compile(r"^jwb-[a-z0-9]+(-[a-z0-9]+)*$")

# 正文里禁止出现的仓库顶层目录（技能分发到宿主后，工作目录是用户自己的工作区，
# 这些前缀在那里都不存在）。新增顶层目录时记得加进来——漏了不会报错，只会让
# 技能把宿主引到死路径上。
REPO_PATH_PREFIXES = ("tools/", "web/", "template/", "skills/", "tests/")


def frontmatter_problems(text, frontmatter_end, fields, entry):
    """frontmatter 的字段级问题清单（白名单、name、description）。

    `entry` 是技能目录名（name 必须与它一致）；`frontmatter_end` 是 0 基结束行号。
    """
    problems = []

    # 字段白名单：缩进行属于上一个字段的嵌套映射（如 `metadata:` 下的 `version`），
    # 不算顶层键，故按行首空白跳过。
    for line in text.splitlines()[1:frontmatter_end]:
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        if ":" not in line:
            continue
        key = line.partition(":")[0].strip()
        if key not in ALLOWED_FIELDS:
            problems.append(
                "frontmatter 字段 `%s` 未登记（规范字段集：%s）——拼错的键不会让宿主"
                "报错，只会静默失效（元数据没生效而本地全绿）"
                % (key, "、".join(sorted(ALLOWED_FIELDS))))

    name = fields.get("name")
    if not name:
        problems.append("frontmatter 缺 name")
    else:
        if name != entry:
            problems.append(
                "name 与目录名不一致：name=%s，目录=%s（技能身份要求两者相同）"
                % (name, entry))
        if not NAME_RE.match(name):
            problems.append(
                "name 必须带 jwb- 前缀（当前：%s）——通用名装到用户级目录时会"
                "与别人已装的同名技能冲突，宿主**静默覆盖**" % name)

    for key in REQUIRED:
        if key != "name" and not fields.get(key):
            problems.append("frontmatter 缺 %s" % key)

    desc = fields.get("description")
    if desc in ("|", ">"):
        # 本解析器只认单行值；块标量会被读成 "|" 从而绕过长度校验
        problems.append(
            "frontmatter 不支持块标量写法（description: %s），请改成单行" % desc)
    elif desc and len(desc) > DESC_MAX:
        problems.append(
            "description 过长（%d 字符，上限 %d）" % (len(desc), DESC_MAX))
    elif desc and ": " in desc:
        # 半角冒号+空格在严格 YAML 宿主下是语法错误：Codex 实测会拒绝整个技能
        problems.append(
            "description 含 `: `（半角冒号+空格）：严格 YAML 宿主（如 Codex）"
            "会因此拒绝加载整个技能；改用全角冒号 `：` 或改写表述")
    return problems


def body_problems(text, frontmatter_end, skill_dir):
    """正文（frontmatter 之后）的问题清单：仓库路径、references 可达、行数上限。"""
    problems = []
    body_lines = text.splitlines()[frontmatter_end + 1:]

    # 仓库相对路径：技能分发到宿主后，工作目录是用户自己的工作区，这些路径都不存在。
    # 只报第一处——修完再跑一次就知道后面还有没有；一次列一串反而没人看。
    for offset, line in enumerate(body_lines):
        hit = next((prefix for prefix in REPO_PATH_PREFIXES if prefix in line), None)
        if hit:
            problems.append(
                "第 %d 行（文件行号，含 frontmatter）引用了仓库相对路径 `%s…`："
                "%s——技能会被分发到宿主，那时的工作目录是用户自己的工作区，"
                "仓库路径在那里不存在；命令名写 `jobws`，路径说明放 frontmatter "
                "的 compatibility"
                % (frontmatter_end + 2 + offset, hit, line.strip()))
            break

    # 参考资料可达性：正文引用的 `references/xxx.md` 必须真的存在——渐进披露靠引用
    # 分流，路径写错时宿主不报错，技能看起来还在、实际少了一半内容。
    for offset, line in enumerate(body_lines):
        for ref in REFERENCE_RE.findall(line):
            if not os.path.isfile(os.path.join(skill_dir, ref)):
                problems.append(
                    "第 %d 行引用了不存在的 `%s`（相对技能根）；渐进披露靠引用分流，"
                    "路径写错时不会有任何提示"
                    % (frontmatter_end + 2 + offset, ref))
                break

    if len(body_lines) > BODY_MAX_LINES:
        problems.append(
            "正文 %d 行，超过 %d 行上限——把重参考资料拆到 `references/`（按需读取）"
            % (len(body_lines), BODY_MAX_LINES))
    return problems
