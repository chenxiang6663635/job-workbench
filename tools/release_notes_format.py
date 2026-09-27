# -*- coding: utf-8 -*-
"""Release 说明的结构化排版：下载引导置顶 + 技术细节折叠。

为什么独立成模块：`release_assist.py` 负责「抽段 + 预检」（受规模水位线约束），
结构化排版是发布页的**呈现**职责——单独一块，改动与测试都只针对它
（tests/test_release_notes_structure.py）。2026-09-27，外部审计第三轮：
「拉到后面才看到下载文件」——Assets 区在描述流之后，描述越长下载入口被推得越深。

发布语义（配套，#226）：先完整、再公开（draft→上传→核验→publish）、
公开即不可变——发布页与制品的呈现规则成对演进。
"""

# 发布页下载引导：Assets 区在描述流之后，描述越长下载入口被推得越深——
# 引导放最前，首屏可见。
_ASSET_NAME = "job-workbench-setup-{version}-win64.exe"


def structure_notes(notes, version):
    """把抽出的 CHANGELOG 段重排成发布页友好的结构。

    两个动作：
    1. 段头之后插入「下载」引导块——Assets 区在发布页描述流之后，描述越长
       下载入口被推得越深；引导放最前，首屏可见。
    2. 「### 技术细节」及其全部子小节折叠进 <details>——发布页默认视图只留
       Highlights 与看得见的变化，内部工程记录点开再看。

    其余小节（Highlights (English) / 看得见的变化）保持原样——它们就是页面
    的主体；段里没有「### 技术细节」时（如极小版本），折叠是空操作。
    """
    lines = notes.splitlines()
    head, rest = lines[0], lines[1:]

    download = [
        "## 下载（Windows 安装包）",
        "",
        "**`%s`** —— 在本页下方 **Assets** 区（点 Show all 展开）。"
        % _ASSET_NAME.format(version=version),
        "附：`latest.yml`（自动更新元数据）· `SHA256SUMS.txt`（完整性核对）· "
        "`.blockmap`（增量更新）。",
        "",
    ]

    out = [head, ""]
    out.extend(download)
    folding = False
    for line in rest:
        if not folding and line.startswith("### 技术细节"):
            folding = True
            out.append("<details>")
            out.append("<summary><b>技术细节（内部工程 / 依赖与构建）</b></summary>")
            out.append("")
            out.append(line)
            continue
        if folding and (line.startswith("### ") or line.startswith("## ")):
            # 技术细节结束、回到同级小节（当前两级制下不会发生，防御未来结构变化）
            out.append("")
            out.append("</details>")
            out.append("")
            folding = False
        out.append(line)
    if folding:
        out.append("")
        out.append("</details>")
    return "\n".join(out)
