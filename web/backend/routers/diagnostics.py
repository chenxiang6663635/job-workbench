# -*- coding: utf-8 -*-
"""诊断包导出（首发前收口批 笔 3）。

为什么需要它：这个应用的所有故障现场都在用户机器上，而用户能提供的往往只有一句
「打不开 / 没反应 / 数据看着不对」。诊断包把定位所需的事实收成一个 zip：版本、平台、
解释器、数据目录与模式、schema 自检摘要、主进程日志尾部（后端的 stdout/stderr 由主进程
转发进同一个文件，见 web/electron/main.js 的 log()）。

隐私边界比导出包更严——导出包是"用户自己要带走的数据"，诊断包是"要贴进 issue 的现场快照"：

- **不含工作区内容**：一个数据文件都不进包（`_iter_files` 那份清单在这里不适用）；
- **不含访问凭证**：`config/imap.json` / `config/provider.json` 从不进包；
- **路径脱敏**：家目录前缀（`C:\\Users\\<某人>`）一律换成 `~`；
- **体积上限**：日志只取尾部，且注明截断。

一个诚实的副作用：自检走的是 `tracker.run_check`（单一事实源），它在遇到无法解析的表文件时
会**隔离**到工作区 `quarantine/`——与界面上「自检」按钮同一个行为，不是诊断包额外的动作。
README 里写明了这一点，不靠用户猜。
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, Response

from jobws_core import pathres
from apierror import ApiError
from deps import workspace_dir

router = APIRouter(prefix="/api/system/diagnostics")

LOG_NAME = "main.log"
# 日志尾部上限：够覆盖几轮启动/报错，又不至于让 zip 变成"另一个数据包"
LOG_LIMIT = 128 * 1024
# 打包体积硬上限：**纵深防御**——包里唯一的变长内容是日志，已被 tail_text 截到 128KB，
# 所以正常路径不可达（批末审查指出不能把它当"运行时兜底"来读；真要防的是将来有人往包里
# 加了大件却忘了限）。
MAX_PACKAGE_BYTES = 4 * 1024 * 1024


def home_dir():
    """当前用户的家目录（脱敏目标）。做成函数是为了能被测试替换。"""
    return os.path.expanduser("~")


def redact(text, home=None):
    """家目录前缀 → `~`（反斜杠 / 正斜杠两种写法都换，**不区分大小写**）。

    诊断包会被贴进 issue、聊天窗口或工单：路径里的用户名不该跟着走。只做前缀替换，
    不去猜"哪个词是用户名"——那种模糊匹配会把无关内容改坏。

    大小写与分隔符都要覆盖：Windows 路径大小写不敏感，而日志里 `c:\\users\\bob` /
    `C:/Users/Bob` 这类写法来自 PATH、第三方库或 Chromium，精确串替换会漏（批末审查）。
    """
    target = home if home is not None else home_dir()
    if not target:
        return text
    out = text
    seen = set()
    for variant in (target, target.replace("\\", "/"), target.replace("/", "\\")):
        key = variant.lower()
        if not variant or key in seen:
            continue
        seen.add(key)
        out = re.sub(re.escape(variant), "~", out, flags=re.IGNORECASE)
    return out


def tail_text(text, limit=LOG_LIMIT):
    """日志尾部：返回 `(文本, 是否截断)`。截断必须有记号，否则看起来像完整日志。"""
    if len(text) <= limit:
        return text, False
    dropped = len(text) - limit
    return (
        "---- truncated: %d earlier bytes dropped, showing the last %d ----\n%s"
        % (dropped, limit, text[-limit:]),
        True,
    )


def _log_info():
    """读主进程日志尾部（不存在不算错：纯 API 场景本来就没有这个文件）。"""
    path = os.path.join(pathres.user_data_dir(), LOG_NAME)
    info = {"path": redact(path), "present": False, "bytes": 0, "truncated": False}
    if not os.path.isfile(path):
        return None, info
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError as exc:
        info["error"] = redact(str(exc))
        return None, info
    text, truncated = tail_text(raw)
    info.update({"present": True, "bytes": len(raw), "truncated": truncated})
    return redact(text), info


def _check_summary(ws):
    """schema 自检摘要：复用 tracker.run_check（单一事实源），只留结论与少数几行问题。"""
    from jobws_core import tracker

    try:
        result = tracker.run_check(ws)
    except Exception as exc:  # noqa: BLE001 —— 自检失败本身也是诊断信息，不该让出包失败
        return {"ok": False, "error": redact("%s: %s" % (type(exc).__name__, exc))}
    files = result.get("files") or []
    bad = [item for item in files if not item.get("ok")]
    issues = []
    for item in bad[:10]:
        for issue in (item.get("issues") or [])[:3]:
            issues.append(redact("%s: %s" % (item.get("file"), issue)))
    return {
        "ok": bool(result.get("ok")),
        "version": result.get("version"),
        "filesOk": len([item for item in files if item.get("ok")]),
        "filesBad": len(bad),
        # 只给文件名与极短的问题描述（行号 + 列名 + 取值）——用户要靠它决定"哪张表坏了"；
        # 但这也意味着包里可能带上少量单元格取值，notes / README 的措辞如实写了这一点
        "issues": issues,
        # 被隔离的文件名要列出来：只说"隔离了 1 个"会让用户不知道什么东西被移走了
        "quarantined": [redact(str(item)) for item in (result.get("quarantined") or [])],
    }


def _manifest(ws, log_info, home):
    """把"用户机器上到底发生了什么"整理成一份可读的 JSON。"""
    from routers.system import system_paths

    # system_paths 是这些事实（数据根 / 模式 / 快照目录与计数 / 上次备份 / 版本 / 平台）
    # 的单一事实源——诊断包不该另算一份，否则两边迟早说不一样的话。
    facts = system_paths(ws)
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "app": {
            "version": facts.get("appVersion") or "unknown",
            "platform": facts.get("platform"),
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
            "telemetry": bool(facts.get("telemetry")),
        },
        "paths": {
            "workspace": redact(facts.get("workspace") or "", home),
            "dataRoot": redact(facts.get("dataRoot") or "", home),
            "mode": facts.get("mode"),
            "snapshotDir": redact(facts.get("snapshotDir") or "", home),
            "snapshotCount": facts.get("snapshotCount"),
            "lastBackup": facts.get("lastBackup"),
        },
        "check": _check_summary(ws),
        "log": log_info,
        "contents": [
            "diagnostics.json",
            "main-log.txt" if log_info.get("present") else "main-log.txt (not found, see log entry in diagnostics.json)",
            "README_诊断包说明.txt",
        ],
        "notes": (
            "不含工作区数据文件与访问凭证（config/imap.json、config/provider.json 从不进包）；"
            "自检摘要里可能带少量单元格取值（行号 + 列名 + 极短原文），那是用户据以判断"
            "哪张表坏了所需的最小信息；路径里的家目录已脱敏为 ~；日志只保留尾部。"
            "自检若发现无法解析的表文件，会把它移进工作区的 quarantine/（与界面上的「自检」"
            "同一个行为），被移动的文件名见 check.quarantined。"
        ),
    }


def _readme(manifest, home):
    app = manifest["app"]
    return (
        "求职工作台诊断包\n"
        "生成时间：%s\n"
        "版本：%s（%s，Python %s）\n"
        "数据目录：%s（模式：%s）\n\n"
        "内容：diagnostics.json（版本 / 平台 / 路径 / schema 自检摘要 / 日志元信息）、"
        "main-log.txt（主进程日志尾部，含后端 stdout/stderr 的转发）。\n\n"
        "不含：工作区数据文件（一个都不进包）、访问凭证（config/imap.json、"
        "config/provider.json 从不进包）。\n"
        "已脱敏：路径里的家目录前缀替换为 ~。\n\n"
        "提醒：自检若发现无法解析的表文件，会把它们隔离到工作区的 quarantine/ 目录——"
        "这与界面上「自检」是同一个行为。\n"
    ) % (
        manifest["generatedAt"],
        app["version"],
        app["platform"],
        app["python"],
        redact(manifest["paths"]["dataRoot"], home),
        manifest["paths"]["mode"],
    )


@router.get("")
def export_diagnostics(ws: str = Depends(workspace_dir)):
    """导出诊断包（zip 附件）。"""
    home = home_dir()
    log_text, log_info = _log_info()
    manifest = _manifest(ws, log_info, home)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "diagnostics.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        if log_text is not None:
            zf.writestr("main-log.txt", log_text)
        zf.writestr("README_诊断包说明.txt", _readme(manifest, home))

    data = buf.getvalue()
    if len(data) > MAX_PACKAGE_BYTES:
        raise ApiError(413, "sys.diagnosticsTooLarge",
                       "诊断包超过体积上限（%d 字节）" % MAX_PACKAGE_BYTES,
                       limit=MAX_PACKAGE_BYTES)
    filename = "job-workbench-diagnostics-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="%s"' % filename},
    )
