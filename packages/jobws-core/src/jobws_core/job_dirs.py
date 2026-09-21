# -*- coding: utf-8 -*-
"""岗位池目录的破坏性操作：删除与改名（2026-09-21 批 D 数据安全网）。

岗位 = 目录：`01_岗位池/<公司>_<岗位>/`（含 JD原文.md、解析卡.md 与用户自己
添置的材料）。删除 = `shutil.rmtree`，所以留痕是**目录级**的——整个目录复制到
快照区（工作区之外），恢复 = 拷回 `01_岗位池/`；改名 = `os.rename`（可逆，
不做目录快照），并同步 JD原文.md 的首行标题（`# 公司 岗位`——只在首行确实是
标题时替换，其余内容一字不动）。

与 CSV 表删除（`tracker/deletes.py`）的关系：同一份纪律（预览优先 / 真删 /
留痕可恢复 / 写不出即中止），但载体不同（目录 vs 行），所以实现不共用泛型——
共享的是**语义**。目录名的生成与拆分（`build_dir_name` / `split_dir_name`）
以及「目录名 ↔ 追踪表」的匹配索引（`applications_by_key`）从 `routers/jobs.py`
搬来——单一事实源，web 层反手 import 本模块，两边不再各写一份互逆运算。
"""

import datetime
import io
import os
import shutil

from . import pathres  # noqa: E402  （快照根目录：**必须**在工作区之外）
from . import tracker  # noqa: E402  （工作区解析、dedup_key、ConflictError、file_lock）
from . import workspace_io  # noqa: E402

DIR_JOBS = "01_岗位池"

# 与 routers/jobs.py 的 DIR_JOBS 同源（一处改名要同步另一处；有测试钉住）
JD_FILE = "JD原文.md"

INVALID_DIR_CHARS = set('\\/:*?"<>|')


def build_dir_name(company, role):
    """公司 + 岗位 → 目录名；非法字符 / 空名返回 (None, 错误)（照着创建时的口径）。"""
    name = ("%s_%s" % ((company or "").strip(), (role or "").strip())).strip()
    bad = [c for c in name if c in INVALID_DIR_CHARS or ord(c) < 32]
    if bad:
        return None, "公司或岗位名含非法字符：%s" % "".join(sorted(set(bad)))
    # 全由 `_ . 空格` 组成视为空：两字段都空时拼出的 "_" 也不能当目录名
    #（创建路径有前置必填校验挡着，但改名预览会直接拿到这个结果——必须在这里堵）
    if not name.strip("_. "):
        return None, "目录名不能为空或纯点号"
    return name, None


def split_dir_name(name):
    """目录名 → (公司, 岗位)，与 `build_dir_name` 互为逆运算。

    取**首个**下划线切分（口径从 routers/jobs.py 原样搬来）：公司名自带下划线
    时会还原偏左——这是刻意选的可预测口径，宁可显示「未投递」也不要猜。
    """
    company, _, role = (name or "").partition("_")
    return company.strip(), role.strip()


def _safe_name(name):
    """目录名安全校验：无路径分隔 / 无上跳（防路径穿越），返回 (name, error)。"""
    name = (name or "").strip()
    if not name:
        return None, "缺少岗位目录名"
    if name in (".", "..") or "/" in name or "\\" in name or ":" in name:
        return None, "目录名不合法：%s" % name
    return name, None


def _checked_dir(ws, name):
    """name → 岗位目录绝对路径；越出岗位池（含 symlink / junction 读穿）返回 (None, error)。

    与只读端的 realpath 二次确认同款（`safe_join` 不解析符号链接）——删除 / 改名
    比读取更不可逆，这层不能省。
    """
    base = os.path.join(ws, DIR_JOBS)
    full = os.path.join(base, name)
    base_real = os.path.realpath(base)
    full_real = os.path.realpath(full)
    if full_real != base_real and not full_real.startswith(base_real + os.sep):
        return None, "目录越出岗位池：%s" % name
    return full, None


def _lock_path(workspace=None):
    """岗位池写锁：`<工作区>/01_岗位池/.jobs.lock`（与 create_job / fetch_jd 同一把）。"""
    ws = tracker.resolve_ws(workspace)
    base = os.path.join(ws, DIR_JOBS)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, ".jobs.lock")


def _dir_files(job_dir):
    """目录内全部文件的 `[相对路径, size, mtime_ns]` 清单（排序稳定）——目录指纹。

    为什么含 mtime：删除前要核"预览看到的还是现在这个目录"——新增 / 删除 /
    改大小都能被 size 捕获，纯内容微改由 mtime 兜住；察觉不到的改动也无损，
    因为快照本来就是删前实况（保的是最新版）。
    """
    out = []
    for dirpath, _dirnames, filenames in os.walk(job_dir):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, job_dir).replace("\\", "/")
            try:
                stat = os.stat(full)
            except OSError:
                continue
            out.append([rel, stat.st_size, stat.st_mtime_ns])
    out.sort(key=lambda item: item[0])
    return out


# ---- 目录名 ↔ 追踪表：匹配索引（从 routers/jobs.py 搬来，单一事实源）----------


def apply_state(row):
    """未投递 / 流程中 / 已终态——终态口径直接复用 tracker，不另立清单。"""
    if not row:
        return "未投递"
    stage = (row.get("当前阶段") or "").strip()
    if not stage:
        return "未投递"
    return "已终态" if stage in tracker.TERMINAL_STAGES else "流程中"


def applications_by_key(workspace=None):
    """`{dedup_key: row}` 索引，供岗位池按 (公司, 岗位) 查出投递状态。

    同键多行是合法数据（挂了再投一次）：保留仍在流程中的那行——状态展示要回答
    「这一岗现在走到哪了」，历史终态行不该盖住它。追踪表还不存在时返回空字典。
    """
    ws = tracker.resolve_ws(workspace)
    if not os.path.isdir(os.path.join(ws, "05_投递追踪")):
        return {}
    index = {}
    for row in tracker.read_rows(ws):
        key = tracker.dedup_key(row.get("公司"), row.get("岗位"))
        if not (key[0] and key[1]):
            continue
        old = index.get(key)
        if old is not None and apply_state(old) != "已终态" and apply_state(row) == "已终态":
            continue
        index[key] = row
    return index


def linked_applications(name, workspace=None):
    """所有 (公司, 岗位) 与目录名拆分匹配的追踪表行（删除预览列清单用）。"""
    ws = tracker.resolve_ws(workspace)
    if not os.path.isdir(os.path.join(ws, "05_投递追踪")):
        return []
    key = tracker.dedup_key(*split_dir_name(name))
    if not (key[0] and key[1]):
        return []
    return [row for row in tracker.read_rows(ws)
            if tracker.dedup_key(row.get("公司"), row.get("岗位")) == key]


# ---- 删除（预览 → 目录级快照 → rmtree）-------------------------------------


def trace_root(workspace=None):
    """删除留痕根：**工作区之外**（一个工作区一个 job-deletes 目录）。"""
    ws = tracker.resolve_ws(workspace)
    ws_name = os.path.basename(os.path.normpath(ws)) or "workspace"
    return os.path.join(pathres.snapshot_root(), ws_name, "job-deletes")


def _snapshot_dir(job_dir, workspace=None):
    """整目录 copytree 到快照区；写不出抛 ConflictError（中止删除）。

    copytree 失败时清理半成品 target——否则快照区里会留下一个看起来像快照、
    实际不完整的目录，那比没有更误导。
    """
    name = os.path.basename(os.path.normpath(job_dir))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    root = trace_root(workspace)
    target = os.path.join(root, "%s-%s" % (name, stamp))
    try:
        os.makedirs(root, exist_ok=True)
        shutil.copytree(job_dir, target)
    except OSError as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise tracker.ConflictError(
            "删除前的留痕写不出来（%s）——已中止，工作区未做任何改动" % exc)
    return target


def preview_delete_job(name, workspace=None):
    """预览删除一个岗位目录（**不落盘**）：列目录内全部文件 + 关联投递提示。

    文件清单不是装饰：删目录会连带用户的材料（简历附件、准备笔记），逐条列明
    是"将失去什么"的唯一事前告知。
    """
    name, error = _safe_name(name)
    if error:
        return [error], None
    ws = tracker.resolve_ws(workspace)
    job_dir, error = _checked_dir(ws, name)
    if error:
        return [error], None
    if not os.path.isdir(job_dir):
        return ["找不到岗位目录：%s" % name], None
    files = _dir_files(job_dir)
    linked = linked_applications(name, ws)
    diff = ["岗位目录：%s" % name, ""]
    if files:
        diff.append("目录内文件（将随目录一起删除；快照留档在工作区之外）：")
        for rel, size, _mtime in files:
            diff.append("- %s（%d 字节）" % (rel, size))
    else:
        diff.append("（目录为空）")
    if linked:
        diff.append("")
        diff.append("追踪表有 %d 条投递关联此岗位（删除岗位不影响它们）：" % len(linked))
        for row in linked:
            diff.append("- %s %s（%s，%s）"
                        % (row.get("公司") or "", row.get("岗位") or "",
                           row.get("id") or "", row.get("当前阶段") or "未填阶段"))
    plan = {
        "payload": {"name": name, "files": files},
        "summary": "删除岗位：%s（含 %d 个文件）" % (name, len(files)),
        "diff": diff,
        "targets": [job_dir],
    }
    return [], plan


def apply_approved_job_delete(payload, workspace=None):
    """删除岗位目录：锁内核对文件清单 → **先**目录级快照 → rmtree。

    顺序与 CSV 表删除一致：留痕先落地、写不出中止——"没有后路的删除"不执行。
    """
    name, error = _safe_name(payload.get("name"))
    expected = payload.get("files")
    if error:
        raise tracker.ConflictError("%s（请重新预览）" % error)
    if not isinstance(expected, list):
        raise tracker.ConflictError("载荷里没有文件清单（请重新预览）")
    ws = tracker.resolve_ws(workspace)
    job_dir, error = _checked_dir(ws, name)
    if error:
        raise tracker.ConflictError("%s（请重新预览）" % error)
    with tracker.file_lock(_lock_path(ws)):
        if not os.path.isdir(job_dir):
            raise tracker.ConflictError("预览之后目录不存在了（请重新预览）")
        if _dir_files(job_dir) != expected:
            raise tracker.ConflictError(
                "预览之后目录内容有变化（可能是编辑器 / 同步工具），已放弃本次删除——请重新预览")
        trace = _snapshot_dir(job_dir, ws)
        shutil.rmtree(job_dir)
    return {"id": name, "written": 1, "trace": trace,
            "summary": "已删除岗位：%s" % name}
