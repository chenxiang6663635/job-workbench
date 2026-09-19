# -*- coding: utf-8 -*-
"""笔记勾选框写回：`03_面试准备/` 与 `04_知识库/` 里 `- [ ]` ↔ `- [x]` 的翻转。

背景：Web「准备 · 笔记」页（`web/backend/routers/prep.py`）只读浏览这两个目录，
本模块补上唯一的"写"——把某一行的勾选状态翻转（"打勾即学习打卡"）。两段式照
题库改题同构：`preview_toggle` 只读不落盘，`apply_approved_toggle` 在锁内重校验
后写回；落盘通道只有 `/api/approvals/apply` 一条（不在本模块开写端点）。

三条纪律（每条都有代价近似的替代方案，选它们的理由如下）：

1. **字节级单点翻转**：以 bytes 读、`\\n` 切行、只替换任务标记括号里的那 1 个
   字符、`atomic_write_bytes` 写回——BOM / CRLF / 行尾空白 / 其余行逐字节保留。
   文本方案在 BOM 与 CRLF 上都要额外纪律（`atomic_write_text` 默认无 BOM，
   会把 utf-8-sig 文件写出 BOM 变化），字节方案天然无此问题。
2. **行内容双校验**：载荷里存预览时该行原文（expected），apply 时在锁内重读
   比对——外部编辑器（Obsidian 等不拿我们的锁）改过就拒绝并要求重新预览。
   只认行首**第一个**任务标记，行内其它 `[ ]` 字样绝不触碰。
3. **写路径不截断**：只读端点的 256KB 截断是展示语义；写回必须全文读写
   （截断 + 写回 = 后半文件丢失）。超过 MAX_BYTES 的文件在预览期直接拒绝。

section → 目录的映射（SECTION_DIRS）与 web 层 `deps.DIR_PREP/DIR_KB`、
`routers/prep.py` 的 `SECTION_DIRS` 是同源字面量，三处改名要同步——
`tests/test_prep_toggle.py` 有一条「领域层与 web 层映射一致」的钉住用例。
"""

import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import tracker  # noqa: E402  （复用工作区解析、file_lock 与 ConflictError；
# file_lock 经 tracker 包门面的 PEP 562 转发取得——不再引旧名 filelock）
from jobws_core import workspace_io  # noqa: E402

# section 白名单：与 web 层同源（见模块 docstring）
SECTION_DIRS = {"interview": "03_面试准备", "knowledge": "04_知识库"}

# 只翻转 .md：这两个目录的约定就是 Markdown（与只读端点 TEXT_EXT 同口径）
TEXT_EXT = ".md"

# 单文件大小上限：正常笔记远小于此；超限拒绝而不是截断读写（纪律 3）。
MAX_BYTES = 2 * 1024 * 1024

# 任务标记：行首（允许缩进）+ 列表标记（- * + 或 1. 1)）+ 空白 + `[` 状态 `]`。
# 状态字符：空格 / tab（未勾选）与 x / X（已勾选）——GFM 任务列表的语法面；
# 结尾前瞻 `[ \t]|\r?$` 对齐 GFM 的"标记后须为空白或行尾"（`\r?$` 兼容 CRLF
# 文件按 `\n` 切行后行尾残留的 `\r`）。`^` 锚定行首使「- 文本 [ ]」这类行内
# 出现不匹配（那不是任务项，不该翻转）。
_TASK_RE = re.compile(
    r"^([ \t]*(?:[-*+]|\d+[.)])[ \t]+\[)([ \t xX])(\])(?=[ \t]|\r?$)")


def _lock_path(workspace=None):
    """笔记写回的互斥锁：<工作区>/config/prep.lock。

    一把锁覆盖 03/04（两目录同属"笔记"写语义；跨目录互斥的代价可忽略，
    少一把锁少一个命名）。锁名从 `workspace_io` 的锁名表取（唯一真值源）；
    **落在 config**（与 imap / provider 同款）——锁与写入目标解耦，写
    `04_知识库` 时不会凭空建出 `03_面试准备` 目录。建目录刻意留在锁外——
    makedirs 幂等，与 tracker._lock_path 同款纪律。
    """
    ws = tracker.resolve_ws(workspace)
    path = workspace_io.lock_path(ws, "prep")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _target_path(ws, section, rel):
    """rel → 绝对路径。领域层自建一份防护（不能 import web 层）：

    - section 白名单（不认识不猜也不拼路径）；
    - 拒绝对路径 / 盘符开头（`os.path.join` 遇盘符会丢掉前段工作区）；
    - `\\` 归一成 `/` 后切段，拒 `..` / `.` / 空段；
    - 扩展名白名单；
    - realpath 二次确认：锚点先工作区根、再 section 目录——前缀式校验不解析
      符号链接，Windows junction 仍能读穿（对齐 MCP 侧强度）。

    返回 (full, norm_rel, error)；出错时前两项为 None。
    """
    base_rel = SECTION_DIRS.get(section)
    if base_rel is None:
        return None, None, "未知笔记分类：%s" % section
    norm_rel = (rel or "").strip().replace("\\", "/")
    if not norm_rel:
        return None, None, "缺少文件路径"
    parts = norm_rel.split("/")
    if norm_rel.startswith("/") or ":" in parts[0]:
        return None, None, "路径必须是工作区内的相对路径：%s" % norm_rel
    if any(part in ("", ".", "..") for part in parts):
        return None, None, "路径不合法：%s" % norm_rel
    if os.path.splitext(parts[-1])[1].lower() != TEXT_EXT:
        return None, None, "只支持 .md 文件：%s" % norm_rel
    base = os.path.join(ws, base_rel)
    full = os.path.join(base, *parts)
    ws_real = os.path.realpath(ws)
    base_real = os.path.realpath(base)
    full_real = os.path.realpath(full)
    if not base_real.startswith(ws_real + os.sep):
        return None, None, "路径越出工作区"
    if not full_real.startswith(base_real + os.sep):
        return None, None, "路径越出工作区"
    return full, norm_rel, None


def _read_lines(full, norm_rel):
    """读全文并按 `\\n` 切行（bytes）。写路径不截断——超限直接拒绝（纪律 3）。"""
    try:
        size = os.path.getsize(full)
    except OSError as exc:
        return None, "文件读不到：%s（%s）" % (norm_rel, exc)
    if size > MAX_BYTES:
        return None, "文件超过 %d KB，为免截断写坏已拒（请直接在编辑器里改）：%s" % (
            MAX_BYTES // 1024, norm_rel)
    try:
        with open(full, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        return None, "文件读不到：%s（%s）" % (norm_rel, exc)
    return data.split(b"\n"), None


def _decode_line(line_bytes, norm_rel, line):
    """目标行 bytes → str。只解码**目标行**：其余行即使有坏字节也不影响
    （字节级写回逐字保留），只有目标行本身要求是合法 UTF-8。"""
    try:
        return line_bytes.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "第 %d 行不是合法 UTF-8，无法翻转：%s" % (line, norm_rel)


def _flip(text):
    """翻转一行的任务标记。返回 (new_text, old_mark, new_mark)；非任务行全 None。

    预览与落盘共用这一处——两处各写一份正是「预览说翻这行、落盘多动一行」的温床。
    """
    match = _TASK_RE.match(text)
    if match is None:
        return None, None, None
    old = match.group(2)
    new = " " if old in ("x", "X") else "x"
    return match.group(1) + new + match.group(3) + text[match.end():], old, new


def _mark_name(mark):
    return "已勾选" if mark in ("x", "X") else "未勾选"


def preview_toggle(workspace, section, rel, line):
    """预览翻转某一行勾选框（**不落盘**），返回 (errors, plan)。

    校验都在预览期做完并给出**具体原因**（哪行、为什么不行）——预览是
    "将要落什么"的承诺，含糊失败比明确报错更贵。
    """
    ws = tracker.resolve_ws(workspace)
    if not isinstance(line, int) or line < 1:
        return ["缺少行号（需要被点勾选框所在行在 Markdown 源码里的行号，从 1 起）"], None
    full, norm_rel, error = _target_path(ws, section, rel)
    if error:
        return [error], None
    if not os.path.isfile(full):
        return ["文件不存在：%s" % norm_rel], None
    lines, error = _read_lines(full, norm_rel)
    if error:
        return [error], None
    if line > len(lines):
        return ["行号 %d 超出文件总行数 %d：%s" % (line, len(lines), norm_rel)], None
    text, error = _decode_line(lines[line - 1], norm_rel, line)
    if error:
        return [error], None
    new_text, old, new = _flip(text)
    if new_text is None:
        return ["第 %d 行不是勾选框行（`- [ ]` 形态），无法翻转：%s"
                % (line, norm_rel)], None
    payload = {"section": section, "rel": norm_rel, "line": line, "expected": text}
    diff = ["%s（第 %d 行）" % (norm_rel, line),
            "- " + text.rstrip("\r"), "+ " + new_text.rstrip("\r")]
    summary = "翻转勾选框：%s 第 %d 行（%s → %s）" % (
        norm_rel, line, _mark_name(old), _mark_name(new))
    return [], {"payload": payload, "summary": summary, "diff": diff,
                "targets": [full]}


def apply_approved_toggle(payload, workspace=None):
    """两段式第二步：按已确认的载荷翻转勾选框（锁内读最新 → 重校验 → 写）。

    重校验比预览多一层意义：从预览到确认之间文件可能被任何编辑器改过
    （Obsidian 等外部程序不拿我们的锁），所以锁**只**保证本仓进程互斥，
    真正兜底的是「行号 + 行内容」双条件——任一不符就拒绝并请用户重新预览。
    """
    ws = tracker.resolve_ws(workspace)
    section = (payload.get("section") or "").strip()
    rel = (payload.get("rel") or "").strip()
    line = payload.get("line")
    expected = payload.get("expected")
    full, norm_rel, error = _target_path(ws, section, rel)
    if error:
        raise tracker.ConflictError("预览之后目标已不可用（%s），请重新预览" % error)
    with tracker.file_lock(_lock_path(ws)):
        if not os.path.isfile(full):
            raise tracker.ConflictError("预览之后文件不存在了（请重新预览）")
        lines, error = _read_lines(full, norm_rel)
        if error:
            raise tracker.ConflictError("预览之后文件不可读（%s），请重新预览" % error)
        if not isinstance(line, int) or line < 1 or line > len(lines):
            raise tracker.ConflictError("预览之后文件行数变了（请重新预览）")
        text, error = _decode_line(lines[line - 1], norm_rel, line)
        if error:
            raise tracker.ConflictError("预览之后目标行不可解码（请重新预览）")
        if text != expected:
            raise tracker.ConflictError(
                "预览之后这一行被改过（可能是编辑器或同步），请重新预览")
        new_text, _old, new = _flip(text)
        if new_text is None:
            raise tracker.ConflictError("预览之后这一行不再是勾选框（请重新预览）")
        data = b"\n".join(lines[:line - 1] + [new_text.encode("utf-8")]
                          + lines[line:])
        workspace_io.atomic_write_bytes(full, data)
    return {"rel": norm_rel, "line": line, "written": 1,
            "summary": "已%s：%s 第 %d 行" % (
                "勾选" if new == "x" else "取消勾选", norm_rel, line)}
