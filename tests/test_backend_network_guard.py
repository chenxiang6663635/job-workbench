# -*- coding: utf-8 -*-
"""监听地址边界：`--host` 非 loopback 必须显式破例（2026-09-25 发布前收口批）。

后端**没有任何鉴权**（SECURITY.md 如实登记）；默认只监听 127.0.0.1 是对的，
但一个普通 `--host 0.0.0.0` 就能把无鉴权的数据 API 暴露到局域网——安全边界
不该由一个日常参数跨过（独立审计 P1）。纯函数 `is_loopback_host` 是那道检查
的唯一判据，便于在此逐档锁死（与 interpreter_verdict 的纯函数先例同款）。
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))

import main  # noqa: E402


def test_loopback_hosts_are_allowed():
    """回环整段都算：127.0.0.0/8（不止 .0.1，RFC 1122）、localhost、IPv6 回环。"""
    for host in ("127.0.0.1", "127.0.0.5", "127.1.2.3", "localhost", "LOCALHOST", "::1"):
        assert main.is_loopback_host(host) is True, host


def test_non_loopback_hosts_are_rejected():
    """通配与外部地址一律进二次开关：0.0.0.0 / :: / 具体网卡地址 / 域名 / 空值。"""
    for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.1", "example.com", "",
                 "   "):
        assert main.is_loopback_host(host) is False, repr(host)


def test_pause_if_frozen_skips_non_interactive(monkeypatch):
    """冻结态 + 非交互 stdin（管道 / DEVNULL）→ 直接返回、不调用 input（2026-09-25 收口批）。

    背景（四端复核）：桌面壳以 stdio: pipe 拉起后端且不关闭 stdin 时，input()
    会永久阻塞——进程不退、壳拿不到 exit 回调，用户 30 秒后看到「启动超时」
    弹窗，真实原因只留在日志；CI 冒烟此前用 DEVNULL 绕开的正是同一行为。
    本用例的 stdin 就是 pytest 的非交互实现（isatty() 为 False）。
    """

    def _boom(*_args):
        raise AssertionError("非交互 stdin 不应调用 input（会阻塞壳的退出回调）")

    monkeypatch.setattr("builtins.input", _boom)
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    main._pause_if_frozen()      # 修复前：AssertionError；修复后：直接返回
