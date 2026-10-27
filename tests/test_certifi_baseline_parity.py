# -*- coding: utf-8 -*-
"""certifi 基线的三方一致性：构建门禁与两道校验门禁必须说同一个值。

为什么需要这个测试（2026-10-27）：
    曾出现「`verify_mcp_prebuilds.{py,js}` 升到 2026.10.23，而
    `build_mcp_exe.ps1` 仍停在 2026.10.19」的工作树状态，且当时**没有任何测试**
    能发现——因为唯一相关的那条基线测试属于另一条未提交的升级线，会被一起带走。

    这种不一致的后果只在真机构建时暴露：
      · 构建放过（10.19）、打包前校验拒绝（10.23）→ 卡在最后一步
      · 或者反过来：校验放过、构建拒绝 → 卡在第一步
    两种都表现为「本机明明能构建」，排查成本极高。

本测试**不检查版本号应该是多少**——那是安全基线评审（四条门禁）的事。
它只回答一个问题：三处说的是不是同一个值。
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BUILDER = "scripts/build_mcp_exe.ps1"
VERIFIER_PY = "scripts/verify_mcp_prebuilds.py"
VERIFIER_JS = "scripts/verify_mcp_prebuilds.js"


def _read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _grab(pattern, text, rel, label, flags=0):
    m = re.search(pattern, text, flags)
    assert m, "在 %s 里找不到 %s——常量名可能被改名，本测试需同步更新" % (rel, label)
    return m.group(1)


def _baselines():
    """返回 (builder_min, builder_pem, py_min, py_pem, js_pem)，PEM 统一小写。"""
    ps1 = _read(BUILDER)
    py = _read(VERIFIER_PY)
    js = _read(VERIFIER_JS)

    b_min = _grab(r'\$CertifiMin\s*=\s*"([^"]+)"', ps1, BUILDER, "$CertifiMin")
    b_pem = _grab(r'\$CertifiSafePemSha\s*=\s*"([^"]+)"', ps1, BUILDER, "$CertifiSafePemSha")
    p_min = _grab(r'CERTIFI_MIN\s*=\s*"([^"]+)"', py, VERIFIER_PY, "CERTIFI_MIN")
    p_pem = _grab(r'CERTIFI_SAFE_PEM_SHA\s*=\s*"([^"]+)"', py, VERIFIER_PY, "CERTIFI_SAFE_PEM_SHA")
    # JS 里该常量是跨行赋值，用 DOTALL 吞掉换行
    j_pem = _grab(r'CERTIFI_SAFE_PEM_SHA\s*=\s*\n?\s*"([^"]+)"', js, VERIFIER_JS,
                  "CERTIFI_SAFE_PEM_SHA", re.S)

    return b_min, b_pem.lower(), p_min, p_pem.lower(), j_pem.lower()


def test_certifi_min_matches_between_builder_and_python_verifier():
    """版本下界：PowerShell 构建脚本 与 Python 校验脚本 必须一致。"""
    b_min, _b_pem, p_min, _p_pem, _j_pem = _baselines()
    assert b_min == p_min, (
        "certifi 版本下界不一致：%s 要求 %s，而 %s 要求 %s。\n"
        "这会让「构建」与「打包前校验」用两套基线，只在真机构建时炸。\n"
        "改版本时三处必须同一批改。"
        % (BUILDER, b_min, VERIFIER_PY, p_min)
    )


def test_certifi_pem_sha_matches_across_all_three():
    """PEM 哈希：构建脚本、Python 校验、JS 校验（npm prepack 用）必须一致。"""
    _b_min, b_pem, _p_min, p_pem, j_pem = _baselines()
    assert b_pem == p_pem, (
        "PEM 基线不一致：%s = %s…，而 %s = %s…"
        % (BUILDER, b_pem[:12], VERIFIER_PY, p_pem[:12])
    )
    assert p_pem == j_pem, (
        "PEM 基线不一致：%s = %s…，而 %s = %s…（npm prepack 走 JS 那条）"
        % (VERIFIER_PY, p_pem[:12], VERIFIER_JS, j_pem[:12])
    )


def test_certifi_baseline_pem_is_full_sha256_hex():
    """PEM 基线必须是完整 64 位 hex——缩写会让比对恒不等（或恒等，取决于写法）。"""
    _b_min, b_pem, _p_min, p_pem, _j_pem = _baselines()
    for label, value in ((BUILDER, b_pem), (VERIFIER_PY, p_pem)):
        assert re.fullmatch(r"[0-9a-f]{64}", value), (
            "%s 的 PEM 基线不是完整 sha256：%r" % (label, value)
        )


def test_certifi_min_looks_like_a_version():
    """版本下界必须是 X.Y.Z 形态——防止把日期或 hash 填进来。"""
    b_min, _b_pem, p_min, _p_min_v, _j = _baselines()
    for label, value in ((BUILDER, b_min), (VERIFIER_PY, p_min)):
        assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", value), (
            "%s 的版本下界形态可疑：%r" % (label, value)
        )
