# -*- coding: utf-8 -*-
"""工作区偏好（jobws prefs）与环境体检（jobws prefs doctor）。

设计（批 4，4f）：
- 偏好存**工作区** `config/preferences.json`——**工作区级物料偏好**的真值源：
  CLI / 技能 / agent / 导出读它（当前主要读者是 CLI 与技能）。前端的主题与
  字体是**设备级**偏好（localStorage，见 web/frontend/src/lib/theme.ts 的
  注释）——「这台机器」与「这份工作区」**分层**、互不覆盖；前端**不**读本
  文件（独立审查记账：不做「只写不读」的半接通双写，等出现真实的物料级偏好
  消费方再接）。
- 只认白名单 key（theme / font / resume_style）：拼错的 key 若静默写进文件，
  读回来永远是空——那类问题不值得再犯一次。
- doctor：环境与推荐清单（含**终端字体**——CLI 不做字体本体，终端字体归用户
  终端软件管理，此处只给建议）。

用法：
    python tools/jobws.py prefs get [key]
    python tools/jobws.py prefs set <key> <value>
    python tools/jobws.py prefs doctor

退出码：0 成功；1 校验失败；2 用法错误。
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys
import tempfile

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import tracker  # noqa: E402  （复用工作区解析与工作区结构约定）

PREFS_REL = os.path.join("config", "preferences.json")
KNOWN_KEYS = ["theme", "font", "resume_style"]

# CLI 端推荐终端字体（不做字体本体；见批 4 施工单 4g）
TERMINAL_FONTS = [
    ("Maple Mono", "中英混排等宽 + Nerd Font 图标——本项目的数字与表格首选"),
    ("JetBrains Mono", "经典编程字体，拉丁字形最成熟"),
    ("Sarasa Gothic 更纱黑体", "中英严格等宽，终端表格对齐最稳"),
]


def prefs_path(workspace=None):
    return os.path.join(tracker.resolve_ws(workspace), PREFS_REL)


def read_prefs(workspace=None):
    """读偏好；文件缺失或坏了都给空 dict（偏好丢了的代价远小于命令挂掉）。"""
    path = prefs_path(workspace)
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def write_prefs(values, workspace=None):
    """原子写（共享原语）：半截 JSON 比没有偏好更糟。批 8 收敛到 workspace_io。"""
    import workspace_io  # 用到才加载：prefs 保持轻量，模块级路径注入交给调用方

    payload = json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True)
    workspace_io.atomic_write_text(prefs_path(workspace), payload)


def cmd_get(args):
    values = read_prefs(getattr(args, "workspace", None))
    if getattr(args, "key", None):
        if args.key not in KNOWN_KEYS:
            print("未知偏好 key：%s（可选：%s）" % (args.key, " / ".join(KNOWN_KEYS)))
            return 1
        print(values.get(args.key, ""))
        return 0
    print(json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_set(args):
    if args.key not in KNOWN_KEYS:
        print("未知偏好 key：%s（可选：%s）" % (args.key, " / ".join(KNOWN_KEYS)))
        return 1
    value = (args.value or "").strip()
    if not value:
        print("value 不能为空")
        return 1
    workspace = getattr(args, "workspace", None)
    values = read_prefs(workspace)
    values[args.key] = value
    write_prefs(values, workspace)
    print("已保存 %s = %s（%s）" % (args.key, value, PREFS_REL))
    return 0


def cmd_doctor(args):
    ws = tracker.resolve_ws(getattr(args, "workspace", None))
    print("## 环境")
    print("- Python：%s" % sys.version.split()[0])
    print("- 工作区：%s" % ws)
    exists = os.path.isfile(prefs_path())
    print("- 偏好文件：%s%s" % (PREFS_REL, "" if exists else "（尚未创建）"))
    values = read_prefs()
    print("- 当前偏好：%s" % (json.dumps(values, ensure_ascii=False) if values else "（空）"))
    print("")
    print("## 推荐终端字体（CLI 不做字体本体；请在你的终端软件里选择）")
    for name, note in TERMINAL_FONTS:
        print("- %s：%s" % (name, note))
    print("")
    print("## 应用内主题与字体")
    print("桌面 / 浏览器端在「设置 → 外观」里切换——设备级偏好，存在本机。")
    return 0


def main():
    parser = argparse.ArgumentParser(description="工作区偏好与环境体检")
    subs = parser.add_subparsers(dest="action")
    # --workspace 与既有命令（track / report / resume…）同形：多工作区用户必须能指定。
    p_get = subs.add_parser("get", help="读偏好（缺省输出全部 JSON）")
    p_get.add_argument("key", nargs="?", help="只读某个 key：%s" % " / ".join(KNOWN_KEYS))
    p_get.add_argument("--workspace", default=None, help="目标工作区（缺省用默认工作区）")
    p_set = subs.add_parser("set", help="写偏好")
    p_set.add_argument("key", help="key：%s" % " / ".join(KNOWN_KEYS))
    p_set.add_argument("value")
    p_set.add_argument("--workspace", default=None, help="目标工作区（缺省用默认工作区）")
    p_doctor = subs.add_parser("doctor", help="环境体检与推荐清单（含终端字体）")
    p_doctor.add_argument("--workspace", default=None, help="目标工作区（缺省用默认工作区）")
    args = parser.parse_args()
    if args.action == "get":
        return cmd_get(args)
    if args.action == "set":
        return cmd_set(args)
    if args.action == "doctor":
        return cmd_doctor(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
