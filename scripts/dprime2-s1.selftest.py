# -*- coding: utf-8 -*-
"""D'-2 S1 离线自检（不装证书、不改 hosts、不绑 443、不起客户端）。

覆盖：
  A. 脚本静态安全扫描（禁项不得出现）
  B. VerifyRc 对真实 RC 的身份校验（PowerShell 动作实跑）
  C. NewCert + Tls1 实跑（证书纯内存生成 + 离线结构检查）
  D. mock 真实 TLS 握手（高位端口，Python 客户端只信任自建 CA）
     - 三条路由内容正确（latest.yml 与真实 RC 逐字节一致）
     - 探针/客户端请求分类正确
     - 未知路径 404；auth 头只记存在性
  E. Verdict 分类逻辑（三组合成日志：PASS / 代理阻断 / TLS 阻断）
  F. 工作流 YAML 结构（关键步骤与 always() 门禁）
"""

import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "dprime2-s1.ps1")
MOCK = os.path.join(HERE, "dprime2-mock-server.py")
CERTCHECK = os.path.join(HERE, "dprime2-certcheck.py")

# workflow 位置随布局变化：仓库里在 .github/workflows/，草案目录里与脚本同放。
# 两处都支持，并用 DPRIME2_WF 可覆盖（便于在无仓库结构的临时目录里跑）。
WF = os.environ.get("DPRIME2_WF", "")
if not WF:
    _repo_wf = os.path.join(os.path.dirname(HERE), ".github", "workflows",
                            "dprime2-s1-discovery.yml")
    WF = _repo_wf if os.path.isfile(_repo_wf) else os.path.join(HERE, "s1-workflow.yml")
# 固定 RC 目录（含 latest.yml 与目标 exe）。**不要在这里写死本机路径**——
# 入仓后 CI 上没有那个目录，硬编码会让自检在 CI 上直接红。
# 用法：设环境变量 DPRIME2_RC_ROOT 指向 RC 目录；未设置或目录不含 latest.yml 时，
# 依赖真实 RC 的组（B / C2）记 SKIP，D 组降级为**合成夹具**只验证 mock 协议，
# 并在结果里明确标注"未验证元数据身份"。
RC = os.environ.get("DPRIME2_RC_ROOT", "")
RC_OK = bool(RC) and os.path.isfile(os.path.join(RC, "latest.yml"))
PWSH = ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1]

results = []


def rep(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("%-4s %-52s %s" % ("PASS" if ok else "FAIL", name[:52], detail[:90]))


def skip(name, why):
    """记 SKIP：既不算通过也不算失败（例如缺少真实 RC 目录时）。"""
    results.append((name, None, why))
    print("%-4s %-52s %s" % ("SKIP", name[:52], why[:90]))


def ps(action, outdir, extra=()):
    cmd = list(PWSH) + ["-Action", action, "-OutDir", outdir] + list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ── A. 静态安全扫描 ────────────────────────────────────────────────────────
FORBIDDEN = ["-SkipCertificateCheck", "ignore-certificate-errors",
             "setCertificateVerifyProc", "--trust", "verify=false",
             "Cert:\\CurrentUser", "NODE_EXTRA_CA_CERTS"]


def strip_comments(text):
    """剥掉 <# #> 块与行尾 # 注释，避免把红线说明文字误判为使用。"""
    text = re.sub(r"<#.*?#>", "", text, flags=re.S)
    out = []
    for line in text.splitlines():
        idx = line.find("#")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


for path in (PS1, MOCK, CERTCHECK, WF):
    txt = strip_comments(io.open(path, encoding="utf-8").read())
    hits = [f for f in FORBIDDEN if f in txt]
    rep("A1 无禁项 %s" % os.path.basename(path), not hits, "hits=%s" % hits)

ps1 = io.open(PS1, encoding="utf-8").read()
rep("A2 hosts 改动只经 PatchHosts 且有备份",
    ps1.count("drivers\\etc\\hosts") >= 3 and "hosts.bak" in ps1, "备份+恢复都在")
rep("A3 Restore 与 CleanupVerify 是两个动作",
    "'Restore','CleanupVerify'" in ps1, "动作枚举含两者")
rep("A4 mock 只绑回环", "'--host', '127.0.0.1'" in ps1 and "127.0.0.1" in io.open(MOCK, encoding="utf-8").read(),
    "默认 127.0.0.1")

# ── B. VerifyRc（需要真实 RC 目录）────────────────────────────────────────
tmp = tempfile.mkdtemp(prefix="dprime2-selftest-")
out_b = os.path.join(tmp, "rc")
if RC_OK:
    rc, out = ps("VerifyRc", out_b, ["-RcRoot", RC])
else:
    rc, out = 2, "skipped"
if not RC_OK:
    skip("B1 VerifyRc 实跑通过", "未设置 DPRIME2_RC_ROOT 或目录内无 latest.yml")
    skip("B2 RC 身份逐项全过", "同上：缺真实 RC 无法校验元数据身份")
else:
    rep("B1 VerifyRc 实跑通过", rc == 0, out.strip().splitlines()[-1][:80] if out.strip() else "")
    if os.path.isfile(os.path.join(out_b, "rc-identity.json")):
        d = json.load(io.open(os.path.join(out_b, "rc-identity.json"), encoding="utf-8"))
        rep("B2 RC 身份逐项全过", d.get("all_ok") is True,
            "rows=%d" % len(d.get("rows", [])))

# ── C. NewCert + Tls1 ─────────────────────────────────────────────────────
out_c = os.path.join(tmp, "cert")
rc, out = ps("NewCert", out_c)
rep("C1 NewCert 实跑", rc == 0, out.strip().splitlines()[-1][:80] if out.strip() else "")
for f in ("ca.crt", "server.crt", "server.key"):
    rep("C2 产出 %s" % f, os.path.isfile(os.path.join(out_c, f)),
        "%d bytes" % os.path.getsize(os.path.join(out_c, f)) if os.path.isfile(os.path.join(out_c, f)) else "missing")
rc, out = ps("Tls1", out_c)
rep("C3 Tls1 离线结构检查全过", rc == 0, out.strip().splitlines()[-1][:80] if out.strip() else "")
tls1 = json.load(io.open(os.path.join(out_c, "tls1.json"), encoding="utf-8"))
rep("C4 Tls1 未做握手", tls1.get("handshake_performed") is False and
    tls1.get("mode") == "offline-structure-only", "mode=%s" % tls1.get("mode"))

# ── C2. PrepareFixtures：与生产**同一条路径**备元数据（2026-10-24 补）──────
# 原自检自己手写 atom.xml/latest.json，掩盖了 StartMock 根本不生成夹具的缺口。
# 现在改为真跑 PrepareFixtures（python 侧只做证书，元数据一律由 PowerShell 派生）。
rc_fx, out_fx = (ps("PrepareFixtures", out_c, ["-RcRoot", RC]) if RC_OK else (2, "skipped"))
if RC_OK:
    rep("C2-1 PrepareFixtures 实跑通过", rc_fx == 0,
        out_fx.strip().splitlines()[-1][:90] if out_fx.strip() else "")
else:
    skip("C2-1 PrepareFixtures 实跑通过", "缺真实 RC；改用合成夹具兜底只验 mock 协议")
fx_json = os.path.join(out_c, "fixtures.json")
if os.path.isfile(fx_json):
    d = json.load(io.open(fx_json, encoding="utf-8"))
    rep("C2-2 夹具自洽 5 项全过", d.get("all_ok") is True,
        "rows=%d version=%s tag=%s" % (len(d.get("rows", [])), d.get("version"), d.get("tag")))
    rep("C2-3 atom/latest 标明是派生而非自造",
        "派生" in (d.get("derived", {}).get("note") or ""), "")

# ── D. mock 真实 TLS 握手（高位端口）──────────────────────────────────────
fixture = os.path.join(out_c, "fixtures")          # 直接用 PrepareFixtures 的产物
os.makedirs(fixture, exist_ok=True)
if not RC_OK:
    # 合成夹具：只够验证 mock 的**协议行为**（路由/302/404/分类），
    # **不验证**元数据身份——那需要真实 RC，已在 B/C2 组记为 SKIP。
    io.open(os.path.join(fixture, "latest.yml"), "w", encoding="utf-8").write(
        "version: 26.10.1\npath: job-workbench-setup-26.10.1-win64.exe\n"
        "sha512: c21f2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9\n"
        "releaseDate: '2026-10-23T00:00:00.000Z'\n")
    io.open(os.path.join(fixture, "latest.json"), "w", encoding="utf-8").write(
        '{"tag_name":"v26.10.1"}')
    io.open(os.path.join(fixture, "atom.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        '<entry><link rel="alternate" href="https://github.com/chenxiang6663635/job-workbench'
        '/releases/tag/v26.10.1"/><title>v26.10.1</title></entry></feed>')
    io.open(os.path.join(fixture, "tag.html"), "w", encoding="utf-8").write(
        '<!doctype html><title>v26.10.1</title>')
# 只补证书（StartMock 负责这部分；自检不绑 443 所以自己放）。
# 只放**叶子**：Python 的 load_cert_chain 用 certfile 第一张配密钥
# （server.crt 里 CA 在前，直接复制会 KEY_VALUES_MISMATCH）
_all = io.open(os.path.join(out_c, "server.crt"), encoding="utf-8").read()
_blocks = [b for b in _all.split("-----BEGIN CERTIFICATE-----") if "END CERTIFICATE" in b]
io.open(os.path.join(fixture, "server.crt"), "w", encoding="utf-8").write(
    "-----BEGIN CERTIFICATE-----" + _blocks[-1])
shutil.copy(os.path.join(out_c, "ca.crt"), fixture)
shutil.copy(os.path.join(out_c, "server.key"), fixture)
io.open(os.path.join(fixture, "probe.txt"), "w", encoding="utf-8").write("dprime2-tls2-probe")

# 三份元数据必须都在（缺一个就说明 PrepareFixtures 没起作用）
for _need in ("atom.xml", "latest.json", "latest.yml"):
    rep("C2-4 夹具含 %s" % _need, os.path.isfile(os.path.join(fixture, _need)), "")

PORT = 18443
log = os.path.join(tmp, "mock.jsonl")
proc = subprocess.Popen([sys.executable, MOCK, "--root", fixture, "--log", log,
                         "--host", "127.0.0.1", "--port", str(PORT)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    up = False
    for _ in range(40):
        try:
            import socket
            s = socket.create_connection(("127.0.0.1", PORT), timeout=0.5)
            s.close()
            up = True
            break
        except OSError:
            time.sleep(0.25)
    rep("D1 mock 在高位端口监听", up, "port=%d" % PORT)

    if up:
        ctx = ssl.create_default_context(cafile=os.path.join(out_c, "ca.crt"))
        # 走回环 + 证书里的 IP:127.0.0.1 SAN；主机名校验仍然开启（未放宽 TLS）
        base = "https://127.0.0.1:%d" % PORT
        # 三条路由
        paths = [
            "/chenxiang6663635/job-workbench/releases.atom",
            "/chenxiang6663635/job-workbench/releases/latest",
            "/chenxiang6663635/job-workbench/releases/download/v26.10.1/latest.yml",
        ]
        want = {
            paths[0]: io.open(os.path.join(fixture, "atom.xml"), "rb").read(),
            paths[1]: io.open(os.path.join(fixture, "latest.json"), "rb").read(),
            paths[2]: io.open(os.path.join(fixture, "latest.yml"), "rb").read(),
        }
        # latest 需要 Accept: application/json（与真实 GitHub 等价，2026-10-24 补）
        for p in paths:
            headers = {"Accept": "application/json"} if p.endswith("/releases/latest") else {}
            req = urllib.request.Request(base + p, headers=headers, method="GET")
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                body = r.read()
                rep("D2 路由 %s" % p.split("/", 3)[-1][:28],
                    r.status == 200 and body == want[p],
                    "status=%s bytes=%d" % (r.status, len(body)))

        # D2b 关键等价性：**不带** Accept: application/json 时必须 302 到 tag 页，
        # 而不是回 JSON（真实 GitHub 行为；否则 mock 会掩盖客户端漏发头的问题）
        latest_p = paths[1]
        try:
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **kw):
                    return None

            op = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx), _NoRedirect())
            op.open(urllib.request.Request(base + latest_p, method="GET"), timeout=15)
            rep("D2b 缺 Accept 时不得直接回 JSON", False, "意外 200")
        except urllib.error.HTTPError as e:
            rep("D2b 缺 Accept → 302 到 /releases/tag/<tag>",
                e.code == 302 and "/releases/tag/" in (e.headers.get("Location") or ""),
                "status=%s location=%s" % (e.code, e.headers.get("Location")))

        # 探针路径 + 未知路径
        with urllib.request.urlopen(base + "/_probe/tls2", context=ctx, timeout=15) as r:
            rep("D3 探针路径可读", r.status == 200 and b"dprime2-tls2-probe" in r.read(), "status=%s" % r.status)
        try:
            urllib.request.urlopen(base + "/nope", context=ctx, timeout=15)
            rep("D4 未知路径 404", False, "意外 200")
        except urllib.error.HTTPError as e:
            rep("D4 未知路径 404", e.code == 404, "status=%s" % e.code)

        # 分类与字段
        time.sleep(0.4)
        recs = [json.loads(l) for l in io.open(log, encoding="utf-8") if l.strip()]
        kinds = {}
        for r in recs:
            kinds.setdefault(r["kind"], []).append(r["path"])
        rep("D5 客户端/探针请求已分类",
            all(p in kinds.get("client", []) for p in paths) and "/_probe/tls2" in kinds.get("probe", []),
            "client=%d probe=%d" % (len(kinds.get("client", [])), len(kinds.get("probe", []))))
        # 注意：首条记录可能是 tls_failure（D1 的裸 TCP 探测会让服务端握手失败），
        # 所以归属字段要在**client 记录**上校验，而不是 recs[0]。
        client_recs = [r for r in recs if r.get("kind") == "client"]
        rep("D6 记录含归属字段",
            bool(client_recs) and all(
                k in client_recs[0]
                for k in ("at", "kind", "method", "path", "ua", "remote",
                          "auth_header_present", "accept")),
            ",".join(sorted(client_recs[0].keys()))[:90] if client_recs else "无 client 记录")

        # D6b 关键：握手失败必须留痕 —— 这是 G3 负例成立的**前提**
        # （否则"TLS 被拒"与"请求压根没到"无法区分）
        tls_fails = [r for r in recs if r.get("kind") == "tls_failure"]
        rep("D6b 握手失败被记为 tls_failure（G3 负例的前提）",
            len(tls_fails) >= 1,
            "count=%d sample=%s" % (len(tls_fails),
                                    (tls_fails[0].get("tls_error") or "")[:60] if tls_fails else ""))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()

# ── E. Verdict 分类逻辑 ───────────────────────────────────────────────────
def synth(dirname, reqs, tls2_ok, proxy_detected, log_text=""):
    d = os.path.join(tmp, dirname)
    os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(d, "mock-requests.jsonl"), "w", encoding="utf-8") as f:
        for r in reqs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump({"ok": tls2_ok, "status": 200 if tls2_ok else 0},
              io.open(os.path.join(d, "tls2.json"), "w", encoding="utf-8"))
    json.dump({"proxy": {"detected": proxy_detected}},
              io.open(os.path.join(d, "preflight.json"), "w", encoding="utf-8"))
    json.dump({"all_ok": True}, io.open(os.path.join(d, "tls1.json"), "w", encoding="utf-8"))
    return d


def verdict_of(d):
    rc, out = ps("Verdict", d)
    rp = os.path.join(d, "dprime2-s1-receipt.json")
    if not os.path.isfile(rp):
        return None, out
    return json.load(io.open(rp, encoding="utf-8")), out


OWNER, REPO, TAG = "chenxiang6663635", "job-workbench", "v26.10.1"
P3 = ["/%s/%s/releases.atom" % (OWNER, REPO),
      "/%s/%s/releases/latest" % (OWNER, REPO),
      "/%s/%s/releases/download/%s/latest.yml" % (OWNER, REPO, TAG)]
mk = lambda p, k="client": {"at": "2026-10-23T00:00:00+00:00", "kind": k, "method": "GET",
                            "path": p, "ua": "ua", "remote": "127.0.0.1",
                            "auth_header_present": False}

r, _ = verdict_of(synth("e-ok", [mk(p) for p in P3] + [mk("/_probe/tls2", "probe")], True, False))
rep("E1 三路过 + 无阻断 → classification=NONE",
    bool(r) and r["tls"]["classification"] == "NONE", r["tls"]["classification"] if r else "no receipt")

r, _ = verdict_of(synth("e-proxy", [mk("/_probe/tls2", "probe")], False, True))
rep("E2 无客户端请求 + 检出代理 → BLOCKED_BY_PROXY_OR_RESOLUTION",
    bool(r) and r["tls"]["classification"] == "BLOCKED_BY_PROXY_OR_RESOLUTION",
    r["tls"]["classification"] if r else "no receipt")

r, _ = verdict_of(synth("e-tls", [mk(p) for p in P3], False, False))
rep("E3 tls2 失败 + 有客户端请求 → BLOCKED_BY_TLS_TRUST",
    bool(r) and r["tls"]["classification"] == "BLOCKED_BY_TLS_TRUST",
    r["tls"]["classification"] if r else "no receipt")

# ── F. 工作流结构 ─────────────────────────────────────────────────────────
wf = io.open(WF, encoding="utf-8").read()
for step in ("Preflight", "UpstreamProbe", "VerifyRc", "NewCert", "Tls1", "PrepareFixtures",
             "StartMock", "PatchHosts", "InstallAndRun", "MarkBoundary", "TlsNegative",
             "InstallCa", "Tls2", "Verdict", "Restore", "CleanupVerify"):
    rep("F1 工作流含步骤 %s" % step, step in wf, "")
# 顺序约束：负例必须在导入 CA 之前，boundary 在两者之间
_i_neg = wf.find("-Action InstallAndRun -Negative")
_i_mark = wf.find("-Action MarkBoundary")
_i_ca = wf.find("-Action InstallCa")
_i_pos = wf.find("-Action InstallAndRun `")
rep("F1b 负例前分界 → 负例 → 导入 CA → 正例 的顺序正确",
    -1 < _i_mark < _i_neg < _i_ca and _i_ca < _i_pos,
    "neg=%d mark=%d ca=%d pos=%d"
    "（P0-5：分界必须在负例之前，否则就绪探针的 tls_failure 污染负例判据）"
    % (_i_neg, _i_mark, _i_ca, _i_pos))
rep("F1c UpstreamProbe 在任何 PatchHosts 之前",
    -1 < wf.find("-Action UpstreamProbe") < wf.find("-Action PatchHosts"), "")
rep("F2 Verdict/Restore/CleanupVerify/Upload 都是 always()",
    wf.count("if: always()") >= 4, "count=%d" % wf.count("if: always()"))
rep("F3 permissions 含 actions: read（跨 run 取 artifact）",
    "actions: read" in wf, "")
rep("F4 PR 阶段跑 S1 自检（有 pull_request 触发）",
    "pull_request" in wf and "s1-lint" in wf,
    "只有 workflow_dispatch 时，PR 的绿色 CI 不含本次改动自检")
rep("F5 下载 RC 走固定 run-id 输入",
    "run-id: ${{ inputs.rc_run_id }}" in wf and "name: installer" in wf, "")

# ── G. 夹具与等价性护栏（2026-10-24：真实缺陷的回归钉子）──────────────────
ps1_src = strip_comments(io.open(PS1, encoding="utf-8").read())
mock_src = strip_comments(io.open(MOCK, encoding="utf-8").read())

rep("G1 PrepareFixtures 动作存在", "'PrepareFixtures'" in ps1_src, "")
rep("G2 StartMock 缺夹具时拒绝启动",
    "缺夹具" in ps1_src and "PrepareFixtures" in ps1_src,
    "原实现只放证书，三条路由必然 404")
rep("G3 工作流含 PrepareFixtures 步骤", "PrepareFixtures" in wf, "")
rep("G4 mock 校验 Accept: application/json",
    'LATEST_PATH' in mock_src and '"application/json" not in' in mock_src,
    "否则客户端漏发头也会被 mock 判成功")
rep("G5 mock 有 302 落点 /releases/tag/", "/releases/tag/" in mock_src, "")
rep("G6 夹具记录派生关系（非自造元数据）",
    "派生" in ps1_src and "latest.yml version" in ps1_src, "")

# --- 2026-10-24 审查修正的回归钉子 ---
rep("G7 G1-b 保留两层降级链（外层直含 resources，降级仅作防御）",
    "$PLUGINSDIR/app-64.7z" in ps1_src and "app-update.yml" in ps1_src,
    "2026-10-24 实物实测：官方 26.10.0 外层 7z 归档**直接含** resources/app-update.yml"
    "（104 B，无 app-64.7z、无 $PLUGINSDIR），单层即可成功；降级链是对未来"
    "oneClick / nsis-web 形态的防御，不得写成当前包的既定结构")
rep("G8 G1-b 比对未执行时记缺口而非假 FAIL",
    "比对未能执行" in ps1_src and "known_gaps = $knownGaps" in ps1_src,
    "工具失败 ≠ 产品失败，但缺口必须可见")
rep("G9 负例停客户端杀整棵进程树",
    "taskkill /PID $c.Id /T /F" in ps1_src,
    "Stop-Process 不杀 Electron/backend 子进程，残留会污染正例")
rep("G10 G3 判据不依赖错误文本（cert_like 仅为佐证）",
    "cert_like_hits" in ps1_src and "TLS_REJECTED_AS_EXPECTED" in ps1_src,
    "服务端视角可能只见 EOF，把证书字样当判据会假阴性")

# ── 第十三轮审查修正的回归钉子（PR #391 第二轮）────────────────────────
# 这一轮全部是「执行环境 / 生命周期 / 证据真实性」类缺陷，离线自检必须钉住。
rep("P0 certcheck.py 在 sparse-checkout 清单内",
    "scripts/dprime2-certcheck.py" in wf,
    "Tls1 对它 throw；漏检出则 S1 首跑在 TLS-1 阶段失败")
rep("P0-1 Verdict 不判定环境恢复（交 CleanupVerify 独立判定）",
    "CleanupVerify 独立判定" in ps1_src and "S1-10 环境已恢复" not in ps1_src,
    "Verdict 跑在 Restore 之前，检查「已恢复」即恒 FAIL")
rep("P0-2 正例实际等待观察窗口（非只算时间戳）",
    "waited_seconds" in ps1_src and "$discoveryAt" in ps1_src,
    "updater.js 启动约 5s 后才检查；不等待会得到假阴性")
rep("P0-3 Save-State 字段级合并（不整对象覆盖）",
    "$merged" in ps1_src and "Get-State" in ps1_src,
    "整对象覆盖会丢 mock_pid → Restore 停不掉 mock → CleanupVerify 失败"
    "（判据只查代码符号，不查注释文字——ps1_src 是剥注释版）")
rep("P0-4 不用 ArgumentList.AddRange",
    "AddRange" not in ps1_src,
    "ProcessStartInfo.ArgumentList 是 Collection<string>，无 AddRange")
rep("P0-5 负例启动前打日志分界",
    wf.count("MarkBoundary") >= 2 and "negative-phase-start" in wf,
    "分界打在负例判定之后，会让就绪探针的 tls_failure 污染负例判据")
rep("P0-6 Verdict 按结论退出（非恒 exit 0）",
    "if ($blocking) { exit 1 }" in ps1_src,
    "恒 exit 0 会让 S1_FAIL 也显示绿色 CI，违反 fail-closed")
rep("P0-7a S1-3b 不是恒真断言",
    "probeOnRequired" in ps1_src,
    "Count -ge 0 -and Count -ge 0 恒真，无证据价值")
rep("P0-7b S1-7 不是传 $true 的范围声明",
    "display_version=$verNow" in ps1_src,
    "范围声明不能伪装成测试成功")
rep("UP-3 不以 HTTP 200 代替 tag_name",
    "-or $withJson.final_status -eq 200" not in ps1_src,
    "只要 200 就通过是假阳性")
rep("G1-b GAP 阻断 S1_PASS",
    "elseif ($g1GapText) { 'S1_INCOMPLETE' }" in ps1_src,
    "硬门禁未完成（工具问题）不得判 PASS")
rep("PR 阶段跑 S1 自检（lint job）",
    "s1-lint" in wf and "pull_request" in wf,
    "只有 workflow_dispatch 时，PR 的绿色 CI 不含本次自检")
rep("收据缺失使 job 失败（非 warn）",
    "if-no-files-found: error" in wf,
    "收据是唯一可审计产物，缺失即证据链断裂")

# ── 汇总 ─────────────────────────────────────────────────────────────────
shutil.rmtree(tmp, ignore_errors=True)
passed = sum(1 for _, ok, _ in results if ok is True)
skipped = sum(1 for _, ok, _ in results if ok is None)
failed = [(n, d) for n, ok, d in results if ok is False]
print("\n" + "=" * 70)
print("离线自检：%d 通过 / %d 跳过 / %d 失败（共 %d）"
      % (passed, skipped, len(failed), len(results)))
for n, d in failed:
    print("  FAIL: %s — %s" % (n, d))
if skipped:
    print("  （SKIP 项需要 DPRIME2_RC_ROOT 指向真实 RC 目录；跳过不等于通过）")
print("=" * 70)
sys.exit(0 if not failed else 1)
