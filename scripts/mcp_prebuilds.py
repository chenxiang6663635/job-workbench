# -*- coding: utf-8 -*-
"""生成平台子包的 prebuilds.json：相对子包根的**全量 sha256 清单**（#271 P2-2）。

清单用途与 `libreoffice-kit` 同款：发布对账（exe 与随它一起落地的运行时可逐文件核验），
以及将来运行时的完整性快照。由 `scripts/build_mcp_exe.ps1` 在落位后调用。

用法：
    python scripts/mcp_prebuilds.py [平台子包目录] [版本]
默认：integrations/dsh/platform/win32-x64 + integrations/dsh/package.json 的 version。
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(pkg_dir, version):
    # 清单一律以 **bin/** 为界：引擎可执行文件 + 随它的运行时。
    # 不把 package.json / .gitignore 之类清单文件混进来——它们由 npm 包自身管理，
    # 哈希清单只回答「运行时载荷是不是这一份」。
    files = {}
    bin_dir = os.path.join(pkg_dir, "bin")
    for base, _dirs, names in os.walk(bin_dir):
        for name in names:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, pkg_dir).replace(os.sep, "/")
            files[rel] = sha256(full)
    return {
        "schemaVersion": 1,
        "version": version,
        "platform": os.path.basename(os.path.normpath(pkg_dir)),
        "status": "built",
        "engine": {"kind": "native", "executable": "bin/jobws-mcp.exe"},
        "files": dict(sorted(files.items())),
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pkg_dir = argv[0] if argv else os.path.join(
        ROOT, "integrations", "dsh", "platform", "win32-x64")
    if len(argv) > 1:
        version = argv[1]
    else:
        with io.open(os.path.join(ROOT, "integrations", "dsh", "package.json"),
                     encoding="utf-8") as handle:
            version = json.load(handle)["version"]
    doc = build(pkg_dir, version)
    with io.open(os.path.join(pkg_dir, "prebuilds.json"), "w",
                 encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print("prebuilds.json：%d 个文件，version=%s" % (len(doc["files"]), version))
    print("exe sha256 = %s" % doc["files"].get("bin/jobws-mcp.exe"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
