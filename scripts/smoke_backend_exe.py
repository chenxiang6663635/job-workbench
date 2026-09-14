"""打包后端冒烟：启动 exe → 轮询 /api/health → 断言 200 → 关进程。

为什么需要它：**构建成功 ≠ 能启动**。v0.2.2 就是这样溜过去的——
`tools/` 没进 PyInstaller 依赖图，`import imaplib` 在启动路径上失败，
后端一启动就崩，而 CI 只构建不运行产物，全绿。

用法：
    python scripts/smoke_backend_exe.py [exe路径] [--port 8799] [--timeout 30]

默认 exe 路径：web/backend/dist/job-workbench-backend/job-workbench-backend.exe
退出码：0 通过；1 失败（进程提前退出或 health 超时，都会打印 exe 输出）
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_EXE = os.path.join(
    "web", "backend", "dist", "job-workbench-backend", "job-workbench-backend.exe"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包后端 exe 冒烟")
    parser.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--timeout", type=int, default=30, help="等 health 的上限秒数")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not os.path.isfile(args.exe):
        print("找不到 exe：%s" % args.exe)
        return 1

    env = dict(os.environ, JOBWS_NO_BROWSER="1")
    print("启动：%s --port %d" % (args.exe, args.port))
    proc = subprocess.Popen(
        [args.exe, "--port", str(args.port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )

    health = "http://127.0.0.1:%d/api/health" % args.port
    deadline = time.time() + args.timeout
    try:
        while time.time() < deadline:
            time.sleep(1)
            if proc.poll() is not None:
                print("**失败**：后端在 health 通过前退出（exit=%s）" % proc.returncode)
                print("---- exe 输出（末 30 行）----")
                out = proc.stdout.read().decode("utf-8", "replace")
                for line in out.splitlines()[-30:]:
                    print(line)
                return 1
            try:
                with urllib.request.urlopen(health, timeout=3) as resp:
                    body = resp.read().decode("utf-8", "replace")
                print("health 通过：%s" % body)
                return 0
            except (urllib.error.URLError, OSError):
                continue
        print("**失败**：%d 秒内 %s 未返回 200" % (args.timeout, health))
        return 1
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("冒烟进程已关闭")


if __name__ == "__main__":
    sys.exit(main())
