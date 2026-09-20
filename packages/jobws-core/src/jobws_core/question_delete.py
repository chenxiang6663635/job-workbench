# -*- coding: utf-8 -*-
"""`questions.csv` 的删除：给"导入"这件高风险动作装刹车（2026-09-20）。

为什么单独成模块（不塞进 `question_bank.py`）：后者是**登记过水位的存量文件**
（`tools/size_allowlist.txt` 里 595 行，只许变小）；新能力按 `question_review.py`
的先例落在同包兄弟模块里——职责相近、互不加行数。

语义三件套，缺一不可：
1. **预览优先**：先把"将删哪几行"列成差异表，人确认后才准删（与 add / update /
   import 共用同一条两段式通道，落盘仍然只在 `jobws apply <令牌>` 一处）；
2. **真删**：对齐全站唯一的行级删除先例——邮件台账（`web/backend/routers/
   progress/mails.py`，锁内整表重读 → 剔除 → 重写，不做软删除标记）；
3. **留痕可恢复**：删之前把整表快照写到**工作区之外**，删错能整份拷回来。

为什么"批量撤回"用筛选条件，而不是"按来源文件撤回"：导入时解析出来的
`来源文件` **没有落盘**（写盘时按 `QUESTION_FIELDS` 白名单过滤），CSV 里没有这
一列；补列违反零 schema 迁移。所以撤回"今天误导入的一整批"的实际用法就是
`--origin 导入 --today`。
"""

import datetime
import os

from . import pathres  # noqa: E402  （快照根目录：**必须**在工作区之外）
from . import tracker  # noqa: E402  （锁、原子写、ConflictError）
from .question_bank import (QUESTION_FIELDS, find_question,  # noqa: E402
                            read_questions, write_questions)
from .tracker import QUESTION_FILE  # noqa: E402

# 批量删除认的筛选键（命令行与后端共用同一份键名，避免两处各写一遍而失配）
DELETE_FILTERS = ("领域", "科目", "关键词", "来源", "关联公司", "今天创建")

# 删除留痕的子目录名（挂在 <snapshot_root>/<工作区名>/ 下）
TRACE_DIR_NAME = "question-deletes"


# --- 预览（不落盘）----------------------------------------------------------


def _targets(workspace=None):
    """写入会落到的文件（供令牌绑定与预览展示）——与题库同款实现，口径不改。"""
    ws = tracker.resolve_ws(workspace)
    return [os.path.join(ws, "05_投递追踪", QUESTION_FILE)]


def _rows_matching(filters, workspace=None):
    """按筛选条件挑题。

    领域 / 科目 / 关键词复用 `question_bank.read_questions`——它是筛选的**唯一实现**，
    这里再抄一遍关键词匹配，就会与 `bank list` 的口径渐行渐远；来源 / 关联公司 /
    今天创建是 `read_questions` 没有的参数，只在本函数补齐。
    """
    rows = read_questions(workspace, domain=filters.get("领域"),
                          subject=filters.get("科目"),
                          keyword=filters.get("关键词"))
    today = datetime.date.today().isoformat()
    out = []
    for row in rows:
        want = filters.get("来源")
        if want and (row.get("来源") or "").strip() != want:
            continue
        want = filters.get("关联公司")
        if want and (row.get("关联公司") or "").strip() != want:
            continue
        if filters.get("今天创建") and (row.get("创建日期") or "").strip() != today:
            continue
        out.append(row)
    return out


def preview_delete_fields(question_id=None, filters=None, workspace=None):
    """预览将删哪些题（**不落盘**），返回 (errors, plan)。

    `question_id` 精确删一题；`filters` 按条件批量删。两者**给且只给一个**。
    匹配 0 题报**错误**而不是空转：预览即承诺，让人以为删过却什么都没发生最伤。
    """
    question_id = (question_id or "").strip()
    filters = dict((key, (value or "").strip())
                   for key, value in (filters or {}).items()
                   if key in DELETE_FILTERS and (value or "").strip())
    if question_id and filters:
        return ["一次只能给题目 id 或筛选条件中的一个"], None
    if not question_id and not filters:
        return ["缺少题目 id 或筛选条件——单题用 --id；批量用 --domain / --subject "
                "/ --keyword / --origin / --company / --today"], None

    if question_id:
        row = find_question(read_questions(workspace), question_id)
        if row is None:
            return ["找不到 id 为 %s 的题目（用 `jobws bank list` 查）" % question_id], None
        picked = [row]
    else:
        picked = _rows_matching(filters, workspace)
        if not picked:
            return ["没有符合筛选条件的题目（%s）——先用 `jobws bank list` 确认条件"
                    % "、".join("%s=%s" % (key, value)
                                for key, value in sorted(filters.items()))], None

    ids = [(row.get("题目id") or "").strip() for row in picked]
    orphan = len([item for item in ids if item])
    if orphan != len(picked):
        # 多半是 CSV 被手改过：跳过去删等于静默少删，比报错糟得多
        return ["有 %d 道题没有题目 id（CSV 可能被手改过），补齐后再删"
                % (len(picked) - orphan)], None

    diff = ["| 题目id | 题目 | 领域 / 科目 |", "|---|---|---|"]
    for row in picked:
        diff.append("| %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            "%s / %s" % (row.get("领域") or "—", row.get("科目") or "—")))
    plan = {
        "payload": {"ids": ids},
        "summary": "删除 %d 道题" % len(picked),
        "diff": diff,
        "targets": _targets(workspace),
    }
    return [], plan


# --- 落盘（凭令牌，且在锁内）------------------------------------------------


def trace_path(workspace=None):
    """删除留痕目录：**工作区之外**（与快照同域，按工作区名分目录）。"""
    ws = tracker.resolve_ws(workspace)
    name = os.path.basename(os.path.normpath(ws)) or "workspace"
    return os.path.join(pathres.snapshot_root(), name, TRACE_DIR_NAME)


def _write_trace(rows, workspace=None):
    """删之前把**整表**快照写走，恢复方式 = 把该文件复制回 `05_投递追踪/questions.csv`。

    为什么放工作区之外：留痕的目的是"删错了还能回来"，而它若与被删对象同处一地
    （同一目录、同一 git、同一网盘），一次误操作会把两者一起抹掉——`pathres` 的
    快照根目录因此强制在工作区之外。写不出来就**中止删除**：无痕删除违背这个操作
    对自己的承诺，宁可不动，也不能悄悄删。
    """
    target_dir = trace_path(workspace)
    os.makedirs(target_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = os.path.join(target_dir, "questions-before-delete-%s.csv" % stamp)
    try:
        tracker._atomic_write_csv(path, rows, QUESTION_FIELDS, "utf-8-sig")
    except OSError as exc:
        raise tracker.ConflictError(
            "删除前的留痕写不出来（%s）——已中止，工作区未做任何改动" % exc)
    return path


def apply_approved_delete(payload, workspace=None):
    """两段式第二步：锁内读最新 → 剔除 → 重写（删之前先留痕）。

    预览之后目标题少了就**整体拒绝**：删一半比什么都不做更糟——用户以为删干净了，
    重跑一次又会拿到另一个结果，而两次之间的差异无从解释。
    """
    ids = [str(item).strip() for item in (payload.get("ids") or [])
           if str(item).strip()]
    if not ids:
        raise tracker.ConflictError("载荷里没有题目 id（请重新预览）")
    ws = tracker.resolve_ws(workspace)
    with tracker.file_lock(tracker._lock_path(ws)):
        rows = read_questions(ws)
        keeping, removing = [], []
        for row in rows:
            if (row.get("题目id") or "").strip() in ids:
                removing.append(row)
            else:
                keeping.append(row)
        missing = [item for item in ids
                   if item not in set((row.get("题目id") or "").strip()
                                      for row in removing)]
        if missing:
            raise tracker.ConflictError(
                "预览之后这些题目不存在了（已放弃本次删除，未做任何改动）：%s"
                % "、".join(missing))
        trace = _write_trace(rows, ws)
        write_questions(keeping, ws)
        return {"id": ",".join(ids), "written": len(removing), "trace": trace,
                "summary": "已删除 %d 道题" % len(removing)}
