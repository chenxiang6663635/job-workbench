# -*- coding: utf-8 -*-
"""笔记勾选框的翻转（预览 / 落盘）——从 `prep_notes` 按职责拆出（2026-09-21 C-1）。

为什么拆：`prep_notes` 是"定位与按字节读取"（哪个目录、哪个文件、怎么切行），
翻转是它唯一的写动作；批量翻转（一次多行，C-1）把这一职责撑到整文件超出
300 行的规模预算。拆开后各自守规模——工具（`_err` / `_target_path` /
`_read_lines` / `_decode_line` / `_lock_path` / `_TASK_RE`）从 prep_notes
引入，不抄第二份（同包兄弟模块直接取私有名，仓库已有先例）。

三条纪律（字节级单点翻转 / 行内容双校验 / 写路径不截断）见 `prep_notes` 的
模块 docstring——本模块是它们的执行面。
"""

import os

from prep_notes import (  # noqa: E402  （同层工具：路径与读取不抄第二份）
    _TASK_RE, _decode_line, _err, _lock_path, _read_lines, _target_path)
from jobws_core import tracker  # noqa: E402  （resolve_ws / file_lock / ConflictError）
from jobws_core import workspace_io  # noqa: E402

# 一次翻转的行数上限（C-1 批量）：正常清单 10-30 行。与 MAX_BYTES 同款的防御性
# 上限——不是为了拦住正常用法，是让"误传整篇行号"这类事故止于预览期。
MAX_TOGGLE_LINES = 100


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


def _normalize_lines(lines):
    """行号参数 → 升序 int 列表；(None, error) 表示参数不可用。

    单个 int 也收（**单行是批量的特例**——老调用方与老用例不必改签名）。
    重复行号**不静默去重**：哪一条被吞掉用户无从知晓，宁可报错指名。
    """
    if isinstance(lines, int) and not isinstance(lines, bool):
        lines = [lines]
    try:
        items = [int(item) for item in (lines or [])]
    except (TypeError, ValueError):
        items = []
    if not items or any(item < 1 for item in items):
        return None, _err("prep.missingLines",
                          "缺少行号（需要被点勾选框所在行在 Markdown 源码里的行号，从 1 起）")
    seen = set()
    for item in items:
        if item in seen:
            return None, _err("prep.duplicateLine",
                              "第 %d 行出现了两次（同一行不要重复提交）" % item,
                              line=item)
        seen.add(item)
    if len(items) > MAX_TOGGLE_LINES:
        return None, _err("prep.tooManyLines",
                          "一次最多翻转 %d 行（这次给了 %d 行）"
                          % (MAX_TOGGLE_LINES, len(items)),
                          limit=MAX_TOGGLE_LINES, count=len(items))
    return sorted(items), None


def _payload_lines(payload):
    """载荷 → [(行号, 预览时原文), …]。**显式兼容老形态**（`line` / `expected`）。

    升级瞬间在途的老确认框（令牌 TTL 内）点确认必须仍能落盘；若不做兼容而写
    `payload.get("lines") or []`，落盘会循环零次、返回"成功翻转 0 行"——用户
    确认了却什么都没写，比报错糟得多。
    """
    items = [item for item in (payload.get("lines") or [])
             if isinstance(item, dict)]
    if items:
        pairs = []
        for item in items:
            line = item.get("line")
            if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
                pairs.append((line, item.get("expected")))
        return pairs
    line = payload.get("line")
    expected = payload.get("expected")
    if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
        return [(line, expected)]
    return []


def preview_toggle(workspace, section, rel, lines):
    """预览翻转勾选框（**不落盘**），返回 (errors, plan)。

    `lines` 是行号列表（单行传 int 也收——单行是批量的特例）。校验都在预览期
    做完并给出**具体原因**（哪一行、为什么不行）：预览是"将要落什么"的承诺，
    含糊失败比明确报错更贵；批量下"N 行里哪一行不行"正是判断依据。
    """
    ws = tracker.resolve_ws(workspace)
    wanted, error = _normalize_lines(lines)
    if error:
        return [error], None
    full, norm_rel, error = _target_path(ws, section, rel)
    if error:
        return [error], None
    if not os.path.isfile(full):
        return [_err("prep.fileNotFound", "文件不存在：%s" % norm_rel,
                     rel=norm_rel)], None
    file_lines, error = _read_lines(full, norm_rel)
    if error:
        return [error], None
    flips = []
    for line in wanted:
        if line > len(file_lines):
            return [_err("prep.lineOutOfRange",
                         "行号 %d 超出文件总行数 %d：%s"
                         % (line, len(file_lines), norm_rel),
                         line=line, total=len(file_lines), rel=norm_rel)], None
        text, error = _decode_line(file_lines[line - 1], norm_rel, line)
        if error:
            return [error], None
        new_text, old, new = _flip(text)
        if new_text is None:
            return [_err("prep.notTaskLine",
                         "第 %d 行不是勾选框行（`- [ ]` 形态），无法翻转：%s"
                         % (line, norm_rel),
                         line=line, rel=norm_rel)], None
        flips.append((line, text, new_text, old, new))
    payload = {"section": section, "rel": norm_rel,
               "lines": [{"line": line, "expected": text}
                         for line, text, _new, _old, _mark in flips]}
    diff = []
    for line, text, new_text, _old, _new in flips:
        if diff:
            diff.append("")  # 块间空一行：N 个既有 3 行块平铺
        diff.append("%s（第 %d 行）" % (norm_rel, line))
        diff.append("- " + text.rstrip("\r"))
        diff.append("+ " + new_text.rstrip("\r"))
    if len(flips) == 1:
        line, _text, _new_text, old, new = flips[0]
        summary = "翻转勾选框：%s 第 %d 行（%s → %s）" % (
            norm_rel, line, _mark_name(old), _mark_name(new))
    else:
        summary = "翻转勾选框：%s 第 %s 行（%d 项）" % (
            norm_rel, "、".join(str(line) for line, *_rest in flips), len(flips))
    return [], {"payload": payload, "summary": summary, "diff": diff,
                "targets": [full]}


def apply_approved_toggle(payload, workspace=None):
    """两段式第二步：按已确认的载荷翻转勾选框（锁内读最新 → 逐行重校验 → 写）。

    重校验比预览多一层意义：从预览到确认之间文件可能被任何编辑器改过
    （Obsidian 等外部程序不拿我们的锁），所以锁**只**保证本仓进程互斥，
    真正兜底的是「行号 + 行内容」双条件——任一不符就拒绝并请用户重新预览。

    批量（C-1）把这条纪律放大为**整批原子**：N 行里只要有一行不符就零字节
    写入。确认书是逐字执行的——"翻能翻的、跳过 M 行"最难向用户解释。
    """
    ws = tracker.resolve_ws(workspace)
    section = (payload.get("section") or "").strip()
    rel = (payload.get("rel") or "").strip()
    entries = _payload_lines(payload)
    if not entries:
        raise tracker.ConflictError(
            "载荷里没有行号与行内容（请重新预览——它是防「预览翻 A、落盘翻 B」"
            "的第二次核对）")
    full, norm_rel, error = _target_path(ws, section, rel)
    if error:
        # error 是 (code, params, message) 三元组：插值取 message（第 3 位）——
        # 直接把三元组 %s 进文案会把 Python repr 泄给用户（C-2 审查 M1）
        raise tracker.ConflictError("预览之后目标已不可用（%s），请重新预览" % error[2])
    with tracker.file_lock(_lock_path(ws)):
        if not os.path.isfile(full):
            raise tracker.ConflictError("预览之后文件不存在了（请重新预览）")
        file_lines, error = _read_lines(full, norm_rel)
        if error:
            raise tracker.ConflictError("预览之后文件不可读（%s），请重新预览" % error[2])
        expected_by_line = dict(entries)
        flips = []
        for line in sorted(expected_by_line):
            if line > len(file_lines):
                raise tracker.ConflictError(
                    "预览之后第 %d 行不存在了（文件行数变了），请重新预览" % line)
            text, error = _decode_line(file_lines[line - 1], norm_rel, line)
            if error:
                raise tracker.ConflictError(
                    "预览之后第 %d 行不可解码（请重新预览）" % line)
            if text != expected_by_line[line]:
                raise tracker.ConflictError(
                    "预览之后第 %d 行被改过（可能是编辑器或同步），请重新预览" % line)
            new_text, _old, new = _flip(text)
            if new_text is None:
                raise tracker.ConflictError(
                    "预览之后第 %d 行不再是勾选框（请重新预览）" % line)
            flips.append((line, new_text, new))
        # 全部核对通过才动字节：整列表一次性重建（不按行号 splice——错位一行
        # 就是写坏文件）
        out = list(file_lines)
        for line, new_text, _new in flips:
            out[line - 1] = new_text.encode("utf-8")
        workspace_io.atomic_write_bytes(full, b"\n".join(out))
    checked = sum(1 for _line, _text, new in flips if new == "x")
    if len(flips) == 1:
        line, _text, new = flips[0]
        return {"rel": norm_rel, "line": line, "written": 1,
                "summary": "已%s：%s 第 %d 行" % (
                    "勾选" if new == "x" else "取消勾选", norm_rel, line)}
    return {"rel": norm_rel, "written": len(flips),
            "summary": "已写回：%s %d 行（勾选 %d、取消 %d）" % (
                norm_rel, len(flips), checked, len(flips) - checked)}
