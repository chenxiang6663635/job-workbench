# -*- coding: utf-8 -*-
"""岗位池改名：`os.rename` + JD原文.md 首行标题同步（2026-09-21 批 D 数据安全网）。

为什么与 `job_dirs.py`（删除）分家：两个操作共享目录件（名字生成 / 路径守卫 /
文件清单），但改名的独有面（新名冲突双检、JD 首行同步）自成一摊——分开各自
守规模预算，共享件留在 `job_dirs`（同包兄弟直接取私有名，与
`tracker/application_delete.py` 共用 `deletes` 工具是同一先例）。

改名可逆（再改回来即可），所以**不做目录快照**——留痕纪律花在真正不可逆的
删除上；但预览与文件清单核对照旧（外部编辑器 / 同步工具改过目录就整体拒绝）。
"""

import io
import os

from . import job_dirs  # noqa: E402  （共享件：名字 / 路径守卫 / 文件清单）
from . import tracker  # noqa: E402
from . import workspace_io  # noqa: E402

JD_FILE = job_dirs.JD_FILE


def _jd_title_update(job_dir, new_name):
    """JD原文.md 首行是否可同步为 `# 新公司 新岗位`；返回 (need, old_line, new_line)。

    只在首行确实是 `# ` 标题时替换——JD 是应用自己写的（create_job / fetch_jd
    都写 `# 公司 岗位` 开头），所以这是可确定性更新；用户后来手动改过格式就
    不动它（宁可不改，不猜）。
    """
    jd_path = os.path.join(job_dir, JD_FILE)
    if not os.path.isfile(jd_path):
        return False, None, None
    try:
        with io.open(jd_path, "r", encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return False, None, None
    if not first.startswith("# "):
        return False, None, None
    company, role = job_dirs.split_dir_name(new_name)
    return True, first.rstrip("\r\n"), "# %s %s" % (company, role)


def preview_rename_job(name, new_company, new_role, workspace=None):
    """预览改名（**不落盘**）：目录名 `旧 → 新`；JD 首行标题可同步时一并列出。"""
    name, error = job_dirs._safe_name(name)
    if error:
        return [error], None
    ws = tracker.resolve_ws(workspace)
    job_dir, error = job_dirs._checked_dir(ws, name)
    if error:
        return [error], None
    if not os.path.isdir(job_dir):
        return ["找不到岗位目录：%s" % name], None
    new_name, error = job_dirs.build_dir_name(new_company, new_role)
    if error:
        return [error], None
    if new_name == name:
        return ["新旧目录名相同（%s）——没有可执行的改名" % name], None
    new_dir, error = job_dirs._checked_dir(ws, new_name)
    if error:
        return [error], None
    if os.path.exists(new_dir):
        return ["目标目录已存在：%s" % new_name], None
    files = job_dirs._dir_files(job_dir)
    need, old_line, new_line = _jd_title_update(job_dir, new_name)
    diff = ["- %s" % name, "+ %s" % new_name, ""]
    if files:
        diff.append("目录内文件（随目录改名，内容不动）：")
        for rel, size, _mtime in files:
            diff.append("- %s（%d 字节）" % (rel, size))
    else:
        diff.append("（目录为空）")
    if need:
        diff.append("")
        diff.append("JD原文.md 首行标题将同步：")
        diff.append("- %s" % old_line)
        diff.append("+ %s" % new_line)
    plan = {
        "payload": {"name": name, "new_name": new_name, "files": files},
        "summary": "改名：%s → %s" % (name, new_name),
        "diff": diff,
        "targets": [job_dir],
    }
    return [], plan


def apply_approved_job_rename(payload, workspace=None):
    """改名：锁内双检（原名在、新名未被占）+ 文件清单核对 → rename → 同步 JD 首行。

    JD 同步在 rename **之后**做（文件在新路径下），失败不回滚——改名已成事实，
    回滚会让"到底改没改"更难解释；失败如实写进 summary 的括注，请用户手动改。
    """
    name, error = job_dirs._safe_name(payload.get("name"))
    new_name, error2 = job_dirs._safe_name(payload.get("new_name"))
    expected = payload.get("files")
    if error or error2:
        raise tracker.ConflictError("%s（请重新预览）" % (error or error2))
    if not isinstance(expected, list):
        raise tracker.ConflictError("载荷里没有文件清单（请重新预览）")
    ws = tracker.resolve_ws(workspace)
    old_dir, error = job_dirs._checked_dir(ws, name)
    new_dir, error2 = job_dirs._checked_dir(ws, new_name)
    if error or error2:
        raise tracker.ConflictError("%s（请重新预览）" % (error or error2))
    note = ""
    with tracker.file_lock(job_dirs._lock_path(ws)):
        if not os.path.isdir(old_dir):
            raise tracker.ConflictError("预览之后原目录不在了（请重新预览）")
        if os.path.exists(new_dir):
            raise tracker.ConflictError("预览之后目标目录名被占用了（请重新预览）")
        if job_dirs._dir_files(old_dir) != expected:
            raise tracker.ConflictError(
                "预览之后目录内容有变化，已放弃本次改名——请重新预览")
        os.rename(old_dir, new_dir)
        # 同步 JD 首行标题（改名已成事实；同步失败如实回报而不是回滚）
        need, old_line, new_line = _jd_title_update(new_dir, new_name)
        if need:
            try:
                jd_path = os.path.join(new_dir, JD_FILE)
                with io.open(jd_path, "r", encoding="utf-8") as handle:
                    text = handle.read()
                text = text.replace(old_line, new_line, 1)
                workspace_io.atomic_write_text(jd_path, text, encoding="utf-8")
            except OSError as exc:
                note = "（JD 首行标题未能同步：%s，请手动修改）" % exc
    return {"id": new_name, "written": 1,
            "summary": "已改名：%s → %s%s" % (name, new_name, note)}
