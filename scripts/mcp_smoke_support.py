# -*- coding: utf-8 -*-
"""MCP 冒烟的支撑层：stdio 协议通道 + 隔离环境 + 一次性进程（2026-10-21 拆出）。

**为什么需要它**（G1 例外 #3 的 P0/P1 修正）：
1. 原 `read_message()` 用阻塞 `stdout.readline()`——frozen 进程失去响应时永不返回，
   外层 deadline 形同虚设。`StdioPipe` 用「后台线程泵 stdout → 队列 → 主线程限时取」
   把等待变成真正有界。
2. 原冒烟继承父进程环境：父环境若有真实 `JOBWS_DATA_DIR`/`APPDATA` 就会读真实求职数据。
   `isolated_env()` 剔除继承变量并重设两者（**必须同时隔离**：`snapshot_root()` 有意
   不跟随 `JOBWS_DATA_DIR`，它在 `APPDATA` 下）。
3. 隔离根选址与本机沙箱的 frozen 写权限相关（`%TEMP%`/用户目录下 `--init` 报 WinError 5，
   仓库内正常），`smoke_base_dir()` 体现该事实并保留回退。

协议走裸 JSON-RPC（不依赖 mcp SDK）：stdio 传输 = 每行一条消息；非 JSON 行跳过。
零第三方依赖。
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64", "bin", "jobws-mcp.exe")
TIMEOUT = 30


class StdioPipe:
    """带真实超时的 stdio 通道。`read_message` 到点返回 None，调用方按失败处理。"""

    def __init__(self, proc):
        self.proc = proc
        self._q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in iter(self.proc.stdout.readline, b""):
            self._q.put(line)

    def send(self, payload):
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def read_message(self, want_id, deadline):
        """等 id == want_id 的消息；超过 deadline 返回 None（不再无限阻塞）。"""
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                return None
            try:
                line = self._q.get(timeout=min(remain, 1.0))
            except queue.Empty:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if msg.get("id") == want_id:
                return msg


def smoke_base_dir():
    """隔离根优先放**仓库内** `.codebuddy\\tmp`（已 gitignore），回退系统临时目录。

    2026-10-21 实测：本机沙箱对 frozen exe 的**写权限与路径相关**——`%TEMP%` 与用户目录下
    `--init` 建目录会 `PermissionError [WinError 5]`，仓库内正常（runbook §八 同族事实）。
    """
    preferred = os.path.join(ROOT, ".codebuddy", "tmp")
    try:
        os.makedirs(preferred, exist_ok=True)
        return tempfile.mkdtemp(prefix="jobws-mcp-smoke-", dir=preferred)
    except OSError:
        return tempfile.mkdtemp(prefix="jobws-mcp-smoke-")


def isolated_env(base):
    """隔离环境：工作区根与用户级根都指向本次临时目录（剔除继承的数据根变量）。"""
    env = dict(os.environ)
    for key in ("JOBWS_DATA_DIR", "JOBWS_WORKSPACE", "JOBWS_APP_ROOT"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["APPDATA"] = os.path.join(base, "appdata")
    env["JOBWS_DATA_DIR"] = os.path.join(base, "data")
    os.makedirs(env["APPDATA"], exist_ok=True)
    os.makedirs(env["JOBWS_DATA_DIR"], exist_ok=True)
    return env


def run_once(args, env, timeout=TIMEOUT):
    """起一次性子进程（负向契约用；stdin 关闭，不等 stdio 服务）。"""
    return subprocess.run([EXE] + args, env=env, cwd=ROOT,
                          stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=timeout)
