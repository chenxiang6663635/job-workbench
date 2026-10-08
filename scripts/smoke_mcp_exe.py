# -*- coding: utf-8 -*-
"""jobws-mcp.exe 冒烟：起 exe → stdio 握手 → tools/list → 真调一个只读工具（#271 P2-2）。

为什么单独一个冒烟（与 scripts/smoke_backend_exe.py 同款理由）：**构建成功 ≠ 能启动，
也 ≠ 能用**。这个 exe 会随 npm 包发给「没装过 Python 的机器」，而 CI 只构建不运行产物——
不真起一次，缺模块/缺 template/编码问题都会以「用户那边起不来」的形态出现。

协议走**裸 JSON-RPC**（不依赖 mcp SDK——本脚本要在任意构建 venv 里能跑）：
stdio 传输 = 每行一个 JSON-RPC 消息。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64", "bin", "jobws-mcp.exe")

TIMEOUT = 30


def _fail(msg):
    print("FAIL: %s" % msg)
    sys.exit(1)


def send(proc, payload):
    proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    proc.stdin.flush()


def read_message(proc, want_id, deadline):
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            continue  # 非 JSON 行（第三方库日志）跳过
        if msg.get("id") == want_id:
            return msg
    return None


def main():
    if not os.path.isfile(EXE):
        _fail("找不到 %s（先跑 scripts\\build_mcp_exe.ps1）" % EXE)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen([EXE, "--workspace", "personal"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=ROOT, env=env)
    deadline = time.time() + TIMEOUT
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "smoke", "version": "0"}}})
        init = read_message(proc, 1, deadline)
        if init is None or "result" not in init:
            _fail("initialize 没有结果（stderr 见下）\n%s"
                  % proc.stderr.read(4096).decode("utf-8", "replace"))
        print("initialize OK：%s" % json.dumps(init["result"].get("serverInfo", {}), ensure_ascii=False))

        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = read_message(proc, 2, deadline)
        if tools is None or "result" not in tools:
            _fail("tools/list 没有结果")
        names = [t["name"] for t in tools["result"]["tools"]]
        print("tools/list OK：%d 个工具" % len(names))
        # 协议层名保持点号：`jobws.info`（宿主侧才会被规范化成 mcp__jobws__jobws_info_*）
        if "jobws.info" not in names:
            _fail("工具清单里没有 jobws.info：%s" % names)

        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "jobws.info", "arguments": {}}})
        call = read_message(proc, 3, deadline)
        if call is None or "result" not in call:
            _fail("jobws.info 调用失败：%s" % call)
        payload = json.loads(call["result"]["content"][0]["text"])
        state = payload.get("dataRoot", {}).get("state")
        if state != "ok":
            _fail("jobws.info 的 dataRoot.state = %r（期望 ok）" % state)
        print("tools/call OK：jobws.info dataRoot.state=%s" % state)

        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            _fail("stdin 关闭后进程未退出（stdio 服务应随输入流结束）")
        print("SMOKE OK")
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
