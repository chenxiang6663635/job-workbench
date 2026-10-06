# -*- coding: utf-8 -*-
"""Release 说明的结构化排版：直链下载置顶 + 不重复版本标题 + 长内容折叠/外包。

为什么独立成模块：`release_assist.py` 负责「抽段 + 预检」（受规模水位线约束），
结构化排版是发布页的**呈现**职责——单独一块，改动与测试都只针对它
（tests/test_release_notes_structure.py）。

演进：
- 2026-09-27 首版（外部审计第三轮）：「拉到后面才看到下载文件」——Assets 区在
  描述流之后，描述越长下载入口被推得越深 → 引导置顶。
- 2026-10-06 重构（用户实测「字体这么大、要滚很久」+ 11 个成熟项目调研：
  VS Code / Electron / Vite / pnpm / Deno / Bun / Bitwarden / Obsidian / Godot /
  mkdocs-material / Tailwind）：
  1. **正文不重复版本号大标题**——页面标题已显示 tag，11/11 项目都不重复；
     `##` 渲染 1.5em 粗体，是「字体大」观感的主要来源。
  2. **首行 = 安装包直链 + 校验和直链**（Bun 的「第一屏即安装」形态）——旧版只有
     指引文字（「在本页下方 Assets 区」），用户仍要滚到底。
  3. **English Highlights 整节折叠**（双语受众，但页面不翻倍）；技术细节维持折叠；
     长内容原则上外包（compare / CHANGELOG 链接），不粘贴。
  4. 全文只用一层 `###` 小节标题：段内 `##` 一律降级。
"""

_REPO = "chenxiang6663635/job-workbench"
_ASSET_NAME = "job-workbench-setup-{version}-win64.exe"


def _download_url(version, name):
    """发布资产直链。文件名带版本号，所以不能用 `latest/download` 通配——
    发布后该 URL 恒定，可以直接写进说明。"""
    return "https://github.com/%s/releases/download/v%s/%s" % (_REPO, version, name)


def structure_notes(notes, version):
    """把抽出的 CHANGELOG 段重排成发布页友好的结构。

    三条规则（2026-10-06，依据见模块头注）：
    1. 首行 = 安装包与校验和的**直链**——0 秒层；不放「请前往 Assets」式指引。
    2. 正文不重复版本号大标题；段内 `##` 一律降为 `###`（全文只一层小节标题）。
    3. `### Highlights (English)` 与 `### 技术细节` 整节折叠进 <details>；
       中文「看得见的变化」是可见主体。段里没有这两节时折叠是空操作。

    空输入原样返回（纯函数契约；调用方由 find_section 保证非空，防御直调）。
    """
    if not notes.strip():
        return notes
    lines = notes.splitlines()
    # 页面标题已显示 tag——正文不重复版本号大标题（调研：11/11 项目均不重复）
    body = lines[1:] if lines and lines[0].startswith("## [") else lines

    asset = _ASSET_NAME.format(version=version)
    out = [
        "⬇️ **下载 Windows 安装包**：[%s](%s)（Windows x64，免 Python / Node 环境）"
        % (asset, _download_url(version, asset)),
        "🔑 完整性：下载后对照 [SHA256SUMS.txt](%s)；`latest.yml`（自动更新）与"
        " `.blockmap`（增量更新）在下方 Assets。" % _download_url(version, "SHA256SUMS.txt"),
        "",
    ]

    fold_head = None  # 当前打开的折叠区标题；None = 没有打开
    for line in body:
        is_h3 = line.startswith("### ")
        starts_fold = is_h3 and (
            line == "### Highlights (English)" or line.startswith("### 技术细节"))
        if fold_head and is_h3 and not starts_fold:
            # 回到同级小节：先闭合再继续（防御未来在折叠区后追加小节）
            out.extend(["", "</details>", ""])
            fold_head = None
        if starts_fold:
            if fold_head:
                out.extend(["", "</details>", ""])  # 防御：折叠区不相邻时先闭合
            fold_head = line
            summary = ("English Highlights"
                       if "Highlights" in line
                       else "技术细节（内部工程 · 依赖 · 逐项变更记录）")
            out.extend(["<details>", "<summary><b>%s</b></summary>" % summary, "", line])
            continue
        # CHANGELOG 段内的小节标题降级：## → ###（正文只留一层小节标题；
        # 段头 `## [版本]` 已在上方摘除，这里再排除一次属防御）
        if line.startswith("## ") and not line.startswith("## ["):
            line = "#" + line
        out.append(line)
    if fold_head:
        out.extend(["", "</details>"])
    return "\n".join(out)
