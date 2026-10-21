# -*- coding: utf-8 -*-
"""jobws-mcp.exe 冒烟：起 exe → stdio 握手 → tools/list → 真调只读工具 → 资源注册（#271 P2-2）。

2026-10-12 补资源探针：DSH 不桥接 MCP 资源（技能走 `read_job_text`），但**服务侧**仍要证明
资源与模板在冻结产物里注册成功——frozen 的导入/序列化与源码态可能不同（构建成功 ≠ 能启动 ≠ 能用）。

为什么单独冒烟（同 smoke_backend_exe.py）：这个 exe 随 npm 发给没装 Python 的机器，
CI 只构建不运行产物；不真起一次，缺模块/缺 template/编码问题会以「用户那边起不来」出现。

协议走**裸 JSON-RPC**（不依赖 mcp SDK——本脚本要在任意构建 venv 里能跑）：
stdio 传输 = 每行一个 JSON-RPC 消息。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64", "bin", "jobws-mcp.exe")

TIMEOUT = 30


def _fail(msg):
    print("FAIL: %s" % msg)
    sys.exit(1)





# 中文 Windows 控制台是 GBK：打印非 GBK 字符会 UnicodeEncodeError——冒烟输出不能中途崩（2026-10-21 实测）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def smoke_base_dir():
    """隔离根优先放**仓库内** `.codebuddy\\tmp`（已 gitignore），回退系统临时目录。

    2026-10-21 实测：本机沙箱对 frozen exe 的**写权限与路径相关**——`%TEMP%` 与用户目录下
    `--init` 建目录会 `PermissionError [WinError 5]`，仓库内正常（runbook §八 同族事实）；
    冒烟必须真初始化工作区，故选址跟着走。
    """
    preferred = os.path.join(ROOT, ".codebuddy", "tmp")
    try:
        os.makedirs(preferred, exist_ok=True)
        return tempfile.mkdtemp(prefix="jobws-mcp-smoke-", dir=preferred)
    except OSError:
        return tempfile.mkdtemp(prefix="jobws-mcp-smoke-")


def isolated_env(base):
    """测试进程的隔离环境：**工作区根与用户级根都指向本次临时目录**。

    2026-10-21（G1 例外 #3）加固：原脚本继承父进程环境并以 `--workspace personal`
    启动——父环境里若有真实 `JOBWS_DATA_DIR`/`APPDATA`，冒烟会读真实求职数据。
    这里剔除继承来的数据根变量后重设两者：
      - `JOBWS_DATA_DIR` → <base>/data（工作区选择）
      - `APPDATA`        → <base>/appdata（快照 snapshot_root 与用户级状态）
    两者必须**同时**隔离：`snapshot_root()` 不跟随 `JOBWS_DATA_DIR`（pathres 有意设计）。
    """
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


def check_isolation(base, payload):
    """数据根必须落在隔离目录内——防「继承来的真实根」被静默读取。"""
    root = payload.get("dataRoot", {}).get("path") or ""
    if os.path.normcase(base) not in os.path.normcase(root):
        _fail("jobws.info 报告的数据根不在隔离目录内：%r（base=%r）" % (root, base))
    print("隔离 OK：数据根在临时目录内（%s）" % root)


def check_negative_cases(base, env):
    """三条负向契约（2026-10-21 新增）：缺根拒绝 / 默认根初始化 / 越界拒绝。"""
    # ① 显式 JOBWS_DATA_DIR 指向不存在的根 → 必须拒绝，且不许静默建出工作区
    missing = os.path.join(base, "does-not-exist")
    env_missing = dict(env)
    env_missing["JOBWS_DATA_DIR"] = missing
    r = run_once(["--workspace", "personal"], env_missing)
    if r.returncode == 0:
        _fail("显式缺根未被拒绝（exit 0）——fail-closed 契约失效")
    if os.path.isdir(os.path.join(missing, "personal")):
        _fail("显式缺根被静默建成了工作区：%s" % missing)
    print("缺根拒绝 OK：exit=%d" % r.returncode)

    # ② 不设 JOBWS_DATA_DIR + 隔离 APPDATA → 默认根首次使用自动初始化（#357）
    env_default = dict(env)
    env_default.pop("JOBWS_DATA_DIR", None)
    env_default["APPDATA"] = os.path.join(base, "appdata-default")
    os.makedirs(env_default["APPDATA"], exist_ok=True)
    r = run_once(["--init"], env_default)
    if r.returncode != 0:
        _fail("默认根 --init 失败：%s" % r.stderr.decode("utf-8", "replace")[:500])
    laid = [c for c in ("job-workbench/personal", "job-workbench/data/personal")
            if os.path.isdir(os.path.join(env_default["APPDATA"], c))]
    if not laid:
        _fail("默认根 --init 后未铺出工作区（%s 下找 job-workbench[/data]/personal）"
              % env_default["APPDATA"])
    print("默认根初始化 OK：%s" % laid[0])

    # ③ 越界工作区 → 拒绝
    r = run_once(["--workspace", "../../etc"], env)
    if r.returncode == 0:
        _fail("越界 workspace 未被拒绝（exit 0）")
    print("越界拒绝 OK：exit=%d" % r.returncode)


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


def check_stdio_surface(proc, deadline, base):
    """正向 stdio 契约：initialize → 17 工具 → jobws.info + 隔离断言 → 3 资源 → 2 模板 → 两工具行为。"""
    send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "smoke", "version": "0"}}})
    reply = read_message(proc, 1, deadline)
    if reply is None or "result" not in reply:
        _fail("initialize 没有结果（stderr 见下）\n%s"
              % proc.stderr.read(4096).decode("utf-8", "replace"))
    print("initialize OK：%s" % json.dumps(reply["result"].get("serverInfo", {}), ensure_ascii=False))

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
    check_isolation(base, payload)

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


def main():
    if not os.path.isfile(EXE):
        _fail("找不到 %s（先跑 scripts\\build_mcp_exe.ps1）" % EXE)
    base = smoke_base_dir()
    env = isolated_env(base)
    proc = None
    try:
        # 0) 显式初始化隔离数据根（--init 幂等铺骨架；不依赖任何真实根）
        init = run_once(["--init"], env)
        if init.returncode != 0:
            _fail("隔离数据根 --init 失败：%s" % init.stderr.decode("utf-8", "replace")[:500])
        ws_dir = os.path.join(base, "data", "personal")
        if not os.path.isdir(ws_dir):
            _fail("--init 未铺出隔离工作区：%s" % ws_dir)
        print("--init OK：隔离工作区 %s" % ws_dir)

        proc = subprocess.Popen([EXE, "--workspace", "personal"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=ROOT, env=env)
        deadline = time.time() + TIMEOUT
        check_stdio_surface(proc, deadline, base)
        check_negative_cases(base, env)  # 一次性子进程，不干扰主服务

        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            _fail("stdin 关闭后进程未退出（stdio 服务应随输入流结束）")
        print("SMOKE OK")
        return 0
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
