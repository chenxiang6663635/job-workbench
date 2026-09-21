# -*- coding: utf-8 -*-
"""笔记：`03_面试准备/` 与 `04_知识库/` 的只读浏览（目录列表 + 内容读取）。

工作区语义里这两层是「训练材料」——03 放表达（自我介绍 / 项目表达 / 行为面），
04 放知识（速查卡 / 面试速记），见各自 README。Web 侧以"读"为主：Markdown 由
用户在编辑器 / Obsidian 里写，界面负责"看得舒服"；2026-09-18 起多了勾选框翻转的
**预览签发**（`preview-toggle`）——真正的落盘走既有的 `/api/approvals/apply`
（写通道只有一条；领域逻辑在 `tools/prep_notes.py`）。

两条硬约束（都有先例）：
1. **目录写死常量**（`deps.DIR_PREP` / `deps.DIR_KB`），不接受任何形式的目录参数
   —— `progress/questions.py:111-114` 记录过一次真实漏洞：曾把目录做成查询参数，
   `os.path.join` 遇绝对路径会丢掉工作区，一个绝对路径参数就能让服务端去扫任意
   目录并把正文回进响应。
2. **读路径三层防护**：`safe_join`（拦 `..` 与绝对路径）→ realpath 二次确认
   （`safe_join` 不解析符号链接，Windows 上 junction 仍能读穿，对齐 MCP 侧
   `resources.py` 的强度）→ 扩展名白名单。

遍历 / 读取 / 解码与 realpath 判断 2026-09-18 收敛到共享模块 `ro_files.py`
（与素材库同源；此前两处实现重复度约 85%）。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from apierror import ApiError
from deps import DIR_KB, DIR_PREP, safe_join, workspace_dir
from ro_files import TextDecodeError, inside, read_text_limited, walk_files

router = APIRouter(prefix="/api/prep")

# section 白名单：只认这两层，映射到写死的目录常量（"interview"/"knowledge"
# 即前端契约，与本模块同源）
SECTION_DIRS = {"interview": DIR_PREP, "knowledge": DIR_KB}

# 只列 / 只读 .md：这两个目录的约定就是 Markdown（模板、README 都是 .md）。
# 其他文件（图片等）不在"笔记浏览"的语义内——是设计决策而非错误，列表里不出现。
TEXT_EXT = {".md"}


def _resolve_section(section):
    """section 白名单 → 写死的目录常量（不认识就 404，不猜也不拼路径）。"""
    base_rel = SECTION_DIRS.get(section)
    if base_rel is None:
        raise ApiError(404, "prep.unknownSection", "未知笔记分类: %s" % section,
                       section=section)
    return base_rel


def _section_base(ws, base_rel):
    """section 根目录 = safe_join + realpath 归属检查（锚点=**工作区根**）：
    section 目录本身被替换成指向外部的链接时整体拒绝——与 MCP 侧同款
    （独立审查 MINOR-2；目录树**内**的 junction 另由 `inside(base, full)` 兜住）。"""
    base = safe_join(ws, base_rel)
    if not inside(ws, base):
        raise ApiError(400, "path.escape", "路径越出工作区")
    return base


# 搜索返回条数的展示上限：命中总数照常**全量统计**（`total` 是真实值），只截断
# 返回列表——两者分开上报，前端才能说清"另有 N 条"（看板待推进块同款口径）。
SEARCH_MAX_HITS = 50


def _search_section(ws, section, keyword):
    """扫一个 section 的全部 .md，返回 (hits, skipped)。

    三条纪律（都有对应的反例）：
    1. 遍历用共享原语 `walk_files`——与列表 / 目录树同源的跳过规则与排序，
       搜得到的东西必须和界面上看得见、点得开的东西一致（README 与 `_模板_`
       照常参与：树里能开就能搜到）。
    2. **逐文件 `inside()`**：`walk_files` 自己不查归属，而 `os.walk` 不跟随
       **目录**链接、却会把**文件**链接当成普通文件——不查就会把工作区外的正文
       回进响应。列表端点只查"被点开的那个"，搜索是批量，这层不能省。
    3. 读不动的文件进 `skipped`**不静默丢**：单文件不该让整次搜索失败，
       但也不能让人以为"没有这个词"。
    """
    base_rel = SECTION_DIRS[section]
    base = _section_base(ws, base_rel)
    hits = []
    total = 0
    skipped = []
    try:
        entries = walk_files(base, exts=TEXT_EXT)
    except OSError as exc:
        # 遍历期失败（目录被外部换掉 / 权限 / 保存竞态）也不该让整次搜索 500——
        # 那会让**全部**结果消失，正是本端点承诺要防的"静默少给"的极端形态。
        skipped.append({"rel": base_rel, "reason": "目录读不到（%s）" % exc})
        return hits, total, skipped
    for item in entries:
        rel = item["rel"]
        full = os.path.join(base, *rel.split("/"))
        if not inside(base, full):
            skipped.append({"rel": rel, "reason": "路径越出工作区"})
            continue
        name = rel.rsplit("/", 1)[-1]
        # 与左树的过滤同口径：**整条 rel** 参与匹配（目录名也算）
        in_name = keyword in rel.lower()
        try:
            text, truncated, _size = read_text_limited(full)
        except TextDecodeError:
            skipped.append({"rel": rel, "reason": "不是 UTF-8 编码的文本"})
            continue
        except OSError as exc:
            skipped.append({"rel": rel, "reason": "读不到（%s）" % exc})
            continue
        if truncated:
            skipped.append({"rel": rel, "reason": "文件超过 256 KB，只搜了前 256 KB"})
        lines = text.split("\n")
        # 整篇一次 lower（比逐行 lower 省）；命中取**原文**行的文本展示
        lowered = text.lower().split("\n")
        file_hit = False
        for offset, low in enumerate(lowered, start=1):
            if keyword not in low:
                continue
            file_hit = True
            total += 1
            # 只攒展示用的前 N 条：命中再多也不必把几万条 dict 留在内存里，
            # 而 total 照常全量计数（两者分开正是"诚实截断"的本意）
            if len(hits) < SEARCH_MAX_HITS:
                hits.append({"section": section, "rel": rel, "name": name,
                             "line": offset,
                             "text": lines[offset - 1].rstrip("\r").strip(),
                             "inName": in_name})
        # 名字（文件名 / 目录名）命中而正文没有：也给一条，否则"名字里明明有"
        # 却搜不到——那正是最像 bug 的一种静默少给。
        if in_name and not file_hit:
            total += 1
            if len(hits) < SEARCH_MAX_HITS:
                hits.append({"section": section, "rel": rel, "name": name,
                             "line": 1, "text": "", "inName": True})
    return hits, total, skipped


@router.get("/search")
def search_prep(q: str = "", ws: str = Depends(workspace_dir)):
    """全文搜索：在两个目录的 .md 里按关键词搜**文件名 + 正文**（**不落盘**）。

    口径（写死，前端据此显示）：
    - 匹配：关键词 `strip().lower()` 后做**子串**匹配（与题库 / 投递列表同款）；
      **不做分词**——中文没有空格，分词会把「缓存 雪崩」拆成两个词，而用户
      以为自己在搜一个短语；
    - 一条命中 = 一行（同文件多行命中就是多条）；文件名命中而正文无命中时，
      给一条 `line=1` 的条目；
    - `total` 是**真实命中总数**（全量统计，不是返回条数），`items` 最多
      `SEARCH_MAX_HITS` 条，截断时 `truncated=true`；
    - `skipped` 列出没搜全的文件（读不动 / 非 UTF-8 / 超 256 KB 只搜了前半）。

    **本端点必须排在 `/{section}` 之前**：FastAPI 按注册顺序匹配，否则
    `/api/prep/search` 里的 "search" 会被当成 section 名 → 404
    `prep.unknownSection`（有测试钉住这条）。
    """
    keyword = (q or "").strip().lower()
    if not keyword:
        # 空关键词不是错误——返回空结果（省一个错误码，也让前端不必分支）
        return {"keyword": "", "items": [], "total": 0, "truncated": False,
                "skipped": []}
    hits = []
    total = 0
    skipped = []
    for section in ("interview", "knowledge"):
        section_hits, section_total, section_skipped = _search_section(
            ws, section, keyword)
        hits.extend(section_hits)
        total += section_total
        skipped.extend(section_skipped)
    return {"keyword": (q or "").strip(), "items": hits, "total": total,
            "truncated": total > len(hits), "skipped": skipped}


@router.get("/{section}")
def list_prep(section: str, ws: str = Depends(workspace_dir)):
    """列出该层的全部 Markdown（**平铺**，rel 带子目录路径；树由前端建）。

    服务端 `rel` 字典序是**唯一排序口径**，前端不再排一次；空目录天然不出现在
    平铺结果里（目录结构由 rel 的路径段还原，空目录因此自动隐藏）；0 字节文件
    照常列出（前端显示"空"标记——文件不能静默消失）。
    """
    base_rel = _resolve_section(section)
    base = _section_base(ws, base_rel)
    items = walk_files(base, exts=TEXT_EXT)
    return {"section": section, "items": items, "total": len(items)}


@router.get("/{section}/content")
def prep_content(section: str, rel: str, ws: str = Depends(workspace_dir)):
    """读取一篇笔记的正文（**不落盘**；写通道不在本模块）。

    文件不存在 / 非 md / 读不动分别给明确错误码——少给比报错更危险。
    超 256KB 截断：`bytes` 报**文件真实总字节**（不是返回内容长度），
    `truncated` 供前端显式提示"仅显示前 256KB"。
    """
    base_rel = _resolve_section(section)
    base = _section_base(ws, base_rel)
    full = safe_join(ws, base_rel, rel)
    if not inside(base, full):
        # 参数与 deps.safe_join 的同码抛点保持一致（无 params——该码文案无占位符）
        raise ApiError(400, "path.escape", "路径越出工作区")
    if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
        raise ApiError(400, "prep.notMarkdown", "只支持 .md 文件: %s" % rel, rel=rel)
    if not os.path.isfile(full):
        raise ApiError(404, "prep.fileNotFound", "文件不存在: %s" % rel, rel=rel)
    try:
        text, truncated, size = read_text_limited(full)
    except TextDecodeError:
        raise ApiError(500, "prep.readFailed", "不是 UTF-8 编码的文本文件: %s" % rel,
                       rel=rel)
    except OSError as exc:
        raise ApiError(500, "prep.readFailed", "文件读取失败: %s（%s）" % (rel, exc),
                       rel=rel)
    return {"rel": rel, "content": text, "truncated": truncated, "bytes": size}


@router.get("/{section}/preview-toggle")
def preview_toggle(section: str, rel: str = "", line: int = 0,
                   ws: str = Depends(workspace_dir)):
    """预览翻转某一行的勾选框（**不落盘**），返回令牌与「原行 → 新行」差异。

    与题库改题（`/api/progress/questions/preview-update`）同构：只签发一次性
    令牌，落盘走既有的 `/api/approvals/apply`（写通道只有一条）。section/rel/
    line 的完整校验与读写都在领域层 `prep_notes`（白名单、realpath 防护、
    字节级翻转），本端点不重复实现——没有第二份校验就没有失配的机会。
    """
    import prep_toggle
    errors, plan = prep_toggle.preview_toggle(ws, section, rel, line)
    if plan is None:
        # 结构化错误（2026-09-21 批次 C-5）：code 走 err.<code> 的语言包（中英各自
        # 成句），message 只是中文兜底（未知 code 时前端回落 detail）——不再出现
        # "英文前缀 + 中文原因"。params 的键与语言包占位名同名。
        code, params, message = errors[0]
        raise ApiError(400, code, message, **params)
    from jobws_core import approval  # 函数内 import：approval 只在写路径用到，保持顶层最小
    result = approval.preview("prep.toggle", ws, plan["payload"], plan["summary"],
                              plan["diff"], plan["targets"])
    return {"token": result["token"], "summary": plan["summary"],
            "diff": plan["diff"], "expiresAt": result["expires_at"]}
