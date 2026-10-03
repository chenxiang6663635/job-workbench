#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SBOM 生成（issue #206）：从锁文件产出 SPDX 2.3 JSON，随 Release 挂出。

依赖爆 CVE 时，靠它直接回答「哪个版本受影响」——不必重建当时的依赖树。

为什么自研而不是 syft / cyclonedx 一类现成工具（留给后来者的说明，
防"重复造轮子"的质疑）：
- CI 零新增安装：外部工具在 Windows runner 上要 choco / npx 现场安装（联网、
  耗时、且命令行语法在工具版本之间会漂）；本脚本只用标准库。
- 输入是**锁文件**（requirements.lock / package-lock.json），SBOM 的实质就是
  「锁文件 → 标准格式」的搬运——逻辑短到能被 pytest 完整覆盖。
- 输出是 SPDX 2.3 最小合法结构：下游 CVE 工具（grype / Dependency-Track 等）
  按 name + versionInfo 就能建索引，不依赖任何分发工具的私有字段。

用法（CI 与本地同一条命令）：
    python tools/gen_sbom.py --root . --version 26.10.0 --out sbom.spdx.json
"""

import argparse
import datetime
import io
import json
import os
import re
import sys
import uuid

REQ_REL = os.path.join("web", "backend", "requirements.lock")
LOCK_REL = os.path.join("web", "frontend", "package-lock.json")

# requirements.lock 的一条包行：`name==version`（行尾可能有续行反斜杠）。
_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$")


def parse_requirements_lock(text):
    """uv pip compile 产物 → [(name, version)]。

    格式（实测）：`altgraph==0.17.5 \\` 后跟缩进的 `--hash=…` 续行，
    段尾 `# via pyinstaller` 注释行。只认顶格的 `name==version`，
    续行 / 注释 / 空行一律跳过。
    """
    packages = []
    for raw in text.splitlines():
        head = raw.strip()
        if not head or head.startswith("#") or head.startswith("-"):
            continue
        head = head.rstrip("\\").strip()
        match = _REQ_LINE.match(head)
        if match:
            packages.append((match.group(1), match.group(2)))
    return packages


def parse_package_lock(data):
    """npm package-lock.json（lockfileVersion 2/3）→ [(name, version)]。

    取 `packages` 字典里 `node_modules/…` 的条目（根条目 "" 是工作区自身，
    跳过）；嵌套安装（`node_modules/a/node_modules/b`）取最后一段名字，
    scoped 包（`@scope/name`）整体保留。
    """
    packages = []
    for path, meta in (data.get("packages") or {}).items():
        if not path.startswith("node_modules/"):
            continue
        name = meta.get("name") or path.split("node_modules/")[-1]
        version = meta.get("version")
        if name and version:
            packages.append((name, version))
    return packages


def _safe(text):
    """SPDXID 只允许 [A-Za-z0-9.-]，其余字符一律换成 `-`。"""
    return re.sub(r"[^A-Za-z0-9.-]", "-", text)


def _spdx_packages(kind, items):
    """一条链 → SPDX packages 数组。

    去重按 (name, version)；同名多版本时 SPDXID 附版本号——SPDXID 是全文档
    唯一键，重名不处理会产出**非法**文档（下游工具导入即失败）。
    """
    unique = sorted(set(items))
    counts = {}
    for name, _version in unique:
        counts[name] = counts.get(name, 0) + 1

    out = []
    for name, version in unique:
        suffix = _safe(name)
        if counts[name] > 1:
            suffix = "%s-%s" % (suffix, _safe(version))
        out.append({
            "name": name,
            "SPDXID": "SPDXRef-Package-%s-%s" % (kind, suffix),
            "versionInfo": version,
            # 锁文件里没有许可证事实，四字段按 SPDX 规范填 NOASSERTION（不猜）。
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        })
    return out


def build_spdx(python_pkgs, npm_pkgs, version, created):
    """两条链 + 版本号 + 创建时间 → SPDX 2.3 文档（dict）。"""
    packages = _spdx_packages("python", python_pkgs) + _spdx_packages("npm", npm_pkgs)
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "job-workbench-%s" % version,
        "documentNamespace": (
            "https://github.com/chenxiang6663635/job-workbench/sbom/%s-%s"
            % (version, uuid.uuid4().hex)
        ),
        "creationInfo": {
            "created": created,
            "creators": ["Tool: tools/gen_sbom.py"],
        },
        "packages": packages,
    }


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    parser = argparse.ArgumentParser(description="从锁文件产出 SPDX 2.3 JSON（SBOM）")
    parser.add_argument("--root", default=".", help="仓库根（默认当前目录）")
    parser.add_argument("--version", required=True, help="版本号（如 26.10.0）")
    parser.add_argument("--out", default="sbom.spdx.json", help="输出文件路径")
    args = parser.parse_args(argv)

    req_path = os.path.join(args.root, REQ_REL)
    lock_path = os.path.join(args.root, LOCK_REL)
    for path in (req_path, lock_path):
        if not os.path.isfile(path):
            print("找不到锁文件：%s" % path, file=sys.stderr)
            return 1

    with io.open(req_path, encoding="utf-8") as handle:
        python_pkgs = parse_requirements_lock(handle.read())
    with io.open(lock_path, encoding="utf-8") as handle:
        npm_pkgs = parse_package_lock(json.load(handle))

    # 空清单是硬失败：产出「零包的合法 SBOM」比不产出更糟——验收会假绿。
    if not python_pkgs or not npm_pkgs:
        print("解析结果为空（python %d / npm %d）——锁文件格式变了吗？"
              % (len(python_pkgs), len(npm_pkgs)), file=sys.stderr)
        return 1

    document = build_spdx(python_pkgs, npm_pkgs, args.version, _now_iso())
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print("已产出 %s：python %d 包 + npm %d 包"
          % (args.out, len(python_pkgs), len(npm_pkgs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
