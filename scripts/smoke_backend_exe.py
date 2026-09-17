"""打包后端冒烟：启动 exe → 轮询 /api/health → 跑 tools 端点 → 资源自检 → 关进程。

为什么需要它：**构建成功 ≠ 能启动，也 ≠ 能用**。两道实证：
- v0.2.2：`tools/` 没进 PyInstaller 依赖图，`import imaplib` 在启动路径上失败，
  后端一启动就崩（health 永远不就绪），而 CI 只构建不运行产物、全绿；
- 只探 /api/health 抓不到「call-time 才炸」的缺口（模板文件读了才知道缺）——
  所以再补一条 `/api/system/check`（后端会执行 tracker.run_check，真跑 tools 代码），
  外加打包布局的资源自检（template/ 必须随包）。

用法：
    python scripts/smoke_backend_exe.py [exe路径] [--port 8799] [--timeout 30]

端口默认 8799：产品默认是 8765，冒烟另用一位，避免撞上你正在开发的后端。
默认 exe 路径：web/backend/dist/job-workbench-backend/job-workbench-backend.exe
退出码：0 通过；1 失败（失败打印 exe 输出尾部，便于定位缺了什么）
"""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

DEFAULT_EXE = os.path.join(
    "web", "backend", "dist", "job-workbench-backend", "job-workbench-backend.exe"
)


def _port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _get(url, timeout=5):
    """返回 (status, body)；连不上时 status=None、body=错误文本。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return None, str(exc)


def _missing_assets(exe):
    """打包布局的资源自检：template/ 必须在 tools 找得到的位置（理由见 spec 注释）。"""
    exe_dir = os.path.dirname(os.path.abspath(exe))
    internal = os.path.join(exe_dir, "_internal")
    root = internal if os.path.isdir(internal) else exe_dir
    required = [
        os.path.join(root, "template", "profiles"),
        os.path.join(root, "template", "workspace"),
    ]
    return [path for path in required if not os.path.isdir(path)]


def main():
    parser = argparse.ArgumentParser(description="打包后端 exe 冒烟")
    parser.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--timeout", type=int, default=30, help="等 health 的上限秒数")
    args = parser.parse_args()

    if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
        if sys.stdout.encoding.lower() != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception as exc:
                # 重配失败不致命（控制台可能不支持），但留一句——否则乱码时
                # 无从判断是「没重配成功」还是「终端本身不显示」。
                print("注意：stdout 重配 utf-8 失败：%s" % exc, file=sys.stderr)

    if not os.path.isfile(args.exe):
        print("找不到 exe：%s" % args.exe)
        return 1

    # 被占就明确报错：既避免把别人的进程测成自己的，也避免踩到后端的
    # 「复用已运行服务」分支（那条分支会弹浏览器、frozen 下还会 input()）
    if _port_busy(args.port):
        print("**失败**：端口 %d 已被占用——换 --port 重试" % args.port)
        return 1

    missing = _missing_assets(args.exe)
    if missing:
        print("**失败**：产物缺少必要资源（PyInstaller datas 缺项）：")
        for path in missing:
            print("  " + path)
        return 1

    # 输出走临时文件而不是 PIPE：子进程日志写满管道缓冲会死锁（2026-09-13 审查 MAJOR-3）
    log = tempfile.TemporaryFile()
    env = dict(os.environ, JOBWS_NO_BROWSER="1")
    print("启动：%s --port %d" % (args.exe, args.port))
    proc = subprocess.Popen(
        [args.exe, "--port", str(args.port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,  # frozen 下复用分支会 input()，CI 无 stdin
        env=env,
    )

    def tail(limit=30):
        try:
            log.flush()
            log.seek(0)
            return log.read().decode("utf-8", "replace").splitlines()[-limit:]
        except Exception:
            return []

    def fail(message):
        print("**失败**：" + message)
        lines = tail()
        if lines:
            print("---- exe 输出（末 %d 行）----" % len(lines))
            for line in lines:
                print(line)
        return 1

    base = "http://127.0.0.1:%d" % args.port
    deadline = time.time() + args.timeout
    try:
        healthy = False
        while time.time() < deadline:
            time.sleep(1)
            if proc.poll() is not None:
                return fail("后端在 health 通过前退出（exit=%s）" % proc.returncode)
            status, body = _get(base + "/api/health", timeout=3)
            if status == 200:
                print("health 通过：%s" % body)
                healthy = True
                break
        if not healthy:
            return fail("%d 秒内 /api/health 未返回 200" % args.timeout)

        # 再跑一条真正执行 tools 代码的端点：health 只证明"活着"，这条证明"能用"。
        # 工作区为空时返回 4xx 属正常分支（仍说明 tools 代码跑到了），5xx 才算失败。
        status, body = _get(base + "/api/system/check")
        if status is None:
            return fail("/api/system/check 无响应：%s" % body)
        if status >= 500:
            return fail("/api/system/check 返回 %d：%s" % (status, body[:300]))
        print("/api/system/check → HTTP %d（tools 代码已实际执行）" % status)
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            print("冒烟进程已关闭")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
