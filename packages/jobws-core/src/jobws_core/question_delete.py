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

# 行指纹（预览与落盘两次核对用）：题目 id 会**被复用**（编号 = max+1，删掉最大号
# 后再导入就拿到同一个 id），只认 id 会删错行，所以把"这一行长什么样"一起带上。
FINGERPRINT_FIELDS = ("题目id", "题目", "领域", "科目", "创建日期")


def _fingerprint(row):
    """一行的指纹：五个字段的去空白取值（够区分"同一 id 换了内容"）。"""
    return dict((field, (row.get(field) or "").strip())
                for field in FINGERPRINT_FIELDS)


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

    all_rows = read_questions(workspace)
    if question_id:
        row = find_question(all_rows, question_id)
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
    # 重复 id 要在**全表**里数：--id 路径下 picked 只有一行，同 id 的第二行只有在
    # 全表里才看得见；而落盘是按 id 匹配全部同 id 行——不查就会"删一题带走两行"
    wanted = set(ids)
    counts = {}
    for row in all_rows:
        key = (row.get("题目id") or "").strip()
        if key in wanted:
            counts[key] = counts.get(key, 0) + 1
    dupes = sorted(item for item, number in counts.items() if number > 1)
    if dupes:
        return ["CSV 里有重复的题目 id（%s）——一次删除会带走多行，先修数据再删"
                % "、".join(dupes)], None

    # 差异表带上**筛选依据**（来源 / 创建日期）：批量撤回的主用法是
    # `--origin 导入 --today`，表里没有这两列就没法核对"删的是不是那批"
    diff = ["| 题目id | 题目 | 领域 / 科目 | 来源 | 创建日期 |",
            "|---|---|---|---|---|"]
    for row in picked:
        diff.append("| %s | %s | %s | %s | %s |" % (
            row.get("题目id") or "", row.get("题目") or "",
            "%s / %s" % (row.get("领域") or "—", row.get("科目") or "—"),
            row.get("来源") or "—", row.get("创建日期") or "—"))
    plan = {
        # rows = 行指纹：落盘时要核对"还是这几行"（见 _validate_fingerprints）
        "payload": {"ids": ids, "rows": [_fingerprint(row) for row in picked]},
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
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = os.path.join(target_dir, "questions-before-delete-%s.csv" % stamp)
    try:
        # makedirs 也放进 try：建不出目录（权限 / 盘满）时抛裸 OSError 会以 500
        # 冒出去，而它其实是"留痕写不出来 → 中止删除"，语义与写文件失败完全同类
        os.makedirs(target_dir, exist_ok=True)
        tracker._atomic_write_csv(path, rows, QUESTION_FIELDS, "utf-8-sig")
    except OSError as exc:
        raise tracker.ConflictError(
            "删除前的留痕写不出来（%s）——已中止，工作区未做任何改动" % exc)
    return path


def _validate_fingerprints(rows, expected):
    """核对"要删的还正是预览时那几行"。

    编号是 max+1（`question_bank.next_question_id`）：删掉最大编号后新题会**复用**
    那个 id，所以只按 id 匹配就会出现"预览删 Q006、落盘删掉刚导入的新 Q006"。
    行指纹（id + 题目 + 领域 + 科目 + 创建日期）不一致就整体拒绝——宁可这次不删，
    也不能删错行（删错之后用户根本察觉不到，快照也就不会去用）。
    """
    by_id = {}
    for row in rows:
        by_id.setdefault((row.get("题目id") or "").strip(), []).append(row)
    for wanted in expected:
        qid = (wanted.get("题目id") or "").strip()
        matches = by_id.get(qid) or []
        if len(matches) != 1:
            raise tracker.ConflictError(
                "%s 这一行在预览之后不在了或不再唯一（已放弃本次删除，未做任何改动）"
                % qid)
        if _fingerprint(matches[0]) != wanted:
            raise tracker.ConflictError(
                "%s 这一行在预览之后被改过（已放弃本次删除，未做任何改动）——请重新预览"
                % qid)


def apply_approved_delete(payload, workspace=None):
    """两段式第二步：锁内读最新 → 核对行指纹 → 剔除 → 重写（删之前先留痕）。

    预览之后目标题少了、被改过、或 id 已被复用，都**整体拒绝**：删一半比什么都不做
    更糟，删错行更糟——用户以为删干净了，重跑一次又会拿到另一个结果，而两次之间的
    差异无从解释。
    """
    ids = [str(item).strip() for item in (payload.get("ids") or [])
           if str(item).strip()]
    expected = [item for item in (payload.get("rows") or []) if isinstance(item, dict)]
    if not ids:
        raise tracker.ConflictError("载荷里没有题目 id（请重新预览）")
    if len(expected) != len(ids):
        # 老令牌 / 手搓载荷没有指纹：没有它就没法确认「删的还是那一行」，拒绝
        raise tracker.ConflictError(
            "载荷里没有行指纹（请重新预览——它是防「预览删 A、落盘删 B」的第二次核对）")
    ws = tracker.resolve_ws(workspace)
    with tracker.file_lock(tracker._lock_path(ws)):
        rows = read_questions(ws)
        _validate_fingerprints(rows, expected)
        keeping, removing = [], []
        for row in rows:
            if (row.get("题目id") or "").strip() in ids:
                removing.append(row)
            else:
                keeping.append(row)
        trace = _write_trace(rows, ws)
        write_questions(keeping, ws)
        return {"id": ",".join(ids), "written": len(removing), "trace": trace,
                "summary": "已删除 %d 道题" % len(removing)}
