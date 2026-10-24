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
    return (x509.load_pem_x509_certificate(ca_pem[0].encode()),
            x509.load_pem_x509_certificate(srv_pem[-1].encode()))


def _check_identity(ca, srv, add):
    """T1-1 … T1-5：主体、SAN、有效期、EKU、CA 基本约束。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    add("T1-1 服务器证书 CN=github.com",
        srv.subject.rfc4514_string() in ("CN=github.com",), srv.subject.rfc4514_string())

    try:
        san = srv.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName)
        add("T1-2 SAN 含 DNS:github.com", "github.com" in names, names)
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

    ca, srv = _load(d)
    if ca is None:
        print(json.dumps({"all_ok": False, "rows": [
            {"id": "T1-0 PEM 可解析", "ok": False, "detail": "ca/server PEM 缺失"}]},
            ensure_ascii=False))
        return 1

    _check_identity(ca, srv, add)
    _check_crypto(ca, srv, d, add)

    all_ok = all(r["ok"] for r in rows)
    print(json.dumps({
        "mode": "offline-structure-only",
        "handshake_performed": False,
        "all_ok": all_ok,
        "rows": rows,
    }, ensure_ascii=False))
    return 0 if all_ok else 5


if __name__ == "__main__":
    sys.exit(main())
