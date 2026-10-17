# -*- coding: utf-8 -*-
"""jobws-mcp.exe 冒烟：起 exe → stdio 握手 → tools/list → 真调只读工具 → 资源注册（#271 P2-2）。

2026-10-12 补资源探针：DSH 宿主不桥接 MCP 资源（技能改走 `read_job_text` 工具），
但**服务侧**仍要能证明资源与模板在冻结论产物里注册成功——frozen 的导入与序列化
与源码态可能不同，这正是本脚本存在的理由（构建成功 ≠ 能启动 ≠ 能用）。

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


# 随包 exe 的工具契约（2026-10-16 E 批）：加工具时这里必须一起改。
# 为什么钉总数与末位而不是只打印：随包 exe 曾长期落后源码（`read_job_text` 与
# `score_calibration` 都是后加的），只打印数量的冒烟看不出"少了一个工具"。
EXPECTED_TOOL_COUNT = 17
# 协议层名保持点号：`jobws.info`（宿主侧才会被规范化成 mcp__jobws__jobws_info_*）
REQUIRED_TOOLS = ("jobws.info",)


def check_tools(names):
    """工具清单契约：数量、必需项、末位（新工具一律追加在协议末尾）。"""
    if len(names) != EXPECTED_TOOL_COUNT:
        _fail("工具数量不符：期望 %d，实际 %d：%s"
              % (EXPECTED_TOOL_COUNT, len(names), names))
    for name in REQUIRED_TOOLS:
        if name not in names:
            _fail("工具清单里没有 %s：%s" % (name, names))
    if names[-1] != "score_calibration":
        _fail("末位工具应为 score_calibration（新工具一律追加在协议末尾）：%s"
              % names[-3:])


def check_tool_behaviors(proc, deadline):
    """真调两个「后补的工具」：`read_job_text`（10-12）与 `score_calibration`（10-16）。

    只验注册面不够：随包 exe 落后源码两个月的教训正是「清单里有、行为没跑过」。
    两者都**不依赖真实数据**——空工作区下 `score_calibration` 仍返回四段结构；
    `read_job_text` 对不存在的岗位 + 非法 kind 明确给 `ok=false`。
    """
    # id 6/7：1 初始化、2 tools/list、3 jobws.info、4 resources/list、5 templates
    send(proc, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                "params": {"name": "score_calibration", "arguments": {}}})
    reply = read_message(proc, 6, deadline)
    if reply is None or "result" not in reply:
        _fail("score_calibration 调用失败：%s" % reply)
    payload = json.loads(reply["result"]["content"][0]["text"])
    missing = [k for k in ("tiers", "unapplied", "conclusion", "notes")
               if k not in payload]
    if missing:
        _fail("score_calibration 返回缺字段 %s：%s" % (missing, list(payload)))

    send(proc, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "read_job_text",
                           "arguments": {"job_name": "__smoke_missing__",
                                         "kind": "bogus"}}})
    reply = read_message(proc, 7, deadline)
    if reply is None or "result" not in reply:
        _fail("read_job_text 调用失败：%s" % reply)
    payload = json.loads(reply["result"]["content"][0]["text"])
    if payload.get("ok") is not False:
        _fail("read_job_text 对缺失岗位 + 非法 kind 应给 ok=false：%s" % payload)
    print("tools/call OK：score_calibration 四段齐全、read_job_text 对坏输入明确拒绝")


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
        check_tools(names)

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

        # 资源注册（2026-10-12）：只验**注册面**（静态 3 + 模板 2），不读内容——
        # 内容读取依赖具体工作区的数据，属 CI 的 stdio 冒烟职责（那边有夹具）。
        send(proc, {"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}})
        listed = read_message(proc, 4, deadline)
        if listed is None or "result" not in listed:
            _fail("resources/list 没有结果：%s" % listed)
        uris = [item["uri"] for item in listed["result"]["resources"]]
        expected = ["jobws://workspace/applications", "jobws://workspace/jobs",
                    "jobws://workspace/dashboard"]
        if uris != expected:
            _fail("静态资源清单不符：%s" % uris)
        print("resources/list OK：%d 个静态资源" % len(uris))

        send(proc, {"jsonrpc": "2.0", "id": 5,
                    "method": "resources/templates/list", "params": {}})
        templates = read_message(proc, 5, deadline)
        if templates is None or "result" not in templates:
            _fail("resources/templates/list 没有结果：%s" % templates)
        count = len(templates["result"]["resourceTemplates"])
        if count != 2:
            _fail("模板资源数不符（期望 2）：%s" % templates["result"]["resourceTemplates"])
        print("resources/templates/list OK：%d 个模板" % count)

        # 实现面（2026-10-16 复核要求）：真调两个后补的工具，不只验注册面
        check_tool_behaviors(proc, deadline)

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
