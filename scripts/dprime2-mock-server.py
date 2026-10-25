# -*- coding: utf-8 -*-
"""D'-2 S1 受控更新源 mock（最小实现，只绑回环，无任何凭据）。

用途：在一性次 runner 上顶替 github.com 的三条更新请求，供官方 26.10.0 客户端
     「发现 26.10.1」。**不下载、不安装、不重启**（那属 S2/S3）。

设计约束（与 dprime-2-s1-contract.md v3 对齐）：
  - 只绑 127.0.0.1（默认 443；离线自检用高位端口），不接受凭据；
  - 每条请求写 JSONL，含 kind=client|probe，用于把**探针请求**与**客户端请求**分开；
  - 永不重定向到真实 GitHub；未知路径一律 404；
  - 不打印、不使用 Authorization 头，只记录「是否存在」；
  - 不关闭 TLS 校验：必须加载真实服务端证书链。
"""

import argparse
import datetime
import json
import os
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OWNER = "chenxiang6663635"
REPO = "job-workbench"
TAG = "v26.10.1"

LATEST_PATH = "/%s/%s/releases/latest" % (OWNER, REPO)
TAG_PATH = "/%s/%s/releases/tag/%s" % (OWNER, REPO, TAG)

ROUTES = {
    "/%s/%s/releases.atom" % (OWNER, REPO): ("application/atom+xml", "atom.xml"),
    LATEST_PATH: ("application/json", "latest.json"),
    "/%s/%s/releases/download/%s/latest.yml" % (OWNER, REPO, TAG): ("text/yaml", "latest.yml"),
    # 302 的落点：与真实 GitHub 一致（/releases/latest 无 JSON Accept 时跳这里）
    TAG_PATH: ("text/html; charset=utf-8", "tag.html"),
    "/_probe/tls2": ("text/plain", "probe.txt"),
}

PROBE_PREFIX = "/_probe/"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    server_version = "dprime2-mock/1.0"
    protocol_version = "HTTP/1.1"

    # 不把请求细节打到 stdout（避免污染 workflow 日志）；只写 JSONL
    def log_message(self, fmt, *args):  # noqa: A003
        return

    def _record(self, method):
        path = self.path.split("?", 1)[0]
        had_query = "?" in self.path
        rec = {
            "at": now(),
            "kind": "probe" if path.startswith(PROBE_PREFIX) else "client",
            "method": method,
            "path": path,
            "had_query": had_query,
            "ua": (self.headers.get("User-Agent") or "")[:200],
            "remote": self.client_address[0] if self.client_address else "",
            "auth_header_present": "Authorization" in self.headers,
            # Accept 是**判据**不只是日志：GitHubProvider.getLatestTagName() 用
            # `Accept: application/json` 取 JSON；缺这个头真实 GitHub 会 302 到 HTML。
            # 记录它以证明客户端确实发了正确的头（S1-G2）。
            "accept": (self.headers.get("Accept") or "")[:200],
        }
        try:
            rec["tls_version"] = self.connection.version() if hasattr(self.connection, "version") else None
            cipher = self.connection.cipher() if hasattr(self.connection, "cipher") else None
            rec["cipher"] = cipher[0] if cipher else None
        except Exception:  # noqa: BLE001 —— 记录失败不能影响响应
            pass
        try:
            with open(self.server.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return rec

    def _serve(self, method):
        rec = self._record(method)

        # 与真实 GitHub 的等价性（2026-10-24 补）：
        # electron-updater 6.8.9 的 GitHubProvider.getLatestTagName() 对 github.com 走的是
        #   GET /<owner>/<repo>/releases/latest  +  Accept: application/json  →  JSON.parse(...).tag_name
        # 真实站点**只有带这个 Accept 才回 JSON**，否则 302 到 /releases/tag/<tag> 的 HTML，
        # 客户端 JSON.parse 必然失败。若 mock 无条件回 JSON，等于放宽契约：
        # 客户端漏发 Accept 时我们仍会"成功"，把真实环境会失败的场景伪装成通过。
        if rec["path"] == LATEST_PATH and "application/json" not in (rec.get("accept") or ""):
            self.send_response(302)
            self.send_header("Location", TAG_PATH)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        hit = ROUTES.get(rec["path"])
        if hit is None:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if method == "GET":
                self.wfile.write(body)
            return
        ctype, fname = hit
        full = os.path.join(self.server.root_dir, fname)
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            body = b"fixture missing\n"
            self.send_response(500)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if method == "GET":
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._serve("GET")

    def do_HEAD(self):  # noqa: N802
        self._serve("HEAD")


class TlsRecordingServer(ThreadingHTTPServer):
    """在 get_request() 里做 TLS 握手，**失败也要留痕**。

    为什么不能沿用 `httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)`：
    那样握手在 accept 阶段完成，失败时请求**根本到不了 handler**，日志里什么都不会留下。
    于是"TLS 被拒"与"请求压根没到（DNS/代理/hosts 没生效）"完全无法区分——
    而 S1-G3 的负例恰恰要求证明"到了但被拒"。
    记录 kind=tls_failure 后，负例判据才成立：
      · 有 tls_failure 记录  → 请求确实抵达 127.0.0.1:443，但证书不被接受
      · 无任何记录           → 请求没到，属 BLOCKED_BY_PROXY_OR_RESOLUTION，不是 TLS 失败
    """

    daemon_threads = True

    def __init__(self, addr, handler, ssl_context, root_dir, log_path):
        self.ssl_context = ssl_context
        self.root_dir = root_dir
        self.log_path = log_path
        super().__init__(addr, handler)

    def get_request(self):
        sock, addr = super().get_request()
        try:
            tls_sock = self.ssl_context.wrap_socket(sock, server_side=True)
            return tls_sock, addr
        except (ssl.SSLError, OSError) as exc:
            self._log_tls_failure(addr, exc)
            try:
                sock.close()
            except OSError:
                pass
            raise

    def _log_tls_failure(self, addr, exc):
        rec = {
            "at": now(),
            "kind": "tls_failure",
            "method": None,
            "path": None,
            "remote": addr[0] if addr else "",
            "tls_error": str(exc)[:300],
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="含 atom.xml / latest.json / latest.yml / probe.txt / server.crt / server.key")
    ap.add_argument("--log", required=True, help="请求日志 JSONL 路径")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--min-tls", default="TLSv1_2")
    args = ap.parse_args()

    missing = [n for n in ("atom.xml", "latest.json", "latest.yml", "probe.txt",
                           "server.crt", "server.key") if not os.path.isfile(os.path.join(args.root, n))]
    if missing:
        print("FATAL missing fixtures: %s" % ", ".join(missing), file=sys.stderr)
        raise SystemExit(2)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = getattr(ssl.TLSVersion, args.min_tls.replace(".", "_"), ssl.TLSVersion.TLSv1_2)
    ctx.load_cert_chain(os.path.join(args.root, "server.crt"),
                        os.path.join(args.root, "server.key"))

    # 2026-10-25 S1-C run 40194676744：mock 起进程后 20 秒仍 listening=False，
    # 而 preflight 显示 443 空闲（Test-Tcp 探测不到**保留端口段**——
    # GitHub runner 上 Hyper-V/WSL 常保留大段高位端口，`netsh excludedportrange`
    # 里的端口 bind() 报 WSAEACCES，但 TCP 探测显示"空闲"）。
    # 对策：--port 传 0，由 OS 分配一个保证可用的端口；实际端口写进
    # stdout 首行（MOCK_PORT=<n>）与 port.json，调用方读它而非假定端口。
    httpd = TlsRecordingServer((args.host, args.port), Handler, ctx, args.root, args.log)
    actual_port = httpd.server_address[1]

    print("MOCK_PORT=%d" % actual_port)
    print("mock listening on https://%s:%d (routes=%d)" % (args.host, actual_port, len(ROUTES)))
    try:
        with open(os.path.join(args.root, os.pardir, "port.json"), "w", encoding="utf-8") as f:
            f.write('{"port": %d}\n' % actual_port)
    except OSError:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
