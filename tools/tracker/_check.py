# -*- coding: utf-8 -*-
"""schema 自检（run_check 家族）：列完整性、枚举、外键与坏文件隔离。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import csv
import io
import json
import logging
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from ._core import (TERMINAL_STAGES, _quarantine, _read_csv_checked, csv_path, parse_iso_date, resolve_ws)
from ._schema import (BATCHES, CONTACT_FILE, HISTORY_FILE, INTERVIEW_FILE, INTERVIEW_FORMS, INTERVIEW_RESULTS, INTERVIEW_ROUNDS, MAIL_DIRECTIONS, MAIL_FILE, MAIL_TAGS, OFFER_FILE, QUESTION_DIFFICULTY, QUESTION_FILE, QUESTION_ORIGINS, QUESTION_STATUS, SCHEMA_FILE, SOURCES, STAGES, TALK_ATTEND, TALK_FILE, TALK_FORMS, TRACKING_SCHEMA_VERSION)



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



def _ensure_schema_sidecar(tracking):
    """读 / 补写 schema sidecar，返回 (version, version_note)。

    sidecar 只是版本标记：写失败不影响自检的正确性（下次再试），但按
    「禁静默吞错」留日志（只记 errno 与人话——异常 str 自带绝对路径）。
    """
    schema_path = os.path.join(tracking, SCHEMA_FILE)
    version = TRACKING_SCHEMA_VERSION
    if os.path.isfile(schema_path):
        try:
            with io.open(schema_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            version = int(meta.get("version", TRACKING_SCHEMA_VERSION))
        except (ValueError, OSError, TypeError):
            version = TRACKING_SCHEMA_VERSION
        if version > TRACKING_SCHEMA_VERSION:
            return version, ("数据由更新版本的应用写入（schema v%d > v%d），"
                             "请升级应用后再操作" % (version, TRACKING_SCHEMA_VERSION))
        if version < TRACKING_SCHEMA_VERSION:
            return version, ("数据是旧版本（schema v%d），当前无破坏性变更，"
                             "无需迁移" % version)
        return version, None

    # 首次自检补写 sidecar（幂等）
    try:
        if not os.path.isdir(tracking):
            os.makedirs(tracking)
        with io.open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"version": TRACKING_SCHEMA_VERSION}, f)
    except OSError as exc:
        logger.warning("写 sidecar 失败：%s", exc.strerror or type(exc).__name__)
    return version, None



def _check_main_table(ws, files, quarantined):
    """自检主表 tracker.csv，返回它的 id 集合（其他文件的外键基准）。"""
    fk_ids = set()
    main_path = csv_path(ws)
    if not os.path.isfile(main_path):
        return fk_ids
    issues = []
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
        return fk_ids
    _check_file_rows(
        "tracker.csv", main_rows, main_path,
        required=["id", "公司", "岗位", "方向", "批次", "当前阶段"],
        dates=["截止日期", "投递日期", "下次动作日期"],
        # 方向不做枚举校验：合法方向取决于工作区装入的插件，动态的
        # 来源也在校验之列：CLI 与导入都会拦脏值，手改 CSV 绕过它们，
        # 自检是最后一道拦网（此前来源只在写入口校验，脏值无人拦）。
        enums=[("当前阶段", STAGES + TERMINAL_STAGES),
               ("批次", BATCHES),
               ("来源", SOURCES)],
        fk_ids=None, issues=issues)
    fk_ids = set((r.get("id") or "").strip() for r in main_rows)
    files.append({"file": "tracker.csv", "ok": not issues,
                  "issues": issues, "note": ""})
    return fk_ids



def _inspect_tracking_file(fname, tracking, ws, files, quarantined, fk_ids,
                           required, dates=(), enums=(), with_fk=False):
    """自检单个追踪表文件：不存在记「尚未创建」，坏文件隔离并记问题。"""
    path = os.path.join(tracking, fname)
    if not os.path.isfile(path):
        files.append({"file": fname, "ok": True, "issues": [], "note": "尚未创建"})
        return
    issues = []
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

    version, version_note = _ensure_schema_sidecar(tracking)
    # tracker.csv 先行：其他文件的外键以它的 id 集合为准
    fk_ids = _check_main_table(ws, files, quarantined)

    # 面试 / 宣讲会 / 邮件 / 题库 / 联系人 / offer / 时间线
    def inspect(fname, required, dates=(), enums=(), with_fk=False):
        _inspect_tracking_file(fname, tracking, ws, files, quarantined, fk_ids,
                               required, dates, enums, with_fk)

    inspect(INTERVIEW_FILE,
            required=["面试id"],          # 关联记录可空（内推等未录入的面试）
            enums=[("轮次", INTERVIEW_ROUNDS), ("形式", INTERVIEW_FORMS),
                   ("结果", INTERVIEW_RESULTS)],
            with_fk=True)          # 面试时间是宽松格式（可含 HH:MM），不套日期校验
    inspect(TALK_FILE,
            required=["宣讲会id"],        # 关联记录可空（还没投递的活动也能记）
            enums=[("形式", TALK_FORMS), ("是否参加", TALK_ATTEND)],
            with_fk=True)          # 时间同样是宽松格式，不套日期校验
    inspect(MAIL_FILE,
            required=["邮件id"],          # 消息id 可空（手工记录时未必拿得到）
            enums=[("方向", MAIL_DIRECTIONS), ("标签", MAIL_TAGS)],
            with_fk=True)          # 日期是宽松格式（可含 HH:MM），不套日期校验
    # 题库不挂外键：关联的是"公司名/岗位名"（自由文本，可能还没进投递表）
    inspect(QUESTION_FILE,
            required=["题目id"],
            enums=[("状态", QUESTION_STATUS), ("来源", QUESTION_ORIGINS),
                   ("难度", QUESTION_DIFFICULTY)],
            dates=["创建日期", "最近复习"],
            with_fk=False)
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
