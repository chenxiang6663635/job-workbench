# -*- coding: utf-8 -*-
"""投递追踪表增删查改。

数据存为 CSV（UTF-8 with BOM，Excel 直接打开中文不乱码）。
每次写入前全量重读并做字段级校验，校验失败不落盘。

用法：
    python tools/tracker.py add --company "某某" --role "热管理工程师" \
        --direction datacenter --batch 正式批 --source 企业校招官网 \
        --deadline 2026-09-30 --resume datacenter --score 78 \
        --archive "05_投递追踪/applications/某某_热管理工程师"

    python tools/tracker.py list [--stage 笔试] [--direction datacenter]
                                 [--batch 提前批] [--due-within 7]
    python tools/tracker.py show --id A001
    python tools/tracker.py update --id A001 --stage 一面 --next "准备项目二口述"
    python tools/tracker.py history [--id A001] [--limit 20]

变更时间线：每次 add/update 会把字段级差异追加到
<工作区>/05_投递追踪/history.csv（时间, id, 字段, 原值, 新值），
供停留天数统计与前端时间线展示使用。

退出码：0 成功，1 失败。
"""

from __future__ import print_function

import argparse
import csv
import io
import json
import os
import re
import sys

# Python 3.8 兼容：不使用 dict | dict、list[str] 等 3.9+ 注解
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORKSPACE = os.path.join(ROOT, "personal")

# 由 main() 在解析 --workspace 后赋值；模块级常量仅供被 report.py 导入时兜底
WORKSPACE = DEFAULT_WORKSPACE


def set_workspace(path):
    """供 report.py 等导入方设置工作区。"""
    global WORKSPACE
    WORKSPACE = os.path.abspath(path)


def resolve_ws(workspace=None):
    """显式传参优先，缺省回退全局。Web 并发场景必须显式传参。"""
    return os.path.abspath(workspace) if workspace else WORKSPACE


def available_directions(workspace=None):
    """读取工作区装入的领域插件支持的方向 ID。

    读不到时返回空列表——此时调用方应放行而非报错，
    因为用户可能还没装入插件，或使用了自定义方向。
    """
    d = os.path.join(resolve_ws(workspace), "config", "directions")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md"))


def check_direction(value, workspace=None):
    """校验方向 ID。插件不可用时放行，可用时严格校验。"""
    valid = available_directions(workspace)
    if not valid:
        return None
    if value in valid or value in DIRECTIONS:
        return None
    return ["`--direction` 必须是 %s 或 other，实际为 `%s`" % ("/".join(valid), value)]


def csv_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", "tracker.csv")

# 输出时保持固定字段顺序
FIELDS = [
    "id", "公司", "岗位", "方向", "批次", "来源", "截止日期", "投递日期",
    "当前阶段", "状态原因", "下次动作", "下次动作日期", "简历版本", "评分",
    "归档目录", "备注",
]

# 方向 ID 取决于工作区装入的领域插件，不在脚本里写死。
# 校验时动态读取 <工作区>/config/directions/*.md，读不到则放行（只记录不拦截）。
DIRECTIONS = ["other"]
BATCHES = ["提前批", "正式批", "补录"]
SOURCES = ["应届生求职网", "牛客", "企业校招官网", "学校就业网", "内推", "其他"]

# 正常流转顺序；终态单独处理
STAGES = ["待投", "已投", "笔试", "一面", "二面", "三面", "HR面", "offer", "签约"]
# 终态。注意语义差异：「已挂/已放弃」是被拒或放弃（失败），
# 「我拒绝的 offer」是用户主动拒绝（双向选择）——复盘归因时必须分开统计，
# 拒绝不该被算成"失败"，它可能意味着拿到了更好的。
TERMINAL_STAGES = ["已挂", "已放弃", "我拒绝的 offer"]
# 失败类终态（失败归因只聚合这两类）
FAIL_STAGES = ["已挂", "已放弃"]

# update 只允许改这些字段，公司与岗位不可改（改则需新建记录并作废原记录）
UPDATABLE = ["当前阶段", "状态原因", "下次动作", "下次动作日期", "备注", "评分",
             "投递日期", "截止日期"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 变更时间线：独立 CSV，主表保持「一行一岗位」的当前状态快照
HISTORY_FILE = "history.csv"
HISTORY_FIELDS = ["时间", "id", "字段", "原值", "新值"]
# 记入时间线的字段。公司与岗位不可改，故不在其中。
HISTORY_TRACKED = ["当前阶段", "状态原因", "下次动作", "下次动作日期",
                   "投递日期", "截止日期", "评分", "备注"]

# 静默提醒默认阈值：非终态记录距最后一次推进超过该天数即提示
STALE_DAYS = 14

# 面试记录：独立 CSV，绝不加 tracker.csv 的列。
# 面试与岗位是一对多（一个岗位可能有四面），加列会破坏主表「一行一岗位」的
# 当前状态快照语义。以「关联记录」外键指回 tracker.csv 的 id。
INTERVIEW_FILE = "interviews.csv"
INTERVIEW_FIELDS = [
    "面试id", "关联记录", "公司", "岗位", "轮次", "面试时间", "形式",
    "面试官", "问题记录", "我的回答要点", "复盘与改进", "结果",
]
# 公司/岗位为冗余快照：关联记录可空（内推、未录入的面试也要能记）
INTERVIEW_ROUNDS = ["笔试", "一面", "二面", "三面", "HR面", "终面", "其他"]
INTERVIEW_FORMS = ["现场", "视频", "电话", "其他"]
INTERVIEW_RESULTS = ["待定", "通过", "未通过", "取消"]

# 招聘方联系人：独立 CSV（一对多）。跟进有节奏的招聘流程靠联系人记录维系。
CONTACT_FILE = "contacts.csv"
CONTACT_FIELDS = [
    "联系人id", "关联记录", "姓名", "角色", "公司", "联系方式",
    "来源", "最近联系", "下次跟进", "备注",
]
# 最近联系/下次跟进用 YYYY-MM-DD，与主表日期格式一致（Excel 可排序）

# Offer 事实记录：只记已知事实，绝不内置「推荐选哪个」的判断字段。
# 选择是多目标决策（钱/地点/成长/风险），产品不替用户加权。
OFFER_FILE = "offers.csv"
OFFER_FIELDS = [
    "offer_id", "关联记录", "公司", "岗位", "薪资构成", "月薪", "年终",
    "签字费", "股票期权", "工作地点", "答复截止日", "其他条件", "备注",
]

# ---------------------------------------------------------------------------
# schema 自检：启动时只读扫描，坏文件隔离到 quarantine/ 而非静默丢弃。
# schema 版本用 sidecar 文件（.schema.json）而不是加列——加列会污染
# 「一行一岗位」的数据语义，sidecar 对 Excel 透明且可手工修复。
# ---------------------------------------------------------------------------
TRACKING_SCHEMA_VERSION = 1
SCHEMA_FILE = ".schema.json"
QUARANTINE_DIR = "quarantine"


def _quarantine(path, workspace=None):
    """把坏文件移入 quarantine/（带时间戳后缀），返回新路径或 None。"""
    if not os.path.isfile(path):
        return None
    qdir = os.path.join(os.path.dirname(path), QUARANTINE_DIR)
    if not os.path.isdir(qdir):
        os.makedirs(qdir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(qdir, "%s.%s.bak" % (os.path.basename(path), stamp))
    try:
        os.replace(path, dest)
        return os.path.relpath(dest, resolve_ws(workspace))
    except OSError:
        return None


def _read_csv_checked(path):
    """读 CSV；解析失败抛 ValueError（由调用方决定是否隔离）。"""
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _check_file_rows(name, rows, path, required, dates, enums, fk_ids, issues):
    """行级校验：必填 / 日期格式 / 枚举 / 外键。rows 为 None 表示文件损坏。"""
    if rows is None:
        return
    header = list(rows[0].keys()) if rows else []
    if header:
        for col in required:
            if col not in header:
                issues.append("缺少列「%s」（schema 不匹配）" % col)

    for i, row in enumerate(rows, start=2):        # 行号从 2 起（1 是表头）
        for col in required:
            if not (row.get(col) or "").strip():
                issues.append("第 %d 行：%s 为空" % (i, col))
        for col in dates:
            value = (row.get(col) or "").strip()
            if value and not parse_iso_date(value):
                issues.append("第 %d 行：%s「%s」不是 YYYY-MM-DD" % (i, col, value))
        for col, allowed in enums:
            value = (row.get(col) or "").strip()
            if value and value not in allowed:
                issues.append("第 %d 行：%s「%s」不在 %s" % (i, col, value, "/".join(allowed)))
        if fk_ids is not None:
            link = (row.get("关联记录") or "").strip()
            if link and link not in fk_ids:
                issues.append("第 %d 行：关联记录「%s」在 tracker.csv 中不存在" % (i, link))


def run_check(workspace=None):
    """只读自检所有投递追踪数据文件。

    返回 {ok, version, files:[{file, ok, issues[]}], quarantined[]}。
    CLI 的 check 子命令与 Web 的 system 路由共用此函数（单一事实源）。
    坏文件（无法解析的 CSV）自动隔离到 quarantine/，绝不让坏数据进流程。
    """
    ws = resolve_ws(workspace)
    tracking = os.path.join(ws, "05_投递追踪")
    quarantined = []
    files = []

    # sidecar schema 版本
    schema_path = os.path.join(tracking, SCHEMA_FILE)
    version = TRACKING_SCHEMA_VERSION
    version_note = None
    if os.path.isfile(schema_path):
        try:
            with io.open(schema_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            version = int(meta.get("version", TRACKING_SCHEMA_VERSION))
        except (ValueError, OSError, TypeError):
            version = TRACKING_SCHEMA_VERSION
        if version > TRACKING_SCHEMA_VERSION:
            version_note = ("数据由更新版本的应用写入（schema v%d > v%d），"
                            "请升级应用后再操作" % (version, TRACKING_SCHEMA_VERSION))
        elif version < TRACKING_SCHEMA_VERSION:
            version_note = ("数据是旧版本（schema v%d），当前无破坏性变更，"
                            "无需迁移" % version)
    else:
        # 首次自检补写 sidecar（幂等）
        try:
            if not os.path.isdir(tracking):
                os.makedirs(tracking)
            with io.open(schema_path, "w", encoding="utf-8") as f:
                json.dump({"version": TRACKING_SCHEMA_VERSION}, f)
        except OSError:
            pass

    # tracker.csv 先行：其他文件的外键以它的 id 集合为准
    fk_ids = set()
    main_path = csv_path(ws)
    if os.path.isfile(main_path):
        issues = []
        main_rows = None
        try:
            main_rows = _read_csv_checked(main_path)
        except (ValueError, csv.Error, UnicodeDecodeError, OSError) as exc:
            dest = _quarantine(main_path, ws)
            quarantined.append({
                "file": "tracker.csv", "error": str(exc)[:120],
                "moved_to": dest or "隔离失败，请手动处理",
            })
            files.append({"file": "tracker.csv", "ok": False,
                          "issues": ["文件无法解析，已隔离到 quarantine/"], "note": ""})
        if main_rows is not None:
            _check_file_rows(
                "tracker.csv", main_rows, main_path,
                required=["id", "公司", "岗位", "方向", "批次", "当前阶段"],
                dates=["截止日期", "投递日期", "下次动作日期"],
                # 方向不做枚举校验：合法方向取决于工作区装入的插件，动态的
                enums=[("当前阶段", STAGES + TERMINAL_STAGES),
                       ("批次", BATCHES)],
                fk_ids=None, issues=issues)
            fk_ids = set((r.get("id") or "").strip() for r in main_rows)
            files.append({"file": "tracker.csv", "ok": not issues,
                          "issues": issues, "note": ""})

    def inspect(fname, required, dates=(), enums=(), with_fk=False):
        path = os.path.join(tracking, fname)
        if not os.path.isfile(path):
            files.append({"file": fname, "ok": True, "issues": [],
                          "note": "尚未创建"})
            return
        issues = []
        rows = None
        try:
            rows = _read_csv_checked(path)
        except (ValueError, csv.Error, UnicodeDecodeError, OSError) as exc:
            dest = _quarantine(path, ws)
            quarantined.append({
                "file": fname, "error": str(exc)[:120],
                "moved_to": dest or "隔离失败，请手动处理",
            })
            files.append({"file": fname, "ok": False,
                          "issues": ["文件无法解析，已隔离到 quarantine/"], "note": ""})
            return
        _check_file_rows(fname, rows, path, required, dates, enums,
                         fk_ids if with_fk else None, issues)
        files.append({"file": fname, "ok": not issues, "issues": issues, "note": ""})

    # 面试 / 联系人 / offer / 时间线
    inspect(INTERVIEW_FILE,
            required=["面试id"],          # 关联记录可空（内推等未录入的面试）
            enums=[("轮次", INTERVIEW_ROUNDS), ("形式", INTERVIEW_FORMS),
                   ("结果", INTERVIEW_RESULTS)],
            with_fk=True)          # 面试时间是宽松格式（可含 HH:MM），不套日期校验
    inspect(CONTACT_FILE,
            required=["联系人id"],
            dates=["最近联系", "下次跟进"],
            with_fk=True)
    inspect(OFFER_FILE,
            required=["offer_id"],
            dates=["答复截止日"],
            with_fk=True)
    inspect(HISTORY_FILE,
            required=["时间", "id", "字段"])

    ok = all(f["ok"] for f in files) and not quarantined
    return {
        "ok": ok,
        "version": version,
        "versionNote": version_note,
        "files": files,
        "quarantined": quarantined,
    }


def parse_iso_date(value):
    """解析 YYYY-MM-DD，非法返回 None。与 report.parse_date 同规则，
    但 tracker 不 import report（脚本互不调用，report 才导入 tracker）。
    """
    raw = (value or "").strip()
    if not DATE_RE.match(raw):
        return None
    y, m, d = (int(x) for x in raw.split("-"))
    try:
        return date(y, m, d)
    except ValueError:
        return None


def history_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", HISTORY_FILE)


def read_history(workspace=None, app_id=None):
    """读取时间线。按写入顺序（时间升序）返回，app_id 非空时只返回该记录。"""
    path = history_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("id") or "").strip() == app_id]
    return rows


def append_history(entries, workspace=None):
    """追加变更条目。entries 为字典列表，键为 id / 字段 / 原值 / 新值。

    新建文件用 utf-8-sig 补 BOM（与主表一致，Excel 中文不乱码）；
    已有文件改用 utf-8 追加——utf-8-sig 每次 open 都会写 BOM，
    在追加场景下会把 BOM 插进文件中间。

    追加无法原子化（必须打开已有文件续写），故只保证 fsync 落盘：
    时间线是审计日志，丢一条尚可追溯，主表损坏才是灾难——原子性预算
    花在 write_rows 上。若需原子追加，正解是改批量重写，但时间线写入频繁，
    全量重写代价过高，不划算。
    """
    if not entries:
        return 0
    path = history_path(workspace)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)

    is_new = not os.path.isfile(path) or os.path.getsize(path) == 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with io.open(path, "w" if is_new else "a",
                 encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS,
                                extrasaction="ignore", restval="")
        if is_new:
            writer.writeheader()
        for entry in entries:
            row = {"时间": now, "id": entry.get("id", ""), "字段": entry.get("字段", ""),
                   "原值": entry.get("原值", ""), "新值": entry.get("新值", "")}
            writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())
    return len(entries)


def diff_entries(app_id, old_row, new_row, fields=None):
    """对比两行，返回有变化的字段条目列表（空列表表示无变化）。"""
    out = []
    for field in (fields or HISTORY_TRACKED):
        before = ((old_row or {}).get(field) or "").strip()
        after = ((new_row or {}).get(field) or "").strip()
        if before != after:
            out.append({"id": app_id, "字段": field, "原值": before, "新值": after})
    return out


def _history_date(entries, app_id, field=None):
    """取某记录最后一次变更（或最后一次指定字段变更）的日期。"""
    best = None
    for entry in entries:
        if (entry.get("id") or "").strip() != app_id:
            continue
        if field and (entry.get("字段") or "").strip() != field:
            continue
        when = parse_iso_date((entry.get("时间") or "")[:10])
        if when and (best is None or when > best):
            best = when
    return best


def last_stage_change_date(app_id, entries):
    """最后一次「当前阶段」变更日期，无则 None。"""
    return _history_date(entries, app_id, "当前阶段")


def last_activity_date(app_id, entries):
    """最后一次任意变更日期（含创建），无则 None。"""
    return _history_date(entries, app_id)


def stage_base_date(row, entries, app_id=None):
    """停留天数的基准日，按优先级回退。

    最后一次阶段变更 → 投递日期 → 最后一次任意变更 → None。

    投递日期排在「任意变更」之前：投递日期是用户声明的流程起点，
    而「任意变更」里包含记录录入时间——补录一条一个月前投的岗位时，
    若以录入时间为准就永远不会触发静默提醒，与语义相反。
    「任意变更」只在既无阶段变更、又没填投递日期时兜底。

    旧数据没有 history.csv 时自动退到投递日期，不需要迁移。
    """
    app_id = app_id or (row.get("id") or "").strip()
    when = last_stage_change_date(app_id, entries)
    if when:
        return when
    when = parse_iso_date(row.get("投递日期"))
    if when:
        return when
    return last_activity_date(app_id, entries)


def stale_days(row, entries, today=None):
    """当前阶段已停留天数。无基准日返回 None（不参与静默判定）。"""
    base = stage_base_date(row, entries)
    if base is None:
        return None
    today = today or date.today()
    return (today - base).days


def read_rows(workspace=None):
    path = csv_path(workspace)
    if not os.path.isfile(path):
        return []
    # utf-8-sig 读取时自动去掉 BOM
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def write_rows(rows, workspace=None):
    """全量重写主表。

    原子写（tmp + os.replace）：主表是用户唯一的数据源，写到一半被中断会
    留下半截 CSV。改名在同目录内是原子操作，故临时文件与目标同目录。
    """
    path = csv_path(workspace)
    _atomic_write_csv(path, rows, FIELDS, "utf-8-sig")


# 临时文件前缀：同步工具（Syncthing / 网盘）可据此排除半成品
TMP_PREFIX = ".jobws_tmp_"


def _atomic_write_csv(path, rows, fieldnames, encoding):
    """原子写 CSV：写临时文件 → fsync → os.replace。

    utf-8-sig 写入时加 BOM，Excel 直接打开不乱码；
    restval 保证旧文件（缺新增列）写回时补出空列，避免 None 落盘成 "None"。
    """
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = os.path.join(directory, TMP_PREFIX + os.path.basename(path))
    with io.open(tmp, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore",
                                restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def interview_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", INTERVIEW_FILE)


def read_interviews(workspace=None, app_id=None):
    """读取面试记录。app_id 非空时只返回关联该岗位记录的面试。"""
    path = interview_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows


def write_interviews(rows, workspace=None):
    """全量重写面试表（原子写）。"""
    _atomic_write_csv(interview_path(workspace), rows, INTERVIEW_FIELDS, "utf-8-sig")


def next_interview_id(rows):
    """生成下一个面试 ID（I001 起）。"""
    max_num = 0
    for row in rows:
        m = re.match(r"^I(\d+)$", (row.get("面试id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "I%03d" % (max_num + 1)


def find_interview(rows, interview_id):
    for row in rows:
        if (row.get("面试id") or "").strip() == interview_id:
            return row
    return None


def contact_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", CONTACT_FILE)


def read_contacts(workspace=None, app_id=None):
    """读取联系人。app_id 非空时只返回关联该岗位记录的联系人。"""
    path = contact_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows


def write_contacts(rows, workspace=None):
    _atomic_write_csv(contact_path(workspace), rows, CONTACT_FIELDS, "utf-8-sig")


def next_contact_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^C(\d+)$", (row.get("联系人id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "C%03d" % (max_num + 1)


def find_contact(rows, contact_id):
    for row in rows:
        if (row.get("联系人id") or "").strip() == contact_id:
            return row
    return None


def offer_path(workspace=None):
    return os.path.join(resolve_ws(workspace), "05_投递追踪", OFFER_FILE)


def read_offers(workspace=None, app_id=None):
    """读取 Offer 事实。app_id 非空时只返回关联该岗位记录的 Offer。"""
    path = offer_path(workspace)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if app_id:
        rows = [r for r in rows if (r.get("关联记录") or "").strip() == app_id]
    return rows


def write_offers(rows, workspace=None):
    _atomic_write_csv(offer_path(workspace), rows, OFFER_FIELDS, "utf-8-sig")


def next_offer_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^O(\d+)$", (row.get("offer_id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "O%03d" % (max_num + 1)


def find_offer(rows, offer_id):
    for row in rows:
        if (row.get("offer_id") or "").strip() == offer_id:
            return row
    return None


def next_id(rows):
    max_num = 0
    for row in rows:
        m = re.match(r"^A(\d+)$", (row.get("id") or "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "A%03d" % (max_num + 1)


def check_date(value, label, allow_empty=True):
    if not value:
        if allow_empty:
            return None
        return ["`%s` 不能为空" % label]
    if not DATE_RE.match(value):
        return ["`%s: %s` 日期格式错误，应为 YYYY-MM-DD" % (label, value)]
    return None


def check_terminal_transition(old_stage, new_stage):
    """终态不回退：原阶段已是终态时禁止再改阶段。

    终态记录仍可更新备注等其他字段（挂了之后仍想记一句话），
    但「当前阶段」一旦落入终态即锁定。返回错误列表，空列表表示通过。
    """
    if not old_stage or not new_stage:
        return []
    if old_stage in TERMINAL_STAGES and new_stage != old_stage:
        return ["记录已处于终态 `%s`，不能再改阶段（如需重新投递，请新建一条记录）" % old_stage]
    return []


def check_reason_required(stage, reason):
    """终态必填原因：阶段属终态而原因为空则报错。正常流转阶段选填。"""
    if stage in TERMINAL_STAGES and not (reason or "").strip():
        return ["进入终态 `%s` 时必须填写「状态原因」" % stage]
    return []


def find_duplicate(rows, company, role):
    """canonical 去重：按 (公司, 岗位) trim + 大小写不敏感匹配。

    返回 (既有行, 该行是否终态)；找不到返回 (None, False)。
    调用方据此决定：非终态则拒绝（409），终态则放行（允许挂了之后再投一次）。
    """
    c = (company or "").strip().lower()
    r = (role or "").strip().lower()
    if not c or not r:
        return None, False
    for row in rows:
        if ((row.get("公司") or "").strip().lower() == c
                and (row.get("岗位") or "").strip().lower() == r):
            return row, (row.get("当前阶段") or "") in TERMINAL_STAGES
    return None, False


def cmd_add(args):
    errors = []

    if not args.company:
        errors.append("`--company` 不能为空")
    if not args.role:
        errors.append("`--role` 不能为空")

    errs = check_direction(args.direction)
    if errs:
        errors.extend(errs)
    if args.batch not in BATCHES:
        errors.append("`--batch` 必须是 %s 之一，实际为 `%s`" % ("/".join(BATCHES), args.batch))
    if args.source and args.source not in SOURCES:
        errors.append("`--source` 必须是 %s 之一，实际为 `%s`" % ("/".join(SOURCES), args.source))

    if args.stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一，实际为 `%s`"
                      % ("/".join(STAGES + TERMINAL_STAGES), args.stage))

    for value, label in ((args.deadline, "截止日期"),
                         (args.applied, "投递日期"),
                         (args.next_date, "下次动作日期")):
        errs = check_date(value, label)
        if errs:
            errors.extend(errs)

    if args.score is not None:
        if not (0 <= args.score <= 100):
            errors.append("`--score` 必须在 0–100 之间，实际为 %d" % args.score)

    # 终态必须填原因
    errors.extend(check_reason_required(args.stage, args.reason))

    rows = read_rows()

    # canonical 去重：同公司+岗位且既有记录非终态则拒绝
    dup, dup_is_terminal = find_duplicate(rows, args.company, args.role)
    if dup and not dup_is_terminal:
        errors.append("已存在相同公司+岗位的记录 `%s`（当前阶段：%s），请勿重复录入"
                      % (dup.get("id", ""), dup.get("当前阶段", "")))

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    new_id = next_id(rows)
    row = {field: "" for field in FIELDS}
    row.update({
        "id": new_id,
        "公司": args.company,
        "岗位": args.role,
        "方向": args.direction,
        "批次": args.batch,
        "来源": args.source or "",
        "截止日期": args.deadline or "",
        "投递日期": args.applied or "",
        "当前阶段": args.stage,
        "状态原因": args.reason or "",
        "下次动作": args.next or "",
        "下次动作日期": args.next_date or "",
        "简历版本": args.resume or "",
        "评分": "" if args.score is None else str(args.score),
        "归档目录": args.archive or "",
        "备注": args.note or "",
    })
    rows.append(row)
    write_rows(rows)
    # 时间线：新建也入账，作为停留天数与首次活动的基准
    append_history([{"id": new_id, "字段": "创建", "原值": "",
                     "新值": "%s %s（%s）" % (args.company, args.role, args.stage)}])

    print("## 已写入\n")
    print("| 字段 | 值 |")
    print("|---|---|")
    for field in FIELDS:
        if row[field]:
            print("| %s | %s |" % (field, row[field]))
    print("\n归档目录建议：`05_投递追踪/applications/%s_%s`" % (args.company, args.role))
    return 0


def cmd_update(args):
    rows = read_rows()
    target = None
    for row in rows:
        if (row.get("id") or "").strip() == args.id:
            target = row
            break

    if target is None:
        print("错误：找不到 id 为 `%s` 的记录" % args.id)
        return 1

    errors = []
    if args.stage and args.stage not in STAGES + TERMINAL_STAGES:
        errors.append("`--stage` 必须是 %s 之一" % "/".join(STAGES + TERMINAL_STAGES))
    if args.score is not None and not (0 <= args.score <= 100):
        errors.append("`--score` 必须在 0–100 之间")
    for value, label in ((args.next_date, "下次动作日期"),
                         (args.applied, "投递日期"),
                         (args.deadline, "截止日期")):
        errs = check_date(value, label)
        if errs:
            errors.extend(errs)

    # 终态不回退：原阶段已是终态时不可再改阶段
    if args.stage:
        errors.extend(check_terminal_transition(target.get("当前阶段", ""), args.stage))

    # 终态必填原因：按更新后的最终阶段与最终原因判定
    final_stage = args.stage or target.get("当前阶段", "")
    final_reason = args.reason if args.reason is not None else target.get("状态原因", "")
    errors.extend(check_reason_required(final_stage, final_reason))

    if errors:
        print("## 校验失败\n")
        for e in errors:
            print("- %s" % e)
        print("\n未写入 CSV。")
        return 1

    changes = []
    before = dict(target)
    mapping = [
        ("当前阶段", args.stage), ("状态原因", args.reason), ("下次动作", args.next),
        ("下次动作日期", args.next_date), ("备注", args.note),
        ("投递日期", args.applied), ("截止日期", args.deadline),
    ]
    for field, value in mapping:
        if value is not None:
            old = target.get(field, "")
            target[field] = value
            changes.append("| %s | %s | %s |" % (field, old or "（空）", value or "（空）"))
    if args.score is not None:
        old = target.get("评分", "")
        target["评分"] = str(args.score)
        changes.append("| 评分 | %s | %d |" % (old or "（空）", args.score))

    if not changes:
        print("没有提供任何要更新的字段。可更新字段：%s" % "、".join(UPDATABLE))
        return 1

    write_rows(rows)
    append_history(diff_entries(args.id, before, target))
    print("## 已更新 %s（%s %s）\n" % (args.id, target.get("公司", ""), target.get("岗位", "")))
    print("| 字段 | 原值 | 新值 |")
    print("|---|---|---|")
    for line in changes:
        print(line)
    return 0


def format_table(rows):
    if not rows:
        return "（无匹配记录）"
    lines = []
    header = ["id", "公司", "岗位", "方向", "批次", "当前阶段", "截止日期", "下次动作", "下次动作日期", "评分"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        lines.append("| " + " | ".join(
            (row.get(h) or "") for h in header
        ) + " |")
    return "\n".join(lines)


def filter_rows(rows, args):
    result = rows
    if getattr(args, "stage", None):
        result = [r for r in result if r.get("当前阶段") == args.stage]
    if getattr(args, "direction", None):
        result = [r for r in result if r.get("方向") == args.direction]
    if getattr(args, "batch", None):
        result = [r for r in result if r.get("批次") == args.batch]
    if getattr(args, "company", None):
        result = [r for r in result if args.company in (r.get("公司") or "")]
    return result


def sort_key(row):
    """活跃记录在前、终态在后；按下次动作日期升序，空日期排最后。

    提升为模块级函数，供 CLI 与 Web 共用同一排序规则——
    两处各写一份迟早会不一致。
    """
    terminal = 1 if row.get("当前阶段") in TERMINAL_STAGES else 0
    nd = (row.get("下次动作日期") or "").strip()
    return (terminal, "9999" if not nd else nd, row.get("id", ""))


def cmd_list(args):
    if getattr(args, "direction", None):
        errs = check_direction(args.direction)
        if errs:
            print("## 校验失败\n")
            for e in errs:
                print("- %s" % e)
            return 1

    rows = read_rows()
    if not rows:
        print("追踪表为空。用 `tracker.py add` 添加第一条记录。")
        return 0

    result = filter_rows(rows, args)

    due_within = getattr(args, "due_within", None)
    if due_within is not None:
        from datetime import date, timedelta
        today = date.today()
        limit = today + timedelta(days=due_within)
        kept = []
        for r in result:
            for field in ("下次动作日期", "截止日期"):
                raw = (r.get(field) or "").strip()
                if DATE_RE.match(raw):
                    y, m, d = (int(x) for x in raw.split("-"))
                    if today <= date(y, m, d) <= limit:
                        kept.append(r)
                        break
        result = kept

    result.sort(key=sort_key)

    print("## 共 %d 条（总记录 %d 条）\n" % (len(result), len(rows)))
    print(format_table(result))
    return 0


def cmd_show(args):
    rows = read_rows()
    for row in rows:
        if (row.get("id") or "").strip() == args.id:
            print("## %s %s（%s）\n" % (row.get("公司", ""), row.get("岗位", ""), args.id))
            print("| 字段 | 值 |")
            print("|---|---|")
            for field in FIELDS:
                print("| %s | %s |" % (field, row.get(field, "") or "（空）"))
            return 0
    print("错误：找不到 id 为 `%s` 的记录" % args.id)
    return 1


def cmd_history(args):
    entries = read_history(app_id=args.id)
    if not entries:
        print("（暂无变更记录%s）" % ("：%s" % args.id if args.id else ""))
        return 0

    # 倒序展示：最近的变更在最上面
    entries = list(reversed(entries))
    if args.limit and args.limit > 0:
        entries = entries[:args.limit]

    print("## 变更时间线（共 %d 条）\n" % len(entries))
    print("| 时间 | id | 字段 | 原值 | 新值 |")
    print("|---|---|---|---|---|")
    for e in entries:
        print("| %s | %s | %s | %s | %s |" % (
            e.get("时间", ""), e.get("id", ""), e.get("字段", ""),
            e.get("原值", "") or "（空）", e.get("新值", "") or "（空）"))
    return 0


def cmd_contact(args):
    """招聘方联系人：跟进有节奏的招聘流程靠它维系。"""
    if args.action == "add":
        rows = read_contacts()

        link = (args.app or "").strip()
        if link:
            main_rows = read_rows()
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                print("错误：找不到记录 `%s`" % link)
                return 1

        if not (args.name or "").strip():
            print("错误：--name 必填")
            return 1

        row = {field: "" for field in CONTACT_FIELDS}
        row["联系人id"] = next_contact_id(rows)
        row["关联记录"] = link
        row["姓名"] = args.name.strip()
        row["角色"] = args.role or ""
        row["公司"] = args.company or ""
        row["联系方式"] = args.contact or ""
        row["来源"] = args.source or ""
        row["最近联系"] = args.last or ""
        row["下次跟进"] = args.next_follow or ""
        row["备注"] = args.note or ""
        rows.append(row)
        write_contacts(rows)
        print("已记录联系人 %s：%s" % (row["联系人id"], row["姓名"]))
        return 0

    if args.action == "list":
        rows = read_contacts(app_id=args.app)
        if not rows:
            print("（暂无联系人）")
            return 0
        # 有下次跟进日期的置顶（按日期升序，最该跟进的在前），其余按姓名
        rows.sort(key=lambda r: (
            (r.get("下次跟进") or "9999-99-99"),
            r.get("姓名", "")))
        print("## 联系人（共 %d 条）\n" % len(rows))
        print("| id | 姓名 | 角色 | 公司 | 下次跟进 | 备注 |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s |" % (
                r.get("联系人id", ""), r.get("姓名", ""), r.get("角色", "") or "—",
                r.get("公司", "") or "—", r.get("下次跟进", "") or "—",
                r.get("备注", "") or ""))
        return 0

    if args.action == "show":
        rows = read_contacts()
        row = find_contact(rows, args.id)
        if not row:
            print("错误：找不到联系人 `%s`" % args.id)
            return 1
        for field in CONTACT_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        rows = read_contacts()
        row = find_contact(rows, args.id)
        if not row:
            print("错误：找不到联系人 `%s`" % args.id)
            return 1
        changed = []
        for arg_name, field in (
            ("role", "角色"), ("contact", "联系方式"), ("source", "来源"),
            ("last", "最近联系"), ("next_follow", "下次跟进"), ("note", "备注"),
        ):
            value = getattr(args, arg_name, None)
            if value is not None:
                changed.append(field)
                row[field] = value
        if not changed:
            print("没有字段变化，未写入")
            return 0
        write_contacts(rows)
        print("已更新联系人 %s：%s" % (args.id, "、".join(changed)))
        return 0

    return 1


def cmd_offer(args):
    """Offer 已知事实：只记录，不判断——选择是多目标决策，由用户自己做。"""
    if args.action == "add":
        rows = read_offers()

        link = (args.app or "").strip()
        company = (args.company or "").strip()
        if link:
            main_rows = read_rows()
            src = next((r for r in main_rows
                        if (r.get("id") or "").strip() == link), None)
            if src is None:
                print("错误：找不到记录 `%s`" % link)
                return 1
            company = company or src.get("公司", "")
        elif not company:
            print("错误：未关联记录时必须给 --company")
            return 1

        row = {field: "" for field in OFFER_FIELDS}
        row["offer_id"] = next_offer_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = args.role or ""
        row["薪资构成"] = args.salary or ""
        row["月薪"] = args.monthly or ""
        row["年终"] = args.bonus or ""
        row["签字费"] = args.signon or ""
        row["股票期权"] = args.equity or ""
        row["工作地点"] = args.location or ""
        row["答复截止日"] = args.deadline or ""
        row["其他条件"] = args.conditions or ""
        row["备注"] = args.note or ""
        rows.append(row)
        write_offers(rows)

        # 拿到 offer 是岗位推进的关键里程碑，入账时间线
        if link:
            append_history([{
                "id": link,
                "字段": "offer",
                "原值": "",
                "新值": "%s（%s）" % (row["offer_id"], row["答复截止日"] or "答复截止待定"),
            }])

        print("已记录 offer %s：%s" % (row["offer_id"], company))
        return 0

    if args.action == "list":
        rows = read_offers(app_id=args.app)
        if not rows:
            print("（暂无 offer 记录）")
            return 0
        # 按答复截止日升序：越先要答复的越靠前
        rows.sort(key=lambda r: (r.get("答复截止日") or "9999-99-99"))
        print("## Offer（共 %d 条）\n" % len(rows))
        print("| id | 公司 | 岗位 | 月薪 | 答复截止 |")
        print("|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s |" % (
                r.get("offer_id", ""), r.get("公司", ""), r.get("岗位", "") or "—",
                r.get("月薪", "") or "—", r.get("答复截止日", "") or "—"))
        return 0

    if args.action == "show":
        rows = read_offers()
        row = find_offer(rows, args.id)
        if not row:
            print("错误：找不到 offer `%s`" % args.id)
            return 1
        for field in OFFER_FIELDS:
            print("**%s**：%s" % (field, row.get(field, "") or "（空）"))
        return 0

    if args.action == "update":
        rows = read_offers()
        row = find_offer(rows, args.id)
        if not row:
            print("错误：找不到 offer `%s`" % args.id)
            return 1
        changed = []
        for arg_name, field in (
            ("salary", "薪资构成"), ("monthly", "月薪"), ("bonus", "年终"),
            ("signon", "签字费"), ("equity", "股票期权"), ("location", "工作地点"),
            ("deadline", "答复截止日"), ("conditions", "其他条件"), ("note", "备注"),
        ):
            value = getattr(args, arg_name, None)
            if value is not None:
                changed.append(field)
                row[field] = value
        if not changed:
            print("没有字段变化，未写入")
            return 0
        write_offers(rows)
        print("已更新 offer %s：%s" % (args.id, "、".join(changed)))
        return 0

    return 1


def cmd_check(args):
    """schema 自检：只读扫描，坏文件隔离，问题清单可直接照着修。"""
    result = run_check()

    print("## schema 自检（v%d）\n" % result["version"])
    if result["versionNote"]:
        print("> %s\n" % result["versionNote"])

    for f in result["files"]:
        status = "通过" if f["ok"] else "异常"
        note = f.get("note") or ""
        print("- **%s**：%s%s" % (f["file"], status,
                                  ("（%s）" % note) if note else ""))
        for issue in f["issues"]:
            print("  - %s" % issue)
    print("")

    if result["quarantined"]:
        print("## 已隔离文件\n")
        for q in result["quarantined"]:
            print("- %s → `%s`（原因：%s）" % (
                q["file"], q["moved_to"], q["error"]))
        print("")
        print("隔离的文件不会参与任何读写。修复后可改名放回，"
              "或从快照备份恢复。")
        return 1
    if not result["ok"]:
        print("存在问题行，按上面清单修正。")
        return 1
    print("全部通过。")
    return 0


def cmd_interview(args):
    """面试记录：投递之后的每一次交流都记下来，复盘是唯一能复利的部分。"""
    action = args.action

    if action == "add":
        rows = read_interviews()
        main_rows = read_rows()

        # 关联记录非空时必须存在，避免指到不存在的岗位
        link = (args.app or "").strip()
        if link:
            if not any((r.get("id") or "").strip() == link for r in main_rows):
                print("错误：找不到记录 `%s`，先 tracker.py add 或省略 --app" % link)
                return 1
            # 未指定公司/岗位时，从主表带出，保证列表可读
            src = next(r for r in main_rows if (r.get("id") or "").strip() == link)
            company = args.company or src.get("公司", "")
            role = args.role or src.get("岗位", "")
        else:
            if not args.company:
                print("错误：未关联记录时必须给 --company")
                return 1
            company = args.company
            role = args.role or ""

        row = {field: "" for field in INTERVIEW_FIELDS}
        row["面试id"] = next_interview_id(rows)
        row["关联记录"] = link
        row["公司"] = company
        row["岗位"] = role
        row["轮次"] = args.round
        row["面试时间"] = args.when or ""
        row["形式"] = args.form or ""
        row["面试官"] = args.interviewer or ""
        row["问题记录"] = args.questions or ""
        row["我的回答要点"] = args.answers or ""
        row["复盘与改进"] = args.retro or ""
        row["结果"] = args.result

        rows.append(row)
        write_interviews(rows)

        # 面试也入账时间线：它是岗位推进的一部分，事后要能回溯
        if link:
            append_history([{
                "id": link,
                "字段": "面试",
                "原值": "",
                "新值": "%s %s（%s）" % (row["轮次"], row["面试时间"] or "时间待定",
                                     row["面试id"]),
            }])

        print("已记录面试 %s：%s %s %s" % (row["面试id"], company, role, args.round))
        return 0

    if action == "list":
        rows = read_interviews(app_id=args.app)
        if args.result:
            rows = [r for r in rows if (r.get("结果") or "").strip() == args.result]
        if not rows:
            print("（暂无面试记录）")
            return 0
        # 按面试时间倒序（最近的在前），空时间排最后
        rows.sort(key=lambda r: (r.get("面试时间") or ""), reverse=True)
        print("## 面试记录（共 %d 条）\n" % len(rows))
        print("| id | 公司 | 岗位 | 轮次 | 时间 | 形式 | 结果 |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("面试id", ""), r.get("公司", ""), r.get("岗位", ""),
                r.get("轮次", ""), r.get("面试时间", "") or "待定",
                r.get("形式", "") or "—", r.get("结果", "")))
        return 0

    if action == "show":
        rows = read_interviews()
        row = find_interview(rows, args.id)
        if not row:
            print("错误：找不到面试 `%s`" % args.id)
            return 1
        print("## %s %s · %s（%s）\n" % (
            row.get("公司", ""), row.get("岗位", ""), row.get("轮次", ""), args.id))
        for field in INTERVIEW_FIELDS:
            print("**%s**：%s\n" % (field, row.get(field, "") or "（空）"))
        return 0

    if action == "update":
        rows = read_interviews()
        row = find_interview(rows, args.id)
        if not row:
            print("错误：找不到面试 `%s`" % args.id)
            return 1
        changed = []
        for arg_name, field in (
            ("when", "面试时间"), ("round", "轮次"), ("form", "形式"),
            ("interviewer", "面试官"), ("questions", "问题记录"),
            ("answers", "我的回答要点"), ("retro", "复盘与改进"),
            ("result", "结果"),
        ):
            value = getattr(args, arg_name, None)
            if value is None:
                continue
            if row.get(field, "") != value:
                changed.append(field)
                row[field] = value
        if not changed:
            print("没有字段变化，未写入")
            return 0
        write_interviews(rows)
        print("已更新面试 %s：%s" % (args.id, "、".join(changed)))
        return 0

    print("错误：未知动作 %s" % action)
    return 1


def build_parser():
    parser = argparse.ArgumentParser(description="投递追踪表增删查改")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="新增投递记录")
    p_add.add_argument("--company", required=True, help="公司")
    p_add.add_argument("--role", required=True, help="岗位")
    # 不在 argparse 层写死 choices：合法方向取决于工作区装入的插件，
    # 交给 check_direction() 在运行时校验，才能给出「可用方向」的具体提示
    p_add.add_argument("--direction", required=True, help="方向 ID，取决于装入的领域插件")
    p_add.add_argument("--batch", required=True, choices=BATCHES, help="批次")
    p_add.add_argument("--source", choices=SOURCES, help="来源")
    p_add.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_add.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_add.add_argument("--stage", default="待投", help="当前阶段")
    p_add.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_add.add_argument("--next", dest="next", help="下次动作")
    p_add.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_add.add_argument("--resume", help="简历版本")
    p_add.add_argument("--score", type=int, help="评分 0-100")
    p_add.add_argument("--archive", help="归档目录相对路径")
    p_add.add_argument("--note", help="备注")

    p_upd = sub.add_parser("update", help="更新记录")
    p_upd.add_argument("--id", required=True, help="记录 id，如 A001")
    p_upd.add_argument("--stage", help="当前阶段")
    p_upd.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_upd.add_argument("--next", dest="next", help="下次动作")
    p_upd.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_upd.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_upd.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_upd.add_argument("--note", help="备注")
    p_upd.add_argument("--score", type=int, help="评分 0-100")

    # 方向选项取决于工作区装入的插件，此处不在定义时写死，
    # 改为在 cmd_list 中校验，以便给出「可用方向」的具体提示
    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--stage", help="按阶段过滤")
    p_list.add_argument("--direction", help="按方向过滤")
    p_list.add_argument("--batch", choices=BATCHES, help="按批次过滤")
    p_list.add_argument("--company", help="按公司名模糊过滤")
    p_list.add_argument("--due-within", dest="due_within", type=int,
                        help="只看未来 N 天内到期（下次动作日期或截止日期）")

    p_show = sub.add_parser("show", help="查看单条记录")
    p_show.add_argument("--id", required=True, help="记录 id")

    p_hist = sub.add_parser("history", help="查看变更时间线")
    p_hist.add_argument("--id", help="只看某条记录，省略则看全部")
    p_hist.add_argument("--limit", type=int, help="只显示最近 N 条")

    p_itv = sub.add_parser("interview", help="面试记录与复盘（add/list/show/update）")
    p_itv.add_argument("action", choices=["add", "list", "show", "update"])
    p_itv.add_argument("--id", help="面试 id（show/update 必填，如 I001）")
    p_itv.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_itv.add_argument("--company", help="公司（未关联记录时必填）")
    p_itv.add_argument("--role", help="岗位")
    p_itv.add_argument("--round", dest="round", choices=INTERVIEW_ROUNDS,
                       default="一面", help="轮次，默认一面")
    # 面试时间允许「2026-09-05 14:00」或只有日期，故不套 DATE_RE
    p_itv.add_argument("--when", help="面试时间，如 2026-09-05 14:00")
    p_itv.add_argument("--form", choices=INTERVIEW_FORMS, help="形式")
    p_itv.add_argument("--interviewer", help="面试官")
    p_itv.add_argument("--questions", help="问题记录")
    p_itv.add_argument("--answers", help="我的回答要点")
    p_itv.add_argument("--retro", help="复盘与改进")
    p_itv.add_argument("--result", choices=INTERVIEW_RESULTS, default="待定",
                       help="结果，默认待定")

    p_ct = sub.add_parser("contact", help="招聘方联系人（add/list/show/update）")
    p_ct.add_argument("action", choices=["add", "list", "show", "update"])
    p_ct.add_argument("--id", help="联系人 id（show/update 必填，如 C001）")
    p_ct.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_ct.add_argument("--name", help="姓名（add 必填）")
    p_ct.add_argument("--role", help="角色（HR/技术面/猎头…）")
    p_ct.add_argument("--company", help="公司")
    p_ct.add_argument("--contact", help="联系方式")
    p_ct.add_argument("--source", help="来源（BOSS/内推/官网…）")
    p_ct.add_argument("--last", help="最近联系 YYYY-MM-DD")
    p_ct.add_argument("--next-follow", dest="next_follow", help="下次跟进 YYYY-MM-DD")
    p_ct.add_argument("--note", help="备注")

    p_off = sub.add_parser("offer", help="Offer 事实记录（add/list/show/update）")
    p_off.add_argument("action", choices=["add", "list", "show", "update"])
    p_off.add_argument("--id", help="offer id（show/update 必填，如 O001）")
    p_off.add_argument("--app", help="关联的记录 id，可省略")
    p_off.add_argument("--company", help="公司（未关联记录时必填）")
    p_off.add_argument("--role", help="岗位")
    p_off.add_argument("--salary", help="薪资构成（如 月薪x14 + 年终x2）")
    p_off.add_argument("--monthly", help="月薪")
    p_off.add_argument("--bonus", help="年终")
    p_off.add_argument("--signon", help="签字费")
    p_off.add_argument("--equity", help="股票期权")
    p_off.add_argument("--location", help="工作地点")
    p_off.add_argument("--deadline", help="答复截止日 YYYY-MM-DD")
    p_off.add_argument("--conditions", help="其他条件")
    p_off.add_argument("--note", help="备注")

    sub.add_parser("check", help="schema 自检：列完整性、枚举、外键、坏文件隔离")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    global WORKSPACE
    WORKSPACE = os.path.abspath(args.workspace)
    if not os.path.isdir(WORKSPACE):
        print("错误：工作区不存在 %s" % WORKSPACE)
        print("先运行 python tools/init_workspace.py 初始化。")
        return 1

    if not args.cmd:
        parser.print_help()
        return 1

    handlers = {
        "add": cmd_add,
        "update": cmd_update,
        "list": cmd_list,
        "show": cmd_show,
        "history": cmd_history,
        "interview": cmd_interview,
        "contact": cmd_contact,
        "offer": cmd_offer,
        "check": cmd_check,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
