# -*- coding: utf-8 -*-
"""启动前检查（pre-flight）：解释器基线与监听地址边界。

从 main.py 拆出（2026-09-25 发布前收口批：main.py 因新增监听边界检查越过
300 行规模预算）。这些检查的共性是：**都在服务启动之前**判定"该不该起、
哪里起"，与请求处理无关；且都是纯函数/近纯函数，便于单测逐档锁死
（tests/test_unhandled_error.py 与 tests/test_backend_network_guard.py）。

两个检查的立场一致：宁可启动时响亮拒绝，也不带着错误配置跑起来——
解释器太旧，IMAP 路径必炸；监听地址非回环，无鉴权的数据 API 就出了本机。
"""

import sys

# ---- 解释器基线（与 tests/conftest.py 的护栏、CONTRIBUTING 的口径同源）----
#
# **技术要求是 ≥3.9**：IMAP 路径把超时交给 `imaplib.IMAP4_SSL(timeout=…)`，这个参数
# 3.9 才有。3.8 上它不是"连不上邮箱"，而是抛 `TypeError: unexpected keyword argument`
# —— 2026-09-15 实测：界面上只看到一句裸的 "Internal Server Error"，既没有错误码也没有
# 指向（那台机器上后端被 conda 的 3.8 启动了）。所以太旧的解释器必须**在启动时**拒绝，
# 而不是等到用户点「拉取邮件」。
#
# **支持基线是 3.12**：CI 与打包只验证它；3.9–3.11 能用但未经验证，启动时给警告而不是拒绝。
IMAP_MIN_PY = (3, 9)
SUPPORTED_MIN_PY = (3, 12)


def interpreter_verdict(version_info):
    """按解释器版本给出 ("ok" | "warn" | "refuse", 说明)。纯函数，便于测试。"""
    current = tuple(version_info[:2])
    if current < IMAP_MIN_PY:
        return "refuse", (
            "本应用需要 Python %d.%d+ 才能启动：IMAP 路径使用 imaplib 的 timeout 参数，"
            "%d.%d 上会直接抛 TypeError。请改用 Python %d.%d 启动后端"
            "（或使用桌面安装包——它自带运行时）。"
            % (IMAP_MIN_PY[0], IMAP_MIN_PY[1], current[0], current[1],
               SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1]))
    if current < SUPPORTED_MIN_PY:
        return "warn", (
            "当前解释器 %d.%d 低于支持基线 %d.%d（CI 与打包只验证后者）：可以运行，"
            "但未经验证——出问题请先用 %d.%d 复现。"
            % (current[0], current[1], SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1],
               SUPPORTED_MIN_PY[0], SUPPORTED_MIN_PY[1]))
    return "ok", ""


def enforce_interpreter():
    """按 verdict 拒收（退出码 2）/ 警告 / 放行。启动时调用一次。"""
    verdict, message = interpreter_verdict(sys.version_info)
    if verdict == "refuse":
        print("[job-workbench] 解释器不满足技术要求：" + message, file=sys.stderr)
        raise SystemExit(2)
    if verdict == "warn":
        print("[job-workbench] 警告：" + message, file=sys.stderr)


def is_loopback_host(host):
    """监听地址是否为本机回环（纯函数，便于测试——与 interpreter_verdict 同款）。

    127.0.0.0/8 整段都是回环（RFC 1122，不止 127.0.0.1）；`localhost` 与
    IPv6 回环 `::1` 同列。其余（`0.0.0.0` / `::` / 具体网卡地址 / 域名 / 空值）
    都视为「会把无鉴权 API 暴露到本机之外」，必须在命令行显式破例
    （`--unsafe-network-api`）——安全边界不该由一个日常参数跨过。
    """
    h = (host or "").strip().lower()
    return h in ("localhost", "::1") or h.startswith("127.")
