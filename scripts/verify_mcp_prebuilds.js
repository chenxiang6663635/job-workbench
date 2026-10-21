#!/usr/bin/env node
/**
 * DSH 插件打包前置门禁（npm prepack，2026-10-21，G1 例外 #3）。
 *
 * 为什么用 Node 而不是复用 Python 版：`npm pack` / `npm publish` 只保证 Node 存在，
 * 不保证系统里有 Python——门禁必须由**打包命令本身**能执行的环境跑，否则等于没有。
 *
 * 用法（两个 package.json 的 prepack 都指向它）：
 *   node <repo>/scripts/verify_mcp_prebuilds.js <平台包目录>
 *     - 平台子包：node ../../../scripts/verify_mcp_prebuilds.js .
 *     - 主包：    node ../scripts/verify_mcp_prebuilds.js ./platform/win32-x64
 *
 * 判据（任一不符 → exit 1，npm pack 直接失败）：
 *   1. prebuilds.json 存在，且没有 .stale 残留（失败构建会留下）；
 *   2. manifest 里每个文件都存在且 SHA256 一致；
 *   3. **反向集合**：平台包目录下 bin/ 里的每个文件都在 manifest 中（拒绝未登记载荷）；
 *   4. bin/_internal/certifi/cacert.pem 不含 G3 且 SHA256 等于安全基线。
 */
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const CERTIFI_SAFE_PEM_SHA =
  "50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785";
const G3_LABEL = "emSign ECC Root CA - G3";

function fail(msg) {
  console.error("PACK GATE FAIL: " + msg);
  process.exit(1);
}

function sha256(file) {
  const h = crypto.createHash("sha256");
  h.update(fs.readFileSync(file));
  return h.digest("hex");
}

function walk(dir, base, out) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const st = fs.statSync(full);
    if (st.isDirectory()) walk(full, base, out);
    else out.push(path.relative(base, full).split(path.sep).join("/"));
  }
  return out;
}

function main() {
  const arg = process.argv[2];
  if (!arg) fail("用法: node verify_mcp_prebuilds.js <平台包目录>");
  const root = path.resolve(process.cwd(), arg);
  const manifestPath = path.join(root, "prebuilds.json");
  const stalePath = path.join(root, "prebuilds.json.stale");

  if (!fs.existsSync(manifestPath)) {
    if (fs.existsSync(stalePath)) {
      fail(
        "prebuilds.json 缺失但存在 .stale —— 上次构建未走完（失败或中断），旧制品不得打包。" +
          "重跑 scripts/build_mcp_exe.ps1 直到成功。"
      );
    }
    fail("prebuilds.json 不存在 —— 先跑 scripts/build_mcp_exe.ps1");
  }
  if (fs.existsSync(stalePath)) {
    fail("存在 prebuilds.json.stale —— 上次构建未清理干净，先确认构建成功并删除该文件");
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const files = manifest.files || {};
  const keys = Object.keys(files);
  if (keys.length === 0) fail("prebuilds.json 没有 files 清单");

  const missing = [];
  const mismatched = [];
  for (const rel of keys) {
    const full = path.join(root, rel);
    if (!fs.existsSync(full)) {
      missing.push(rel);
    } else if (sha256(full) !== files[rel]) {
      mismatched.push(rel);
    }
  }
  if (missing.length || mismatched.length) {
    fail(
      `清单与实际产物不符：缺失 ${missing.length} 个 ${JSON.stringify(missing.slice(0, 5))}；` +
        `哈希不符 ${mismatched.length} 个 ${JSON.stringify(mismatched.slice(0, 5))}`
    );
  }

  // 反向集合：bin/ 下的每个实际文件都必须登记（拒绝未登记载荷）
  const binDir = path.join(root, "bin");
  if (fs.existsSync(binDir)) {
    const actual = walk(binDir, root, []);
    const unregistered = actual.filter((rel) => !(rel in files));
    if (unregistered.length) {
      fail(
        `bin/ 中有 ${unregistered.length} 个未登记文件（可能是旧构建残留或未审核载荷）：` +
          JSON.stringify(unregistered.slice(0, 5))
      );
    }
  }

  const pemPath = path.join(root, "bin", "_internal", "certifi", "cacert.pem");
  if (!fs.existsSync(pemPath)) fail("随包 CA 清单缺失: bin/_internal/certifi/cacert.pem");
  const pemText = fs.readFileSync(pemPath, "utf8");
  if (pemText.includes(G3_LABEL)) {
    fail(`随包 CA 清单含受影响的 ${G3_LABEL}（PYSEC-2026-4320）——拒绝打包`);
  }
  const pemSha = sha256(pemPath);
  if (pemSha !== CERTIFI_SAFE_PEM_SHA) {
    fail(`随包 PEM SHA256 ${pemSha} 与已审核基线 ${CERTIFI_SAFE_PEM_SHA} 不一致——拒绝打包`);
  }

  console.log(
    `PACK GATE OK: ${keys.length} 文件哈希一致、反向集合无未登记文件、无 G3、PEM = ${CERTIFI_SAFE_PEM_SHA.slice(0, 12)} 基线`
  );
}

main();
