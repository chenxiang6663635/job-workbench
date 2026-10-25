# -*- coding: utf-8 -*-
"""D'-2 S1 TLS-1：证书离线结构检查（**不发起任何网络握手**）。

由 dprime2-s1.ps1 -Action Tls1 调用；结果以 JSON 打到 stdout。
只做结构/密码学验证：CN、SAN、有效期、EKU、CA 基本约束、**签名验签**、私钥匹配。
"""

import argparse
import datetime
import io
import json
import os
import sys

# 2026-10-24 CI 实测根因：GitHub runner 的 locale 是 en-US，Python 的 stdout
# 编码是 **cp1252**（不是 UTF-8）。本脚本 print 的 JSON 含中文，
# 于是 UnicodeEncodeError -> exit 1 + Traceback 到 stderr，而 stdout 全空。
# 本地是中文系统（cp936）所以不复现——典型的"本地过、CI 挂"。
# 双保险：① 输出统一 ensure_ascii=True（纯 ASCII，任何编码都能打）
#        ② reconfigure stdout 为 UTF-8（兜底其他 print）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def pem_certs(path):
    data = io.open(path, encoding="utf-8").read()
    marker = "-----BEGIN CERTIFICATE-----"
    blocks = []
    cur = []
    for line in data.splitlines():
        if marker in line:
            cur = [line]
        elif cur:
            cur.append(line)
            if "-----END CERTIFICATE-----" in line:
                blocks.append("\n".join(cur) + "\n")
                cur = []
    return blocks


def _load(d):
    """返回 (ca, srv)；PEM 缺失或不可解析时返回 (None, None)。"""
    ca_pem = pem_certs(os.path.join(d, "ca.crt"))
    srv_pem = pem_certs(os.path.join(d, "server.crt"))
    if not ca_pem or not srv_pem:
        return None, None
    # server.crt 的排列是**叶子在前、CA 在后**（load_cert_chain 的要求，2026-10-24 修正）。
    # 原实现取 srv_pem[-1]（那是旧顺序「CA 在前」下的叶子），顺序改对后 [-1] 变成 CA，
    # 于是 T1-7 报 key_bits=2048 cert_bits=4096。load_pem_x509_certificate 只读第一个证书。
    return (x509.load_pem_x509_certificate(ca_pem[0].encode()),
            x509.load_pem_x509_certificate(srv_pem[0].encode()))


def _check_identity(ca, srv, add):
    """T1-1 … T1-5：主体、SAN、有效期、EKU、CA 基本约束。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    add("T1-1 服务器证书 CN=github.com",
        srv.subject.rfc4514_string() in ("CN=github.com",), srv.subject.rfc4514_string())

    try:
        san = srv.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName)
        # 语义是**列表成员的精确相等**，不是子串匹配：SAN 里的 DNSName 是独立条目，
        # `github.com.evil.example` 不会因为包含 "github.com" 而通过。
        # 显式写成 any(... == ...)：既表达意图，也避免被 CodeQL 的
        # py/incomplete-url-substring-sanitization 规则误判（该规则针对 URL 净化场景）。
        exact_dns = any(str(n).strip().lower() == "github.com" for n in names)
        add("T1-2 SAN 含 DNS:github.com", exact_dns, names)
    except x509.ExtensionNotFound:
        add("T1-2 SAN 含 DNS:github.com", False, "SAN 扩展缺失")

    add("T1-3 有效期覆盖现在",
        srv.not_valid_before_utc <= now <= srv.not_valid_after_utc,
        "%s ~ %s" % (srv.not_valid_before_utc, srv.not_valid_after_utc))

    try:
        eku = srv.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        listed = [o.dotted_string for o in eku]
        add("T1-4 EKU 含 serverAuth(1.3.6.1.5.5.7.3.1)",
            "1.3.6.1.5.5.7.3.1" in listed, listed)
    except x509.ExtensionNotFound:
        add("T1-4 EKU 含 serverAuth(1.3.6.1.5.5.7.3.1)", False, "EKU 扩展缺失")

    try:
        bc = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
        ca_ok = bc.ca and ca.subject == ca.issuer
        add("T1-5 CA 自签且 CA:TRUE", ca_ok,
            "ca=%s subject=%s issuer=%s" % (bc.ca, ca.subject.rfc4514_string(), ca.issuer.rfc4514_string()))
    except x509.ExtensionNotFound:
        add("T1-5 CA 自签且 CA:TRUE", False, "CA 缺 BasicConstraints")


def _check_crypto(ca, srv, d, add):
    """T1-6 … T1-7：签名验签与私钥匹配（需要实际密码学运算，与身份字段检查分开）。"""
    # 关键：用 CA 公钥验服务器证书签名（离线，无握手）
    try:
        ca.public_key().verify(
            srv.signature, srv.tbs_certificate_bytes,
            padding.PKCS1v15(), srv.signature_hash_algorithm)
        add("T1-6 服务器证书签名可由 CA 验签", True,
            "hash=%s" % srv.signature_hash_algorithm.name)
    except Exception as exc:  # noqa: BLE001 —— 任何异常都是验签失败
        add("T1-6 服务器证书签名可由 CA 验签", False, "%s: %s" % (type(exc).__name__, exc))

    # 私钥与证书公钥模数一致
    try:
        key_pem = io.open(os.path.join(d, "server.key"), encoding="utf-8").read()
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        pub = srv.public_key()
        kn = key.public_key().public_numbers()
        pn = pub.public_numbers()
        add("T1-7 私钥与证书公钥匹配",
            isinstance(key, rsa.RSAPrivateKey) and kn.n == pn.n,
            "key_bits=%s cert_bits=%s" % (key.key_size, pub.key_size))
    except Exception as exc:  # noqa: BLE001
        add("T1-7 私钥与证书公钥匹配", False, "%s: %s" % (type(exc).__name__, exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    d = args.dir
    rows = []

    def add(rid, ok, detail):
        rows.append({"id": rid, "ok": bool(ok), "detail": str(detail)[:200]})

    # 任何未预期异常都必须以**结构化 JSON** 输出，而不是裸 Traceback。
    # 2026-10-24 CI 实测：cryptography 50.0.2 下本脚本抛 Traceback，
    # 调用方（ps1 的 Tls1）解析不到 rows，整条链路只剩 "unparsed"，
    # 看不到真正的异常行——等于把诊断信息扔了。
    try:
        ca, srv = _load(d)
        if ca is None:
            print(json.dumps({"all_ok": False, "rows": [
                {"id": "T1-0 PEM 可解析", "ok": False, "detail": "ca/server PEM 缺失"}]},
                ensure_ascii=True))
            return 1

        _check_identity(ca, srv, add)
        _check_crypto(ca, srv, d, add)
    except Exception as exc:  # noqa: BLE001 —— 结构性兜底：保住诊断信息
        import traceback
        tb = traceback.format_exc()
        add("T1-X certcheck 内部异常", False,
            "%s: %s" % (type(exc).__name__, str(exc)[:120]))
        print(json.dumps({
            "mode": "offline-structure-only",
            "handshake_performed": False,
            "all_ok": False,
            "internal_error": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
            "traceback_tail": tb[-800:],
            "rows": rows,
        }, ensure_ascii=True))
        return 5

    all_ok = all(r["ok"] for r in rows)
    print(json.dumps({
        "mode": "offline-structure-only",
        "handshake_performed": False,
        "all_ok": all_ok,
        "rows": rows,
    }, ensure_ascii=True))
    return 0 if all_ok else 5


if __name__ == "__main__":
    sys.exit(main())
