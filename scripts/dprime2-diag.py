# -*- coding: utf-8 -*-
"""CI 诊断：手动跑 NewCert + certcheck，把 exit/stdout/stderr 分别打印。

背景：S1 自检里 certcheck 连续多轮表现为「stdout 空 / stderr 空 / exit=1」，
而本地用同版本 Python 3.12 + cryptography 50.0.2 完全正常（exit 0，JSON 755 B）。
这个脚本在 CI 上手动复现那条链路，把三个流分别打印出来，不再靠推断。

用 Python 而不是内联 PowerShell：YAML 的 run: 块在 pwsh -command 模式下
对嵌套引号/反引号极不友好，诊断步骤自己就会 ParserError（2026-10-24 实测）。
"""

import os
import subprocess
import sys
import tempfile

# Windows 控制台默认 GBK：certcheck 的 JSON 含中文，直接 print 会
# UnicodeEncodeError 把诊断脚本自己打断（2026-10-24 本地实测，本轮第三次踩）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def main():
    py = sys.executable
    print("python      =", py)
    d = tempfile.mkdtemp(prefix="certcheck-diag-")
    print("diag dir    =", d)

    rc, out, err = run([
        "pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", os.path.join(HERE, "dprime2-s1.ps1"),
        "-Action", "NewCert", "-OutDir", d, "-Python", py,
    ])
    print("NewCert rc  =", rc)
    print("NewCert out >>>", out.strip()[-400:])
    if err.strip():
        print("NewCert err >>>", err.strip()[-400:])

    for f in ("ca.crt", "server.crt", "server.key"):
        p = os.path.join(d, f)
        print("  %-12s exists=%s size=%s" % (f, os.path.isfile(p),
                                             os.path.getsize(p) if os.path.isfile(p) else "-"))

    rc, out, err = run([py, os.path.join(HERE, "dprime2-certcheck.py"),
                        "--dir", d])
    print("certcheck rc =", rc)
    print("stdout lines =", len(out.splitlines()))
    print("stderr lines =", len(err.splitlines()))
    print("STDOUT>>>", out[:1200])
    print("STDERR>>>", err[:1200])
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
