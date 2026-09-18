# -*- coding: utf-8 -*-
"""题库 `questions.csv` 的领域层，以及 1a 从 `03_面试准备/**/*.md` 的两段式导入。

为什么单独立表（不并进 `interviews.csv`）：面试记录是**被问过的事实**，题库是
**要准备的题**。并表的后果是「要准备的题」被「只发生过一次的题」淹没，而且复习
状态（未看 / 看过 / 会了）没有地方安放。两者用「来源 = 面试记录 + 关联公司 /
岗位」串起来做溯源，不合并。

1a 口径（2026-09-15 冻结）：读 `03_面试准备/**/*.md`——**只读，不动用户的
Markdown**——解析成候选题目后**预览**（新增 / 重复 / 跳过），用户确认后凭一次性
令牌落 `questions.csv`。Markdown 没有统一的「题目 / 答案」分隔符，解析只能是
**启发式**的，所以这一步必须走两段式：让人看过「将要落什么」再落。

两段式共三对：add / update / import——预览签发令牌（校验与载荷构造都在本模块），
落盘统一走 approval 的 `question.*` 注册项。**本模块只提供读写与校验、不含
argparse**：命令层 2026-09-18 拆到 `_cli_bank.py`（后端 import 领域层不再连带 CLI）。
"""

import csv
import datetime
import io
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import tracker  # noqa: E402  （复用工作区解析、原子写、锁与 ConflictError）

# 字段常量**只在 tracker.py 定义一处**（与 TALK_* / INTERVIEW_* 同区），这里导入
# 复用——同一张表的列名若在两处各写一遍，改了一边就会静默失配（自检、CSV 表头、
# 前端类型与锁内重校验四路都读它）。
from tracker import (QUESTION_FILE, QUESTION_FIELDS, QUESTION_STATUS,  # noqa: E402
                     QUESTION_ORIGINS, QUESTION_DIFFICULTY)

# 去重键：题目 + 领域 + 科目都相同才算同一道（导入与自拟都用它判重）。
# 不看答案——同一道题的答案要点会随复习更新，不该因为改了答案就变成两道题。
# 科目也要进键：`技术面/网络/x.md` 与 `技术面/操作系统/x.md` 同名却是两道题，
# 只按（题目, 领域）判重会让后者被静默并入"已存在，跳过"（第二轨 MINOR）。
DUPE_KEY_FIELDS = ("题目", "领域", "科目")

# 导入时答案要点的截断长度：正文可能很长，CSV 单行太大会让 Excel / 编辑器都难看，
# 且题库是"要点"而非全文——要全文请看原来的 Markdown（导入不改它）。
ANSWER_PREVIEW_CHARS = 200

# 1a 扫描的模块目录与要跳过的文件：模板不是题目，README 也不是。
MODULE_DIR = "03_面试准备"
SKIP_NAME_PREFIXES = ("_模板_", "README")


# --- 数据层（照 talks.csv 的同构实现）----------------------------------------


def question_path(workspace=None):
    return os.path.join(tracker.resolve_ws(workspace), "05_投递追踪", QUESTION_FILE)


def read_questions(workspace=None, domain=None, subject=None, status=None,
                   keyword=None):
    """读题库；筛选是**同一套口径**的唯一实现（CLI 与后端都走它）。"""
    path = question_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]

    def _match(row, field, value):
        return not value or (row.get(field) or "").strip() == value

    out = []
    for row in rows:
        if not _match(row, "领域", domain):
            continue
        if not _match(row, "科目", subject):
            continue
        if not _match(row, "状态", status):
            continue
        if keyword:
            haystack = " ".join((row.get(field) or "")
                                for field in ("题目", "领域", "科目", "标签",
                                              "答案要点", "关联公司", "关联岗位"))
            if keyword.lower() not in haystack.lower():
                continue
        out.append(row)
    return out


def write_questions(rows, workspace=None):
    """全量重写题库（原子写）。"""
    tracker._atomic_write_csv(question_path(workspace), rows, QUESTION_FIELDS,
                              "utf-8-sig")


def next_question_id(rows):
    """生成下一个题目 ID（Q001 起）。"""
    max_num = 0
    for row in rows:
        m = re.match(r"^Q(\d+)$", (row.get("题目id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "Q%03d" % (max_num + 1)


def find_question(rows, question_id):
    for row in rows:
        if (row.get("题目id") or "").strip() == question_id:
            return row
    return None


def dupe_key(row):
    return tuple((row.get(field) or "").strip() for field in DUPE_KEY_FIELDS)


def _targets(workspace=None):
    """写入会落到的文件（供令牌绑定与预览展示）。"""
    ws = tracker.resolve_ws(workspace)
    return [os.path.join(ws, "05_投递追踪", QUESTION_FILE)]


# --- 1a：从 03_面试准备 的 Markdown 解析（只读）------------------------------


def _strip_markdown(text):
    """去掉围栏代码块、表格行与勾选清单，留下可读的正文骨架。"""
    out = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("|") or stripped.startswith("- [ ]"):
            continue
        out.append(line)
    return "\n".join(out)


def _first_heading(text):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _body_preview(text, limit=ANSWER_PREVIEW_CHARS):
    body = _strip_markdown(text)
    # 去掉一级标题那一行（它已经当成题目）
    body = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.M)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) > limit:
        body = body[:limit].rstrip() + "…"
    return body


def scan_markdown(workspace=None, module_dir=MODULE_DIR, skipped=None):
    """扫描 `<工作区>/<module_dir>/**/*.md` 返回候选题目（**只读**，不写任何东西）。

    启发式（形态不统一，所以必须预览确认）：
      - 题目 = 一级标题 `# xxx` 优先，其次文件名（去扩展名）；
      - 领域 = 模块下的直接子目录名（如 `技术面`），科目 = 再下一级目录（若有）；
      - 答案要点 = 正文去掉代码块 / 表格 / 勾选清单后的摘要（截断 200 字）；
      - 跳过模板（`_模板_*`）与 README——它们不是题目；
      - **正文为空**（占位文件、0 字节）也跳过：否则会落进一堆空壳题目。

    读不动的文件**不静默丢弃**：文件名与原因记进 `skipped`（调用方负责展示）。
    在"预览即承诺"的两段式里，少给题比报错更危险——用户会以为就这些（第二轨
    MAJOR-3；另见 CONTRIBUTING 的禁静默吞错）。

    `skipped` 由调用方传入一个列表（保持本函数的返回类型不变）。
    """
    ws = tracker.resolve_ws(workspace)
    root = os.path.join(ws, module_dir)
    if not os.path.isdir(root):
        return []
    candidates = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()                      # 跨目录顺序也要确定，否则导入顺序会飘
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            # 大小写不敏感：readme.md 与 README.md 一样不是题目
            if name.lower().startswith(tuple(p.lower() for p in SKIP_NAME_PREFIXES)):
                continue
            full = os.path.join(dirpath, name)
            try:
                with io.open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError) as exc:
                if skipped is not None:
                    skipped.append((os.path.relpath(full, ws).replace("\\", "/"),
                                    "读不动（%s）" % exc.__class__.__name__))
                continue
            rel = os.path.relpath(dirpath, root)
            parts = [] if rel == "." else rel.replace("\\", "/").split("/")
            domain = parts[0] if parts else ""
            subject = parts[1] if len(parts) > 1 else ""
            title = _first_heading(text) or os.path.splitext(name)[0]
            answer = _body_preview(text)
            if not title.strip() or not answer:
                if skipped is not None:
                    skipped.append((os.path.relpath(full, ws).replace("\\", "/"),
                                    "没有可用正文（空文件）"))
                continue
            candidates.append({
                "题目": title,
                "领域": domain,
                "科目": subject,
                "答案要点": answer,
                "来源": "导入",
                "来源文件": os.path.relpath(full, ws).replace("\\", "/"),
            })
    return candidates


# --- 校验（预览与落盘两段共用）----------------------------------------------


def _validate_question_fields(fields, workspace=None):
    errors = []
    if not (fields.get("题目") or "").strip():
        errors.append("题目不能为空")
    status = fields.get("状态") or ""
    if status and status not in QUESTION_STATUS:
        # 参数名与中文字段名都写出来：diff 里按中文字段展示，用户按参数名纠错
        errors.append("`--status`（状态）必须是 %s 之一，实际为 `%s`"
                      % ("/".join(QUESTION_STATUS), status))
    origin = fields.get("来源") or ""
    if origin and origin not in QUESTION_ORIGINS:
        errors.append("来源必须是 %s 之一，实际为 `%s`"
                      % ("/".join(QUESTION_ORIGINS), origin))
    difficulty = fields.get("难度") or ""
    if difficulty not in QUESTION_DIFFICULTY:
        errors.append("`--difficulty`（难度）只能是 空/%s，实际为 `%s`"
                      % ("/".join(d for d in QUESTION_DIFFICULTY if d), difficulty))
    return errors


# --- 两段式：自拟新增 --------------------------------------------------------


def preview_add_fields(fields, workspace=None):
    """预览新增一道题（**不落盘**），返回 (errors, plan)。"""
    fields = {field: (fields.get(field) or "") for field in QUESTION_FIELDS}
    for field in QUESTION_FIELDS:
        fields[field] = fields[field].strip()
    if not fields["状态"]:
        fields["状态"] = "未看"
    if not fields["来源"]:
        fields["来源"] = "自拟"
    errors = _validate_question_fields(fields, workspace)
    if errors:
        return errors, None
    rows = read_questions(workspace)
    if any(dupe_key(r) == dupe_key(fields) for r in rows):
        return ["已存在同名同领域的题目（`%s` / `%s`）——改答案请用 update"
                % (fields["题目"], fields["领域"] or "（未分领域）")], None
    diff = ["| 字段 | 值 |", "|---|---|"]
    for field in QUESTION_FIELDS:
        if fields.get(field):
            diff.append("| %s | %s |" % (field, fields[field]))
    plan = {
        "payload": {"fields": fields},
        "summary": "新增题目：%s" % fields["题目"],
        "diff": diff,
        "targets": _targets(workspace),
    }
    return [], plan


def apply_approved_add(payload, workspace=None):
    """两段式第二步：按已确认的载荷新增一道题。"""
    ws = tracker.resolve_ws(workspace)
    fields = dict(payload.get("fields") or {})
    with tracker.file_lock(tracker._lock_path(ws)):
        errors = _validate_question_fields(fields, ws)
        if errors:
            raise tracker.ConflictError(
                "预览之后数据有变化，已拒绝写入：%s（请重新预览）" % "；".join(errors))
        rows = read_questions(ws)
        if any(dupe_key(r) == dupe_key(fields) for r in rows):
            raise tracker.ConflictError("预览之后已存在同名同领域的题目（请重新预览）")
        record = {field: "" for field in QUESTION_FIELDS}
        record.update(fields)
        record["题目id"] = next_question_id(rows)
        record["创建日期"] = datetime.date.today().isoformat()
        rows.append(record)
        write_questions(rows, ws)
        return {"id": record["题目id"], "written": 1,
                "summary": "已新增 %s（%s）" % (record["题目"], record["题目id"])}


# --- 两段式：修改（改答案要点 / 标状态 / 改难度）------------------------------


def _merge_changes(current, changes):
    """合并改动并补自动字段（状态改「会了」时记 `最近复习`）。

    预览段与落盘段共用这一处，别再各写一份——两处拷贝正是「预览说改一列、
    落盘多写一列」的温床（本模块 2026-09-18 修的正是这类）。
    """
    merged = dict(current)
    merged.update(changes)
    if changes.get("状态") == "会了":
        merged["最近复习"] = datetime.date.today().isoformat()
    return merged


def preview_update_fields(question_id, changes, workspace=None):
    """预览修改一道题（**不落盘**），返回 (errors, plan)。

    `changes` 只认 `QUESTION_FIELDS` 里的字段（`题目id` 是身份，不可改）；
    状态改为「会了」时顺手记 `最近复习`——复习过就该有日期，不靠用户另填一次。
    这一列不在 `changes` 里、却会被落盘段写入，所以差异表**显式列出**它：
    预览是"将要落什么"的承诺，只能多列、不能漏列（2026-09-18）。
    """
    question_id = (question_id or "").strip()
    if not question_id:
        return ["缺少题目 id（可用 `bank list` 查）"], None
    changes = dict((k, (v or "").strip()) for k, v in (changes or {}).items()
                   if k in QUESTION_FIELDS and k != "题目id" and (v or "").strip())
    if not changes:
        return ["没有提供任何要改的字段"], None
    rows = read_questions(workspace)
    current = find_question(rows, question_id)
    if current is None:
        return ["找不到 id 为 %s 的题目" % question_id], None
    merged = _merge_changes(current, changes)
    errors = _validate_question_fields(merged, workspace)
    if errors:
        return errors, None
    diff = ["| 字段 | 原值 | 新值 |", "|---|---|---|"]
    for field in QUESTION_FIELDS:
        if field in changes and (current.get(field) or "") != merged[field]:
            diff.append("| %s | %s | %s |" % (
                field, current.get(field) or "（空）", merged[field]))
    # 「最近复习」不在 changes 里（由落盘段自动写入），上面的循环遍历不到它——
    # 不列出来就是「预览说改一列、落盘多写一列」。只在这一列**确实会变**时列出：
    # 今天已标记过「会了」再提交一次，不该出现一行假差异。
    if (changes.get("状态") == "会了"
            and (current.get("最近复习") or "") != merged["最近复习"]):
        diff.append("| 最近复习（自动） | %s | %s |" % (
            current.get("最近复习") or "（空）", merged["最近复习"]))
    if len(diff) == 2:
        return ["这些字段的值没有变化"], None
    plan = {
        "payload": {"id": question_id, "changes": changes},
        "summary": "修改题目 %s（%s）" % (question_id, current.get("题目") or ""),
        "diff": diff,
        "targets": _targets(workspace),
    }
    return [], plan


def apply_approved_update(payload, workspace=None):
    """两段式第二步：按已确认的载荷修改一道题（锁内读最新 → 重校验 → 写）。"""
    ws = tracker.resolve_ws(workspace)
    question_id = (payload.get("id") or "").strip()
    changes = dict(payload.get("changes") or {})
    with tracker.file_lock(tracker._lock_path(ws)):
        rows = read_questions(ws)
        current = find_question(rows, question_id)
        if current is None:
            raise tracker.ConflictError("预览之后这道题不存在了（请重新预览）")
        merged = _merge_changes(current, changes)
        errors = _validate_question_fields(merged, ws)
        if errors:
            raise tracker.ConflictError(
                "预览之后数据有变化，已拒绝写入：%s（请重新预览）" % "；".join(errors))
        changed = [f for f in QUESTION_FIELDS
                   if (current.get(f) or "") != (merged.get(f) or "")]
        if not changed:
            raise tracker.ConflictError("预览之后这些字段没有变化（请重新预览）")
        current.update(merged)
        write_questions(rows, ws)
        return {"id": question_id, "written": 1,
                "summary": "已更新 %s（%s）" % (question_id, "、".join(changed))}


# --- 两段式：1a 从 Markdown 导入 --------------------------------------------


def preview_import(workspace=None, module_dir=MODULE_DIR):
    """解析 `03_面试准备/**/*.md` 并预览将落什么（**不落盘**），返回 (errors, plan)。

    读不动 / 没有正文的文件**出现在预览里**（列为「跳过」），而不是悄悄消失：
    预览是"将要落什么"的承诺，少给题比报错更危险（第二轨 MAJOR-3）。
    """
    ws = tracker.resolve_ws(workspace)
    unreadable = []
    candidates = scan_markdown(ws, module_dir, skipped=unreadable)
    if not candidates:
        if unreadable:
            return ["`%s/` 下没有可导入的 Markdown：%s" % (
                module_dir, "；".join("%s（%s）" % item for item in unreadable))], None
        return ["`%s/` 下没有可导入的 Markdown（或只有模板 / README）" % module_dir], None
    existing = set(dupe_key(r) for r in read_questions(ws))
    picked, duplicates = [], []
    for item in candidates:
        key = dupe_key(item)
        if key in existing or key in set(dupe_key(p) for p in picked):
            duplicates.append(item)
        else:
            picked.append(item)
    if not picked:
        return ["`%s/` 下的 %d 个文件都已入题库（无新增）" % (module_dir, len(candidates))], None

    diff = ["| 题目 | 领域 | 科目 | 来源 |", "|---|---|---|---|"]
    for item in picked:
        diff.append("| %s | %s | %s | 导入 |" % (
            item["题目"], item["领域"] or "—", item["科目"] or "—"))
    for item in duplicates:
        diff.append("| %s | %s | %s | 已存在，跳过（%s） |" % (
            item["题目"], item["领域"] or "—", item["科目"] or "—",
            item.get("来源文件") or "—"))
    for path, reason in unreadable:
        diff.append("| %s | — | — | 跳过：%s |" % (path, reason))
    plan = {
        "payload": {"module_dir": module_dir, "items": picked},
        "summary": "导入 %d 道题（跳过 %d 个已存在%s）" % (
            len(picked), len(duplicates),
            "、%d 个读不动" % len(unreadable) if unreadable else ""),
        "diff": diff,
        "targets": _targets(ws),
    }
    return [], plan


def apply_approved_import(payload, workspace=None):
    """两段式第二步：把已确认的候选题目写进 questions.csv。

    落盘前重算一次重复（预览之后题库可能已变）；`创建日期` 落到当天，
    `最近复习` 留空——导入不等于复习过。
    """
    ws = tracker.resolve_ws(workspace)
    items = list(payload.get("items") or [])
    if not items:
        raise tracker.ConflictError("载荷里没有题目（请重新预览）")
    today = datetime.date.today().isoformat()
    with tracker.file_lock(tracker._lock_path(ws)):
        rows = read_questions(ws)
        existing = set(dupe_key(r) for r in rows)
        added = 0
        for item in items:
            key = dupe_key(item)          # 与预览段同一个键函数，别在这里另写一份
            if not key[0] or key in existing:
                continue
            record = {field: "" for field in QUESTION_FIELDS}
            record.update({k: v for k, v in item.items() if k in QUESTION_FIELDS})
            record["状态"] = record["状态"] or "未看"
            record["来源"] = record["来源"] or "导入"
            # 落盘段也走同一校验（与 add 一致）：预览之后载荷可能被改过
            errors = _validate_question_fields(record, ws)
            if errors:
                raise tracker.ConflictError(
                    "预览之后载荷不合法，已拒绝写入：%s（请重新预览）" % "；".join(errors))
            record["题目id"] = next_question_id(rows)
            record["创建日期"] = today
            rows.append(record)
            existing.add(key)
            added += 1
        if not added:
            raise tracker.ConflictError("预览之后这些题目都已存在（请重新预览）")
        write_questions(rows, ws)
        return {"written": added, "summary": "已导入 %d 道题" % added}


if __name__ == "__main__":
    # 领域层没有可直跑的命令（命令层 2026-09-18 拆到 _cli_bank.py）；直跑给迁移
    # 提示，与 tools/ 下其它模块同一约定：exit 2 而不是静默退出 0。
    print("这是题库的领域层（没有命令）；请改用：python tools/jobws.py bank ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
