# -*- coding: utf-8 -*-
"""DSH 插件平台子包打包前置校验（2026-10-21，G1 例外 #3）。

为什么需要独立脚本：`build_mcp_exe.ps1` 失败时可能留下**旧的 bin/**（旧 CA 清单）。
构建脚本在开始前已把 prebuilds.json 改名为 .stale（失败即缺清单），本脚本是打包前的
最后一道闸：清单存在 + 全量哈希匹配 + 随包 PEM 等于已审核安全基线，任一不符即 exit 1。

用法（**npm pack 之前必须跑**，构建脚本成功路径也会自动调用）：
    python scripts/verify_mcp_prebuilds.py

判据：
  1. `integrations/dsh/platform/win32-x64/prebuilds.json` 存在（失败构建会缺失）；
  2. 清单里每个文件都存在且 SHA256 一致（0 不符 / 0 缺失）；
  3. `bin/_internal/certifi/cacert.pem` 存在、不含 `emSign ECC Root CA - G3`、
     且 SHA256 == 已审核基线（与 build_mcp_exe.ps1 的 $CertifiSafePemSha 同一值）；
  4. 无残留 `prebuilds.json.stale`（有 = 上次构建未走完，提示排查）。

零第三方依赖：只用标准库，可在任意 Python 3.12 里跑。
"""
import hashlib
import json
import os
import sys

# 中文 Windows 控制台是 GBK：中文输出会 UnicodeEncodeError（冒烟脚本同款处理）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "integrations", "dsh", "platform", "win32-x64")
MANIFEST = os.path.join(OUT_DIR, "prebuilds.json")
STALE = os.path.join(OUT_DIR, "prebuilds.json.stale")
PEM_REL = os.path.join("bin", "_internal", "certifi", "cacert.pem")
CERTIFI_MIN = "2026.10.19"
CERTIFI_SAFE_PEM_SHA = "50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785"
G3_LABEL = "emSign ECC Root CA - G3"


def _fail(msg):
    print("FAIL: %s" % msg)
    sys.exit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.isfile(MANIFEST):
        if os.path.isfile(STALE):
            _fail("prebuilds.json 缺失但存在 prebuilds.json.stale——上次构建未走完（失败或中断），"
                  "旧制品不得打包。重跑 scripts\\build_mcp_exe.ps1 直到成功。")
        _fail("prebuilds.json 不存在——先跑 scripts\\build_mcp_exe.ps1")
    if os.path.isfile(STALE):
        _fail("存在 prebuilds.json.stale——上次构建未清理干净，先确认构建成功并删除该文件")

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    files = manifest.get("files") or {}
    if not files:
        _fail("prebuilds.json 没有 files 清单")

    # 元数据一致性（2026-10-21 审计）：G4 改版本后若忘记重建运行时，哈希仍一致、
    # 旧二进制会静默通过——三方版本必须同时对上，status / schemaVersion 受控。
    if manifest.get("schemaVersion") != 1:
        _fail("prebuilds.json.schemaVersion=%r（期望 1）" % manifest.get("schemaVersion"))
    if manifest.get("status") != "built":
        _fail("prebuilds.json.status=%r（期望 'built'）" % manifest.get("status"))

    def _pkg_version(path, label):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("version")
        except (OSError, ValueError) as exc:
            _fail("读不到%s版本：%s（%s）" % (label, path, exc))

    platform_version = _pkg_version(os.path.join(OUT_DIR, "package.json"), "平台子包")
    main_version = _pkg_version(os.path.join(os.path.dirname(OUT_DIR), "..", "package.json"), "DSH 主包")
    if not (manifest.get("version") == platform_version == main_version):
        _fail("三方版本不一致：manifest=%r 平台子包=%r 主包=%r——改版本后必须重建 MCP 运行时"
              % (manifest.get("version"), platform_version, main_version))

    missing = []
    mismatched = []
    for rel, expected in files.items():
        full = os.path.join(OUT_DIR, rel)
        if not os.path.isfile(full):
            missing.append(rel)
            continue
        if sha256_file(full) != expected:
            mismatched.append(rel)
    if missing or mismatched:
        _fail("清单与实际产物不符：缺失 %d 个 %s；哈希不符 %d 个 %s"
              % (len(missing), missing[:5], len(mismatched), mismatched[:5]))

    # 反向集合（2026-10-21 审计）：bin/ 下每个实际文件都必须登记。
    # 215/215 只证明登记的都对，不证明目录里恰好只有这 215 个——多一个未登记载荷即拒。
    bin_dir = os.path.join(OUT_DIR, "bin")
    if os.path.isdir(bin_dir):
        actual = []
        for dirpath, _dirnames, filenames in os.walk(bin_dir):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                actual.append(os.path.relpath(full, OUT_DIR).replace("\\", "/"))
        unregistered = sorted(r for r in actual if r not in files)
        if unregistered:
            _fail("bin/ 中有 %d 个未登记文件（旧构建残留或未审核载荷）：%s"
                  % (len(unregistered), unregistered[:5]))

    pem = os.path.join(OUT_DIR, PEM_REL)
    if not os.path.isfile(pem):
        _fail("随包 CA 清单缺失：%s" % PEM_REL)
    with open(pem, "rb") as f:
        pem_text = f.read().decode("utf-8", "replace")
    if G3_LABEL in pem_text:
        _fail("随包 CA 清单含受影响的 %s（PYSEC-2026-4320）——拒绝打包" % G3_LABEL)
    pem_sha = sha256_file(pem)
    if pem_sha != CERTIFI_SAFE_PEM_SHA:
        _fail("随包 PEM SHA256 %s 与已审核基线 %s 不一致——拒绝打包"
              % (pem_sha, CERTIFI_SAFE_PEM_SHA))

    print("PACK GATE OK：%d 个文件哈希一致、无 G3、PEM 等于 %s 基线（certifi >= %s）"
          % (len(files), CERTIFI_SAFE_PEM_SHA[:12], CERTIFI_MIN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
