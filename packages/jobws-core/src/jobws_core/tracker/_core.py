# -*- coding: utf-8 -*-
"""基座：应用/数据根、工作区解析、原子写与锁、通用校验小工具、时间线 ID 等。

（由 tools/tracker.py 拆出；2026-09-16 重构批。2026-09-19 批 6 第二批从仓库的
`tools/tracker/` 搬进本包——旧路径留转发 shim，对外经包门面 re-export，
引用方无需改动。）
"""

import csv
import io
import logging
import os
import re

from datetime import date, datetime


from jobws_core import pathres  # noqa: E402  （ROOT 由入口注入，见 pathres._APP_ROOT）
from jobws_core import workspace_io  # noqa: E402  （批 8：原子写与锁名收敛到共享原语）

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)




# ROOT 由**入口注入**（`pathres.set_app_root`）——本文件住 site-packages 之后，
# 任何「从 __file__ 上溯」的写法都指向安装目录的上层：层级数对了也是碰巧，
# 错了就静默把 DEFAULT_WORKSPACE 指到别处。注入是显式的，没有注入时
# `pathres.resolve_root()` 直接报错（完整论证见 tests/test_domain_root.py）。
ROOT = pathres.resolve_root()

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


# 方向 ID 取决于工作区装入的领域插件，不在脚本里写死。
# 校验时动态读取 <工作区>/config/directions/*.md，读不到则放行（只记录不拦截）。
DIRECTIONS = ["other"]

# 终态。注意语义差异：「已挂/已放弃」是被拒或放弃（失败），
# 「我拒绝的 offer」是用户主动拒绝（双向选择）——复盘归因时必须分开统计，
# 拒绝不该被算成"失败"，它可能意味着拿到了更好的。
TERMINAL_STAGES = ["已挂", "已放弃", "我拒绝的 offer"]


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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



def parse_iso_date(value):
    """解析 YYYY-MM-DD，非法返回 None。与 report.parse_date 同规则，
    但 tracker 不 import report（反向依赖：report 导入 tracker，避免循环）。
    """
    raw = (value or "").strip()
    if not DATE_RE.match(raw):
        return None
    y, m, d = (int(x) for x in raw.split("-"))
    try:
        return date(y, m, d)
    except ValueError:
        return None



# 临时文件前缀：同步工具（Syncthing / 网盘）可据此排除半成品
TMP_PREFIX = ".jobws_tmp_"



def _atomic_write_csv(path, rows, fieldnames, encoding):
    """原子写 CSV：写临时文件 → fsync → os.replace。

    utf-8-sig 写入时加 BOM，Excel 直接打开不乱码；
    restval 保证旧文件（缺新增列）写回时补出空列，避免 None 落盘成 "None"。
    """
    workspace_io.atomic_write_csv(path, rows, fieldnames, encoding=encoding)



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
    # 形状对了还要是**真日期**：`2026-02-31` 能过正则，入库后看板 parse_date
    # 直接抛 ValueError（整页 500），健康度静默失效——审计 P0-3 的根因。
    if parse_iso_date(value) is None:
        return ["`%s: %s` 不是有效日期（如 2 月没有 31 日）" % (label, value)]
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



def dedup_key(company, role):
    """(公司, 岗位) 的规范化键：trim + 大小写不敏感。

    单一事实源：去重、导入校验、岗位池联动三处共用同一口径。
    各写一份迟早漂移——一边判「重复」、另一边判「没投过」，用户会看到自相矛盾的结论。
    """
    return ((company or "").strip().lower(), (role or "").strip().lower())



def find_duplicate(rows, company, role):
    """canonical 去重：按 (公司, 岗位) trim + 大小写不敏感匹配。

    返回 (既有行, 该行是否终态)；找不到返回 (None, False)。
    调用方据此决定：非终态则拒绝（409），终态则放行（允许挂了之后再投一次）。
    """
    key = dedup_key(company, role)
    if not key[0] or not key[1]:
        return None, False
    for row in rows:
        if dedup_key(row.get("公司"), row.get("岗位")) == key:
            return row, (row.get("当前阶段") or "") in TERMINAL_STAGES
    return None, False



class ConflictError(RuntimeError):
    """预览与落盘之间数据变了，已确认的写入不再安全。

    领域层只抛它；协议层（tools/approval.py）把它转译成 ApprovalConflict——
    方向是单向的，领域代码不必知道"令牌"这回事。
    """



def _tracking_targets(workspace=None):
    """一次写类操作会落到的文件（供令牌绑定与预览展示）。"""
    ws = resolve_ws(workspace)
    return [os.path.join(ws, "05_投递追踪", "tracker.csv"),
            os.path.join(ws, "05_投递追踪", "history.csv")]



# 公开别名：MCP 包（另一棵树）要用它——跨包伸手拿下划线名是坏味道，
# 一旦这里改签名那边会静默失配（独立审查 m9）。
tracking_targets = _tracking_targets



def _lock_path(workspace=None):
    """写类操作的互斥锁文件：<工作区>/05_投递追踪/tracker.lock（与 Web 层同一把锁）。

    三个 apply_approved_* 在锁内做「读最新 → 重校验 → 写」整段——否则并发的
    两次落盘会各自算出同一个 next_id，后写覆盖前写（独立审查 M1）。锁文件所在
    目录按需创建：全新工作区第一次导入时它还不存在。建目录刻意留在**锁外**——
    makedirs 幂等，并发首建也无害（跨宿主审查 MINOR 确认过这一点）。
    """
    ws = resolve_ws(workspace)
    tracking_dir = os.path.join(ws, "05_投递追踪")
    os.makedirs(tracking_dir, exist_ok=True)
    return os.path.join(tracking_dir, "tracker.lock")
