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

退出码：0 成功 / 1 业务失败（无可导入的题、冲突）/ 2 用法错误。
"""

from __future__ import print_function

import argparse
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

# 去重键：同领域同名视为同一道题（导入与自拟都用它判重）。只看题目不看答案——
# 同一道题的答案要点会随复习更新，不该因为改了答案就变成两道题。
DUPE_KEY_FIELDS = ("题目", "领域")

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


def scan_markdown(workspace=None, module_dir=MODULE_DIR):
    """扫描 `<工作区>/<module_dir>/**/*.md` 返回候选题目（**只读**，不写任何东西）。

    启发式（形态不统一，所以必须预览确认）：
      - 题目 = 一级标题 `# xxx` 优先，其次文件名（去扩展名）；
      - 领域 = 模块下的直接子目录名（如 `技术面`），科目 = 再下一级目录（若有）；
      - 答案要点 = 正文去掉代码块/表格/勾选清单后的摘要（截断 200 字）；
      - 跳过模板（`_模板_*`）与 README——它们不是题目。
    """
    ws = tracker.resolve_ws(workspace)
    root = os.path.join(ws, module_dir)
    if not os.path.isdir(root):
        return []
    candidates = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            if name.startswith(SKIP_NAME_PREFIXES):
                continue
            full = os.path.join(dirpath, name)
            try:
                with io.open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(dirpath, root)
            parts = [] if rel == "." else rel.replace("\\", "/").split("/")
            domain = parts[0] if parts else ""
            subject = parts[1] if len(parts) > 1 else ""
            title = _first_heading(text) or os.path.splitext(name)[0]
            candidates.append({
                "题目": title,
                "领域": domain,
                "科目": subject,
                "答案要点": _body_preview(text),
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


# --- 两段式：1a 从 Markdown 导入 --------------------------------------------


def preview_import(workspace=None, module_dir=MODULE_DIR):
    """解析 `03_面试准备/**/*.md` 并预览将落什么（**不落盘**），返回 (errors, plan)。"""
    ws = tracker.resolve_ws(workspace)
    candidates = scan_markdown(ws, module_dir)
    if not candidates:
        return ["`%s/` 下没有可导入的 Markdown（或只有模板 / README）" % module_dir], None
    existing = set(dupe_key(r) for r in read_questions(ws))
    picked, skipped = [], []
    for item in candidates:
        key = (item["题目"].strip(), item["领域"].strip())
        if key in existing or key in set(dupe_key(p) for p in picked):
            skipped.append(item)
        else:
            picked.append(item)
    if not picked:
        return ["`%s/` 下的 %d 个文件都已入题库（无新增）" % (module_dir, len(candidates))], None

    today = datetime.date.today().isoformat()
    diff = ["| 题目 | 领域 | 状态 | 来源 |", "|---|---|---|---|"]
    for item in picked:
        diff.append("| %s | %s | 未看 | 导入 |" % (item["题目"], item["领域"] or "—"))
    for item in skipped:
        diff.append("| %s | %s | — | 已存在，跳过 |" % (item["题目"], item["领域"] or "—"))
    plan = {
        "payload": {"module_dir": module_dir, "items": picked},
        "summary": "导入 %d 道题（跳过 %d 个已存在）" % (len(picked), len(skipped)),
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
            key = ((item.get("题目") or "").strip(), (item.get("领域") or "").strip())
            if not key[0] or key in existing:
                continue
            record = {field: "" for field in QUESTION_FIELDS}
            record.update({k: v for k, v in item.items() if k in QUESTION_FIELDS})
            record["状态"] = record["状态"] or "未看"
            record["来源"] = record["来源"] or "导入"
            record["题目id"] = next_question_id(rows)
            record["创建日期"] = today
            rows.append(record)
            existing.add(key)
            added += 1
        if not added:
            raise tracker.ConflictError("预览之后这些题目都已存在（请重新预览）")
        write_questions(rows, ws)
        return {"written": added, "summary": "已导入 %d 道题" % added}


# --- CLI --------------------------------------------------------------------


def _print_questions(rows):
    if not rows:
        print("（题库为空——用 `jobws bank add` 加题，或 `jobws bank import --preview` 从 03_面试准备 导入）")
        return
    print("| 题目id | 题目 | 领域 | 状态 | 来源 |")
    print("|---|---|---|---|---|")
    for row in rows:
        print("| %s | %s | %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            row.get("领域") or "—", row.get("状态") or "未看", row.get("来源") or ""))
    print("")
    print("共 %d 道" % len(rows))


def cmd_bank(args):
    """题库：list 查、add 加（两段式）、import 从 03_面试准备 导入（两段式）。"""
    workspace = getattr(args, "workspace", None)

    if args.action == "list":
        rows = read_questions(workspace, domain=args.domain, subject=args.subject,
                              status=args.status, keyword=args.keyword)
        _print_questions(rows)
        return 0

    if args.action == "add":
        fields = {
            "题目": args.title, "领域": args.domain or "", "科目": args.subject or "",
            "标签": args.tags or "", "难度": args.difficulty or "",
            "答案要点": args.answer or "", "来源": args.origin or "",
            "关联公司": args.company or "", "关联岗位": args.role or "",
            "状态": args.status or "", "备注": args.note or "",
        }
        errors, plan = preview_add_fields(fields, workspace)
        for error in errors:
            print("错误：%s" % error)
        if plan is None:
            return 1
        # 函数内 import：jobws 的 lint 分支要求被分发模块不得顶层引入三方库
        import approval
        result = approval.preview("question.add", workspace, plan["payload"],
                                  plan["summary"], plan["diff"], plan["targets"])
        print("预览：%s" % result["summary"])
        for line in plan["diff"]:
            print(line)
        print("")
        print("确认后落盘：python tools/jobws.py apply %s" % result["token"])
        return 0

    if args.action == "import":
        errors, plan = preview_import(workspace, args.module_dir or MODULE_DIR)
        for error in errors:
            print("错误：%s" % error)
        if plan is None:
            return 1
        import approval
        result = approval.preview("question.import", workspace, plan["payload"],
                                  plan["summary"], plan["diff"], plan["targets"])
        print("预览：%s" % result["summary"])
        for line in plan["diff"]:
            print(line)
        print("")
        print("确认后落盘：python tools/jobws.py apply %s" % result["token"])
        return 0

    print("未知子命令：%s" % args.action)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jobws bank", description="题库：list / add / import（写操作走两段式）")
    subs = parser.add_subparsers(dest="action")

    p_list = subs.add_parser("list", help="列出题目（可按领域/科目/状态/关键词筛选）")
    p_list.add_argument("--domain", help="领域（如 技术面）")
    p_list.add_argument("--subject", help="科目")
    p_list.add_argument("--status", help="状态（未看/看过/会了）")
    p_list.add_argument("--keyword", "-k", help="关键词（题目/要点/标签等）")
    p_list.add_argument("--workspace", default=None)

    p_add = subs.add_parser("add", help="新增一道题（预览后凭令牌落盘）")
    p_add.add_argument("--title", required=True, help="题目")
    p_add.add_argument("--domain", help="领域")
    p_add.add_argument("--subject", help="科目")
    p_add.add_argument("--tags", help="标签（逗号分隔）")
    p_add.add_argument("--difficulty", default="", help="难度（易/中/难，可留空）")
    p_add.add_argument("--answer", help="答案要点")
    p_add.add_argument("--origin", default="", help="来源（自拟/笔试回忆/面试记录/导入）")
    p_add.add_argument("--company", help="关联公司")
    p_add.add_argument("--role", help="关联岗位")
    p_add.add_argument("--status", help="状态（默认 未看）")
    p_add.add_argument("--note", help="备注")
    p_add.add_argument("--workspace", default=None)

    p_import = subs.add_parser("import", help="从 03_面试准备/**/*.md 导入（只读解析 + 预览）")
    p_import.add_argument("--module-dir", default=MODULE_DIR, help="模块目录名")
    p_import.add_argument("--workspace", default=None)

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 2
    return cmd_bank(args)


if __name__ == "__main__":
    print("该脚本已合并进统一入口，请改用：python tools/jobws.py bank ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
