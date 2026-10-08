# -*- coding: utf-8 -*-
"""DSH bundle 的兼容契约守卫（#271 P2-4）。

官方机制（2026-10-07 从 DSH 自带文档实证，见 integrations/dsh/README.md 第七节）：
- DSH 在导入插件与加载组合包前，检查其 `peerDependencies` 里对 `@deepseek-ai/dsh` /
  `@deepseek-ai/dsh-*` 的声明，与宿主运行时版本比较：每个声明的范围都必须匹配；
  预发布版本参与匹配；**未声明不施加约束；无效范围视为不兼容**。被拒的组合包会被
  整体跳过（`skippedBundles`）——所以 peerDependencies 是这个包的**真实生效面**。
- `engines.dsh` **不被强制**（官方原话「兼容性仅作声明」），但作为声明性元数据保留。

本测试钉三件事：① cordis.patch.yml 引用的官方包 ↔ peerDependencies **双向一致**
（少声明 = 未覆盖的真依赖；多声明 = 会挡住本可兼容宿主的冗余约束）；② 范围形态
= 带预发布分支的保守上限（node-semver 只在同元组比较符带预发布标签时放行预发布
宿主——没有分支的范围会静默排除 rc 宿主）；③ `!!js` 自引用与 patch 文件存在性
（这两处静默坏掉的表现是「技能行 Cannot find module / 组合包不装载」）。
"""

import io
import json
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSH_DIR = os.path.join(ROOT_DIR, "integrations", "dsh")
PKG_PATH = os.path.join(DSH_DIR, "package.json")
PATCH_PATH = os.path.join(DSH_DIR, "cordis.patch.yml")

# 带预发布分支的保守上限两种合法形态（^0.2.0-rc.N 或 >=0.2.0-rc.N <0.3）
PEER_RANGE_RE = re.compile(r"^(?:\^0\.2\.0-rc\.\d+|>=0\.2\.0-rc\.\d+ <0\.3)$")
ENGINES_RANGE_RE = re.compile(r"^>=0\.2\.0-rc\.\d+ <0\.3$")


def _manifest():
    with io.open(PKG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _patch_referenced_dsh_packages():
    """cordis.patch.yml 非注释行里引用的全部 @deepseek-ai/* 包名（去重）。"""
    with io.open(PATCH_PATH, encoding="utf-8") as handle:
        text = handle.read()
    names = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        names.update(re.findall(r"@deepseek-ai/[a-z0-9][a-z0-9-]*", line))
    return names


def test_patch_references_and_peers_are_mutually_consistent():
    manifest = _manifest()
    peers = set(manifest.get("peerDependencies", {}))
    referenced = _patch_referenced_dsh_packages()
    assert referenced, "patch 里一个 @deepseek-ai/* 都没扫到——引用面解析坏了？"
    missing = sorted(referenced - peers)
    extra = sorted(peers - referenced)
    assert not missing, "patch 引用但未声明为 peer（漏声明）：%s" % missing
    assert not extra, "声明了 patch 并未引用的 peer（冗余约束会挡住可兼容宿主）：%s" % extra


def test_peer_ranges_keep_prerelease_branch_and_conservative_ceiling():
    manifest = _manifest()
    peers = manifest.get("peerDependencies", {})
    assert peers, "peerDependencies 不应为空"
    for name, spec in sorted(peers.items()):
        assert PEER_RANGE_RE.match(spec), (
            "%s 的范围 %r 不是「带预发布分支的保守上限」形态——没有预发布分支的范围"
            "会静默排除 rc 宿主（node-semver 规则）" % (name, spec))


def test_engines_declared_conservatively():
    manifest = _manifest()
    engines = manifest.get("dsh", {}).get("engines", {})
    assert ENGINES_RANGE_RE.match(engines.get("dsh", "")), (
        "dsh.engines.dsh 应为保守上限形态（>=0.2.0-rc.N <0.3）：当前 %r"
        % engines.get("dsh"))


def test_self_reference_and_patch_file_exist():
    manifest = _manifest()
    # !!js 自引用（createRequire(baseUrl).resolve('.../package.json')）的前提
    assert manifest.get("exports", {}).get("./package.json") == "./package.json"
    patch_rel = manifest.get("dsh", {}).get("bundle", {}).get("patch")
    assert patch_rel == "./cordis.patch.yml", "bundle.patch 应为包根相对路径"
    assert os.path.isfile(os.path.join(DSH_DIR, patch_rel.lstrip("./"))), \
        "dsh.bundle.patch 指向的文件不存在"
