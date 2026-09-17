# -*- coding: utf-8 -*-
"""系统能力：导出、快照备份、路径查询、打开数据目录。

这是本地优先应用的工程底座——功能不炫，但决定用户敢不敢把求职数据放进来：
- **导出 zip**：保留 Markdown/CSV/JSON 原格式，可脱离本应用独立阅读（反锁定）
- **快照备份**：存在**工作区之外**的系统目录（同盘同目录的备份等于没备份）
- **路径可见 + 无遥测声明**：让用户看得见数据在哪、确认没人上传

本路由只做编排与 IO，不碰业务规则（业务在 tools/）。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

import atomicio
import pathres
import tracker
from apierror import ApiError
from deps import workspace_dir

router = APIRouter(prefix="/api/system")

# 导出与快照都要排除的运行时产物
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git", ".codebuddy", ".venv"}
EXCLUDE_SUFFIX = {".lock", ".pyc", ".tmp"}
EXCLUDE_PREFIX = {atomicio.TMP_PREFIX, "."}

# 凭证类文件**不进**导出与快照：导出包可能被分享（求助/迁移），快照目录可能
# 落在云盘同步范围内——而这两个文件是明文凭证（邮箱授权码≈邮箱读取权限；
# API key≈计费凭证）。本清单是 `_iter_files` 的一部分，导出与备份共用。
# 新增任何"会存凭证"的文件时，必须加进来。
EXCLUDE_REL = {
    "config/imap.json",
    "config/provider.json",
}

# 时间机器式保留策略（照抄 Syncthing 的 staggered versioning）：
# 越近的快照越密，越老的越稀，避免备份无限膨胀
RETENTION_RULES = [
    # (时间窗口秒, 该窗口内保留的最小间隔秒)
    (3600, 30),              # 1 小时内：每 30 秒至多一份
    (86400, 3600),           # 1 天内：每小时至多一份
    (86400 * 30, 86400),     # 30 天内：每天至多一份
]
WEEKLY_INTERVAL = 86400 * 7  # 更老：每周至多一份


def _app_version():
    """应用版本（机器形态 YY.M.D，如 26.9.15）。

    打包版：主进程拉起后端时注入 JOBWS_APP_VERSION（= Electron app.getVersion()）；
    开发模式：回退读仓库 web/electron/package.json 的 version。
    两条都不可用时返回空串——「关于」区块据此显示「未知」，不编造版本。
    """
    injected = os.environ.get("JOBWS_APP_VERSION", "").strip()
    if injected:
        return injected
    from deps import ROOT  # 函数内 import：本模块别处不依赖 deps
    pkg = os.path.join(ROOT, "web", "electron", "package.json")
    try:
        with io.open(pkg, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return ""
    version = data.get("version") if isinstance(data, dict) else None
    return version.strip() if isinstance(version, str) else ""


def _snapshot_dir(ws):
    """该工作区的快照目录：<系统用户目录>/snapshots/<工作区名>/"""
    name = os.path.basename(os.path.normpath(ws)) or "workspace"
    return os.path.join(pathres.snapshot_root(), name)


def _iter_files(root):
    """遍历工作区内应纳入导出/备份的文件（排除运行时产物与访问凭证）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if any(name.startswith(p) for p in EXCLUDE_PREFIX):
                continue
            if os.path.splitext(name)[1].lower() in EXCLUDE_SUFFIX:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel in EXCLUDE_REL:
                continue
            yield full


def _prune(snapshots):
    """按时间机器策略淘汰旧快照。snapshots 为 (mtime, path) 列表，新的在前。"""
    kept = []
    for mtime, path in snapshots:
        age = None
        # 与已保留快照比较：落在同一窗口且间隔不足的淘汰
        for kept_mtime, _ in kept:
            delta = abs(kept_mtime - mtime)
            if delta > WEEKLY_INTERVAL:
                continue
            age = delta
            break
        if age is None:
            kept.append((mtime, path))
            continue
        # 找到所属窗口的最小间隔
        for window, interval in RETENTION_RULES:
            if age <= window:
                if age >= interval:
                    kept.append((mtime, path))
                break
        else:
            if age >= WEEKLY_INTERVAL:
                kept.append((mtime, path))
    return kept


def _apply_retention(snap_dir):
    """淘汰不符合保留策略的旧快照，返回 (保留数, 删除数)。"""
    if not os.path.isdir(snap_dir):
        return 0, 0
    entries = []
    for name in os.listdir(snap_dir):
        if not name.endswith(".zip"):
            continue
        full = os.path.join(snap_dir, name)
        entries.append((os.path.getmtime(full), full))
    # 新的在前
    entries.sort(key=lambda x: -x[0])

    keep_paths = {p for _, p in _prune(entries)}
    removed = 0
    for _, path in entries:
        if path not in keep_paths:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return len(entries) - removed, removed


@router.get("/check")
def system_check(ws: str = Depends(workspace_dir)):
    """schema 自检（P3）：列完整性、枚举、外键、坏文件隔离。

    复用 tracker.run_check（单一事实源）。坏文件已在 check 内被隔离到
    quarantine/，前端展示异常清单与隔离记录。
    """
    return tracker.run_check(ws)


@router.get("/paths")
def system_paths(ws: str = Depends(workspace_dir)):
    """数据在哪——让用户看得见。"""
    snap_dir = _snapshot_dir(ws)
    last = None
    if os.path.isdir(snap_dir):
        zips = [f for f in os.listdir(snap_dir) if f.endswith(".zip")]
        if zips:
            last = max(
                datetime.fromtimestamp(os.path.getmtime(os.path.join(snap_dir, f)))
                for f in zips
            ).strftime("%Y-%m-%d %H:%M:%S")

    # 「数据位置」卡片要用：数据根 + 当前模式。模式只有两种——便携（数据就在
    # 应用目录旁，解压/拷 U 盘即用）与用户目录（应用装在不可写位置时的回退）。
    from deps import ROOT, data_root  # 函数内 import：本模块别处不依赖 deps

    data_root_path = os.path.normpath(data_root())
    return {
        "workspace": ws,
        "dataRoot": data_root_path,
        "mode": "portable" if data_root_path == os.path.normpath(ROOT) else "user",
        "snapshotDir": snap_dir,
        "snapshotCount": len(
            [f for f in os.listdir(snap_dir) if f.endswith(".zip")]
        ) if os.path.isdir(snap_dir) else 0,
        "lastBackup": last,
        # 「关于」区块（时间戳体系 2026-09-15）：版本 / 运行平台。
        # 版本优先级：打包链注入的环境变量 → 仓库 package.json（开发模式）；
        # 两者都不可用时为空串，前端按"有则显示"处理。
        # 这里曾经还有 buildDate（读 JOBWS_BUILD_DATE），但全仓没有任何生产方
        # （打包链与 main.js 都不设置它）——死字段不留，已删（第二轨 MAJOR-2）。
        "appVersion": _app_version(),
        "platform": sys.platform,
        # 无遥测声明：本地优先产品的信任基石，UI 直接展示
        "telemetry": False,
        "note": "全部数据只存在你这台机器，无遥测、无上传。",
    }


@router.get("/export")
def export_workspace(ws: str = Depends(workspace_dir)):
    """整包导出 zip：保留 Markdown/CSV/JSON 原格式，可脱离本应用独立阅读。

    明确告知不包含什么——含糊承诺不如写清边界更能建立信任。
    """
    name = os.path.basename(os.path.normpath(ws)) or "workspace"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for full in _iter_files(ws):
            arcname = os.path.relpath(full, os.path.dirname(ws))
            zf.write(full, arcname)
            count += 1
        # 附一份说明，让 zip 离开应用后仍可自解释
        readme = (
            "求职工作台导出包\n"
            "生成时间：%s\n"
            "工作区：%s\n\n"
            "内容：数据文件（Markdown / CSV 等原始格式），可用任意编辑器或 Excel 打开，\n"
            "不需要本应用即可阅读。\n\n"
            "不包含：应用外的快照备份（在系统用户目录）、运行时临时文件与锁文件；\n"
            "也不包含邮箱授权码 / API key 等访问凭证（换机后在「设置」里重新填写）。\n"
            "注意：导出包含你的真实简历与个人信息，请妥善保管。\n"
        ) % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name)
        zf.writestr("README_导出说明.txt", readme)

    data = buf.getvalue()
    filename = "%s-%s.zip" % (name, stamp)
    # 中文文件名不能直接放 header（latin-1 会抛异常），用 RFC 5987 编码
    encoded = filename.encode("utf-8")
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=\"export.zip\"; filename*=UTF-8''%s"
            % "".join("%%%02X" % b for b in encoded)
        },
    )


@router.post("/backup")
def backup_workspace(ws: str = Depends(workspace_dir)):
    """快照备份到工作区之外，并按时间机器策略淘汰旧快照。"""
    snap_dir = _snapshot_dir(ws)
    if not os.path.isdir(snap_dir):
        os.makedirs(snap_dir)

    name = os.path.basename(os.path.normpath(ws)) or "workspace"
    # 精确到微秒：只用秒级时间戳的话，同一秒内的两次并发备份仍指向同一个临时
    # 文件（两个 ZipFile 同时写它，产物照样损坏）——秒不够细，得多一位。
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 暂存名带时间戳：固定名在两次备份并发时会互踩（同一 tmp 被两个 ZipFile 写、
    # os.replace 也可能撞车）；保留 TMP_PREFIX 以便残留清理照旧识别它。
    tmp_path = os.path.join(snap_dir, atomicio.TMP_PREFIX + "backup-%s.zip" % stamp)

    count = 0
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for full in _iter_files(ws):
            zf.write(full, os.path.relpath(full, os.path.dirname(ws)))
            count += 1

    target = os.path.join(snap_dir, "%s-%s.zip" % (name, stamp))
    os.replace(tmp_path, target)

    kept, removed = _apply_retention(snap_dir)
    return {
        "ok": True,
        "path": target,
        "files": count,
        "size": os.path.getsize(target),
        "kept": kept,
        "removed": removed,
        "snapshotDir": snap_dir,
    }


class OpenFolderBody(BaseModel):
    path: str


def _open_target(key, ws):
    """把「打开目录」的预设键解析成目标路径；未知键即拒绝（400）。

    只认预设键、不接受任意路径——避免变成任意目录打开器。抽成纯函数是为了
    能直接单测：走端点会真的拉起系统文件管理器。
    """
    from deps import data_root  # 函数内 import：本模块别处不依赖 deps
    if key == "workspace":
        return ws
    if key == "snapshots":
        return _snapshot_dir(ws)
    if key == "dataRoot":
        # 设置页「数据位置」卡片用：便携模式下数据根在应用旁、用户目录模式下
        # 在系统用户目录——两种都不一定等于某个具体工作区。
        return os.path.normpath(data_root())
    raise ApiError(400, "sys.unknownTarget",
                   "只支持 workspace / snapshots / dataRoot", target=key)


@router.post("/open-folder")
def open_folder(body: OpenFolderBody, ws: str = Depends(workspace_dir)):
    """用系统文件管理器打开目录（workspace / snapshots / dataRoot 三种）。

    只接受这几个预设键，不接受任意路径——避免变成任意目录打开器。
    """
    target = _open_target((body.path or "").strip(), ws)

    if not os.path.isdir(target):
        # 目录可能还没建（快照目录、全新数据根），直接建出来再打开，比报错有用
        os.makedirs(target)

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", target])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except OSError as exc:
        raise ApiError(500, "sys.openFailed", "打开失败：%s" % exc, error=str(exc))

    return {"ok": True, "path": target}
